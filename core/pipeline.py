from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .audio import AudioGenerationError, EdgeWordAudioProvider, build_audio_artifacts, convert_to_alignment_wav
from .cache import LessonCache
from .config import AppConfig, DEFAULT_CONFIG
from .dictionary import lookup_definition
from .grapheme_alignment import GraphemeAlignmentError, align_grapheme_chunks
from .mfa import ForcedAlignmentError, MfaBackend, MfaUnavailableError
from .models import WordLesson
from .phonology import (
    cmudict_pronunciations,
    full_pronunciation_ipa,
    syllabify_phones,
    validate_word,
)


ProgressCallback = Callable[[str], None]


class LessonBuilder:
    def __init__(
        self,
        config: AppConfig = DEFAULT_CONFIG,
        cache: LessonCache | None = None,
        audio_provider: EdgeWordAudioProvider | None = None,
        mfa_backend: MfaBackend | None = None,
    ) -> None:
        self.config = config
        self.cache = cache or LessonCache()
        self.audio_provider = audio_provider or EdgeWordAudioProvider(config.voice, config.speech_rate)
        self._mfa_backend = mfa_backend

    def _progress(self, callback: ProgressCallback | None, message: str) -> None:
        if callback:
            callback(message)

    @staticmethod
    def _fallback_lesson(
        word: str,
        candidates: list[tuple[str, ...]],
        pronunciation_source: str,
        aligned_wav: Path,
        output_dir: Path,
        warning: str,
    ) -> WordLesson:
        fallback = output_dir / "full_word.wav"
        shutil.copy2(aligned_wav, fallback)
        pronunciation = candidates[0] if candidates else ()
        return WordLesson(
            word=word,
            display_ipa=full_pronunciation_ipa(pronunciation) if pronunciation else "",
            arpabet=pronunciation,
            chunks=[], phones=[], timeline=[], lesson_audio_path="",
            full_audio_path=str(fallback), pronunciation_source=pronunciation_source,
            warning=warning,
        )

    def build(self, value: str, progress: ProgressCallback | None = None) -> WordLesson:
        word = validate_word(value)
        cached = self.cache.load(word, self.config)
        if cached:
            self._progress(progress, "已从本地缓存读取精确分段。")
            return cached

        output_dir = self.cache.directory_for(word, self.config)
        output_dir.mkdir(parents=True, exist_ok=True)
        candidates = cmudict_pronunciations(word)
        pronunciation_source = "CMU Pronouncing Dictionary" if candidates else "MFA G2P"

        self._progress(progress, "正在生成一次自然、完整的美式单词发音……")
        with tempfile.TemporaryDirectory(prefix="build-", dir=str(output_dir)) as temporary:
            workspace = Path(temporary)
            source_audio = workspace / "complete_word.mp3"
            aligned_wav = workspace / "complete_word_16k.wav"
            self.audio_provider.synthesize(word, source_audio)
            convert_to_alignment_wav(source_audio, aligned_wav)

            try:
                mfa = self._mfa_backend or MfaBackend()
            except MfaUnavailableError as exc:
                return self._fallback_lesson(
                    word, candidates, pronunciation_source, aligned_wav, output_dir, str(exc)
                )

            try:
                if not candidates:
                    self._progress(progress, "词典未收录，正在用 MFA G2P 生成候选发音……")
                    candidates = mfa.g2p(word, workspace / "g2p", self.config.g2p_model)

                phones, selected = mfa.align_word(
                    aligned_wav, word, candidates, workspace / "alignment",
                    self.config.acoustic_model, progress,
                )
                phone_chunks = syllabify_phones(selected)
                chunks = align_grapheme_chunks(
                    word, selected, phone_chunks, strict=self.config.strict_alignment
                )
                self._progress(progress, "正在寻找自然切点并制作独立发音片段……")
                chunks, timeline, lesson_path, full_path = build_audio_artifacts(
                    aligned_wav, phones, chunks, output_dir, self.config
                )
            except (ForcedAlignmentError, GraphemeAlignmentError, AudioGenerationError) as exc:
                return self._fallback_lesson(
                    word, candidates, pronunciation_source, aligned_wav, output_dir,
                    f"完整词可以播放，但本次无法生成可信分段：{exc}",
                )

        self._progress(progress, "发音分段已完成。")
        definition, example = lookup_definition(word)
        lesson = WordLesson(
            word=word,
            display_ipa=full_pronunciation_ipa(selected),
            arpabet=selected,
            chunks=chunks,
            phones=phones,
            timeline=timeline,
            lesson_audio_path=lesson_path.name,
            full_audio_path=full_path.name,
            pronunciation_source=pronunciation_source,
            alternatives=[full_pronunciation_ipa(candidate) for candidate in candidates],
            definition=definition,
            example=example,
        )
        self.cache.save(lesson, output_dir)
        lesson.resolve_paths(output_dir)
        return lesson

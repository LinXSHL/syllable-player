from pathlib import Path

import numpy as np

from core.audio import write_wav
from core.cache import LessonCache
from core.config import AppConfig
from core.mfa import ForcedAlignmentError
from core.pipeline import LessonBuilder


class WaveProvider:
    def synthesize(self, word: str, output_path: Path) -> None:
        samples = np.zeros(8_000, dtype=np.int16)
        write_wav(output_path, samples, 16_000)


class FailingMfa:
    def align_word(self, *args, **kwargs):
        raise ForcedAlignmentError("test alignment rejection")


def test_alignment_failure_keeps_full_word_but_never_fakes_chunks(tmp_path: Path) -> None:
    builder = LessonBuilder(
        config=AppConfig(),
        cache=LessonCache(tmp_path),
        audio_provider=WaveProvider(),
        mfa_backend=FailingMfa(),
    )
    lesson = builder.build("everyone")
    assert lesson.chunks == []
    assert lesson.timeline == []
    assert "无法生成可信分段" in lesson.warning
    assert Path(lesson.full_audio_path).is_file()

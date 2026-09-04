from __future__ import annotations

import asyncio
import wave
from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from .config import AppConfig
from .models import PhoneInterval, PronunciationChunk, TimelineEvent


class AudioGenerationError(RuntimeError):
    pass


ProgressCallback = Callable[[str], None]


class EdgeWordAudioProvider:
    """Generate one natural complete-word recording; never individual chunks."""

    def __init__(self, voice: str, rate: str) -> None:
        self.voice = voice
        self.rate = rate

    def synthesize(self, word: str, output_path: Path) -> None:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - setup catches this
            raise AudioGenerationError("缺少 edge-tts；请先运行 setup.ps1。") from exc

        async def generate() -> None:
            communicator = edge_tts.Communicate(word, self.voice, rate=self.rate)
            await communicator.save(str(output_path))

        try:
            asyncio.run(generate())
        except Exception as exc:
            raise AudioGenerationError(
                "无法获取完整单词音频。请检查网络连接，然后重试。"
            ) from exc
        if not output_path.exists() or output_path.stat().st_size < 512:
            raise AudioGenerationError("语音服务没有返回有效的完整单词音频。")


def decode_to_pcm(source: Path, *, sample_rate: int = 16_000) -> np.ndarray:
    try:
        import av
    except ImportError as exc:  # pragma: no cover - setup catches this
        raise AudioGenerationError("缺少 PyAV，无法解码完整单词音频。") from exc

    decoded: list[np.ndarray] = []
    try:
        with av.open(str(source)) as container:
            if not container.streams.audio:
                raise AudioGenerationError("输入文件没有音频轨道。")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
            for frame in container.decode(audio=0):
                converted = resampler.resample(frame)
                if converted is None:
                    continue
                frames = converted if isinstance(converted, list) else [converted]
                for item in frames:
                    decoded.append(item.to_ndarray().reshape(-1).astype(np.int16, copy=False))
            flushed = resampler.resample(None)
            if flushed:
                frames = flushed if isinstance(flushed, list) else [flushed]
                for item in frames:
                    decoded.append(item.to_ndarray().reshape(-1).astype(np.int16, copy=False))
    except AudioGenerationError:
        raise
    except Exception as exc:
        raise AudioGenerationError(f"音频解码失败：{exc}") from exc
    if not decoded:
        raise AudioGenerationError("解码后没有可用的声音采样。")
    return np.concatenate(decoded)


def write_wav(path: Path, samples: np.ndarray, sample_rate: int = 16_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.asarray(samples, dtype="<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise AudioGenerationError("仅支持 16-bit PCM WAV。")
    samples = np.frombuffer(frames, dtype="<i2")
    if channels > 1:
        samples = samples.reshape(-1, channels).astype(np.int32).mean(axis=1).astype(np.int16)
    return samples.copy(), rate


def convert_to_alignment_wav(source: Path, destination: Path) -> None:
    write_wav(destination, decode_to_pcm(source), 16_000)


def _ms_to_sample(milliseconds: float, rate: int) -> int:
    return int(round(milliseconds * rate / 1000.0))


def _sample_to_ms(sample: int, rate: int) -> float:
    return sample * 1000.0 / rate


def best_quiet_cut(samples: np.ndarray, center: int, radius: int, rate: int) -> int:
    """Find a nearby low-energy zero crossing without moving outside audio."""
    if samples.size < 3:
        return max(0, min(samples.size, center))
    left = max(1, center - radius)
    right = min(samples.size - 1, center + radius)
    if right <= left:
        return max(0, min(samples.size, center))
    window = max(2, int(rate * 0.0015))
    signal = samples.astype(np.float64, copy=False)
    best_index = center
    best_score = float("inf")
    radius_scale = max(1, radius)
    for index in range(left, right + 1):
        a, b = max(0, index - window), min(samples.size, index + window)
        energy = float(np.mean(np.abs(signal[a:b]))) / 32768.0
        crosses_zero = signal[index - 1] * signal[index] <= 0
        crossing_penalty = 0.0 if crosses_zero else 0.035
        distance_penalty = abs(index - center) / radius_scale * 0.012
        score = energy + crossing_penalty + distance_penalty
        if score < best_score:
            best_score, best_index = score, index
    return best_index


def apply_fade(samples: np.ndarray, fade_samples: int) -> np.ndarray:
    result = samples.astype(np.float64, copy=True)
    length = min(fade_samples, len(result) // 2)
    if length > 0:
        ramp = np.linspace(0.0, 1.0, length, endpoint=False)
        result[:length] *= ramp
        result[-length:] *= ramp[::-1]
    return np.clip(np.rint(result), -32768, 32767).astype(np.int16)


def build_audio_artifacts(
    aligned_wav: Path,
    phones: Sequence[PhoneInterval],
    chunks: Sequence[PronunciationChunk],
    output_dir: Path,
    config: AppConfig,
) -> tuple[list[PronunciationChunk], list[TimelineEvent], Path, Path]:
    if not phones or not chunks:
        raise AudioGenerationError("没有可切片的真实音素时间范围。")
    samples, rate = read_wav(aligned_wav)
    output_dir.mkdir(parents=True, exist_ok=True)

    boundary_samples: list[int] = []
    initial = _ms_to_sample(max(0.0, phones[0].start_ms - 8.0), rate)
    boundary_samples.append(max(0, initial))
    search_radius = _ms_to_sample(config.cut_search_ms, rate)
    for left_chunk, right_chunk in zip(chunks, chunks[1:]):
        left_phone = phones[left_chunk.phone_end - 1]
        right_phone = phones[right_chunk.phone_start]
        center_ms = (left_phone.end_ms + right_phone.start_ms) / 2.0
        center = _ms_to_sample(center_ms, rate)
        cut = best_quiet_cut(samples, center, search_radius, rate)
        if cut <= boundary_samples[-1]:
            raise AudioGenerationError("相邻发音组的安全切点发生重叠。")
        boundary_samples.append(cut)
    final = _ms_to_sample(min(_sample_to_ms(len(samples), rate), phones[-1].end_ms + 10.0), rate)
    boundary_samples.append(min(len(samples), max(final, boundary_samples[-1] + 1)))

    fade_samples = max(1, _ms_to_sample(config.fade_ms, rate))
    built_chunks: list[PronunciationChunk] = []
    chunk_audio: list[np.ndarray] = []
    for chunk, start, end in zip(chunks, boundary_samples, boundary_samples[1:]):
        clip = apply_fade(samples[start:end], fade_samples)
        clip_path = output_dir / f"chunk_{chunk.index + 1:02d}.wav"
        write_wav(clip_path, clip, rate)
        chunk_audio.append(clip)
        built_chunks.append(replace(
            chunk,
            source_start_ms=_sample_to_ms(start, rate),
            source_end_ms=_sample_to_ms(end, rate),
            clip_path=clip_path.name,
        ))

    full_start = _ms_to_sample(max(0.0, phones[0].start_ms - config.full_word_lead_ms), rate)
    full_end = _ms_to_sample(
        min(_sample_to_ms(len(samples), rate), phones[-1].end_ms + config.full_word_tail_ms),
        rate,
    )
    full_samples = samples[full_start:max(full_start + 1, full_end)]
    full_path = output_dir / "full_word.wav"
    write_wav(full_path, full_samples, rate)
    silence_between = np.zeros(_ms_to_sample(config.inter_chunk_silence_ms, rate), dtype=np.int16)
    silence_before_full = np.zeros(_ms_to_sample(config.before_full_word_silence_ms, rate), dtype=np.int16)
    lesson_parts: list[np.ndarray] = []
    timeline: list[TimelineEvent] = []
    cursor_ms = 0.0
    for index, clip in enumerate(chunk_audio):
        duration_ms = _sample_to_ms(len(clip), rate)
        timeline.append(TimelineEvent("chunk", cursor_ms, cursor_ms + duration_ms, index))
        lesson_parts.append(clip)
        cursor_ms += duration_ms
        if index < len(chunk_audio) - 1:
            lesson_parts.append(silence_between)
            next_cursor = cursor_ms + config.inter_chunk_silence_ms
            timeline.append(TimelineEvent("silence", cursor_ms, next_cursor))
            cursor_ms = next_cursor
    lesson_parts.append(silence_before_full)
    next_cursor = cursor_ms + config.before_full_word_silence_ms
    timeline.append(TimelineEvent("silence", cursor_ms, next_cursor))
    cursor_ms = next_cursor
    full_duration_ms = _sample_to_ms(len(full_samples), rate)
    timeline.append(TimelineEvent("full_word", cursor_ms, cursor_ms + full_duration_ms))
    lesson_parts.append(full_samples)

    lesson_path = output_dir / "lesson.wav"
    write_wav(lesson_path, np.concatenate(lesson_parts), rate)
    return built_chunks, timeline, lesson_path, full_path


def active_chunk_at(milliseconds: float, timeline: Sequence[TimelineEvent]) -> int | None:
    for event in timeline:
        if event.kind == "chunk" and event.start_ms <= milliseconds < event.end_ms:
            return event.chunk_index
    return None

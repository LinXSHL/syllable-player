from pathlib import Path

import numpy as np

from core.audio import active_chunk_at, build_audio_artifacts, read_wav, write_wav
from core.config import AppConfig
from core.models import PhoneInterval, PronunciationChunk, TimelineEvent


def _chunk(index: int, g: str, gs: int, ge: int, ps: int, pe: int) -> PronunciationChunk:
    return PronunciationChunk(index, g, gs, ge, ps, pe, tuple("ABC"[ps:pe]), g)


def test_slice_compose_and_timeline(tmp_path: Path) -> None:
    rate = 16_000
    duration = 1.2
    t = np.arange(int(rate * duration)) / rate
    signal = (7_000 * np.sin(2 * np.pi * 180 * t)).astype(np.int16)
    # MFA-style boundaries have short quiet regions where cuts should land.
    signal[int(.292 * rate):int(.308 * rate)] = 0
    signal[int(.592 * rate):int(.608 * rate)] = 0
    source = tmp_path / "source.wav"
    write_wav(source, signal, rate)
    phones = [
        PhoneInterval("A", "a", 120, 290),
        PhoneInterval("B", "b", 310, 590),
        PhoneInterval("C", "c", 610, 880),
    ]
    chunks = [_chunk(0, "a", 0, 1, 0, 1), _chunk(1, "b", 1, 2, 1, 2), _chunk(2, "c", 2, 3, 2, 3)]
    built, timeline, lesson, full = build_audio_artifacts(source, phones, chunks, tmp_path / "out", AppConfig())

    assert lesson.is_file() and full.is_file()
    assert len(built) == 3
    assert all(Path(chunk.clip_path).name.startswith("chunk_") for chunk in built)
    assert abs(built[0].source_end_ms - 300.0) <= 3.1
    assert abs(built[1].source_end_ms - 600.0) <= 3.1
    assert [event.kind for event in timeline] == [
        "chunk", "silence", "chunk", "silence", "chunk", "silence", "full_word"
    ]
    for chunk in built:
        clip, _ = read_wav((tmp_path / "out") / chunk.clip_path)
        assert clip[0] == 0
        assert abs(int(clip[-1])) < 300
    full_samples, _ = read_wav(full)
    assert len(full_samples) < len(signal)


def test_highlight_is_neutral_during_silence_and_full_word() -> None:
    timeline = [
        TimelineEvent("chunk", 0, 400, 0),
        TimelineEvent("silence", 400, 580),
        TimelineEvent("chunk", 580, 900, 1),
        TimelineEvent("full_word", 1200, 1900),
    ]
    assert active_chunk_at(100, timeline) == 0
    assert active_chunk_at(500, timeline) is None
    assert active_chunk_at(700, timeline) == 1
    assert active_chunk_at(1500, timeline) is None

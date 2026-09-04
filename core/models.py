from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(slots=True)
class PhoneInterval:
    arpa: str
    ipa: str
    start_ms: float
    end_ms: float

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PhoneInterval":
        return cls(**value)


@dataclass(slots=True)
class PronunciationChunk:
    index: int
    grapheme: str
    grapheme_start: int
    grapheme_end: int
    phone_start: int
    phone_end: int
    arpabet: tuple[str, ...]
    ipa: str
    source_start_ms: float = 0.0
    source_end_ms: float = 0.0
    clip_path: str = ""
    alignment_cost: float = 0.0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PronunciationChunk":
        data = dict(value)
        data["arpabet"] = tuple(data["arpabet"])
        return cls(**data)


@dataclass(slots=True)
class TimelineEvent:
    kind: Literal["chunk", "silence", "full_word"]
    start_ms: float
    end_ms: float
    chunk_index: int | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TimelineEvent":
        return cls(**value)


@dataclass(slots=True)
class WordLesson:
    word: str
    display_ipa: str
    arpabet: tuple[str, ...]
    chunks: list[PronunciationChunk]
    phones: list[PhoneInterval]
    timeline: list[TimelineEvent]
    lesson_audio_path: str
    full_audio_path: str
    pronunciation_source: str
    alignment_source: str = "Montreal Forced Aligner"
    alternatives: list[str] = field(default_factory=list)
    definition: str = ""
    example: str = ""
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WordLesson":
        data = dict(value)
        data["arpabet"] = tuple(data["arpabet"])
        data["chunks"] = [PronunciationChunk.from_dict(x) for x in data["chunks"]]
        data["phones"] = [PhoneInterval.from_dict(x) for x in data["phones"]]
        data["timeline"] = [TimelineEvent.from_dict(x) for x in data["timeline"]]
        return cls(**data)

    def resolve_paths(self, base: Path) -> None:
        for field_name in ("lesson_audio_path", "full_audio_path"):
            value = Path(getattr(self, field_name))
            if not value.is_absolute():
                setattr(self, field_name, str(base / value))
        for chunk in self.chunks:
            value = Path(chunk.clip_path)
            if value and not value.is_absolute():
                chunk.clip_path = str(base / value)

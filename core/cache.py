from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict
from pathlib import Path

from .config import AppConfig, CACHE_ROOT
from .models import WordLesson


class LessonCache:
    def __init__(self, root: Path = CACHE_ROOT) -> None:
        self.root = root
        self._lock = threading.Lock()

    def directory_for(self, word: str, config: AppConfig) -> Path:
        identity = {"word": word, **asdict(config)}
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        safe_word = word.replace("'", "_").replace("-", "_")
        return self.root / f"{safe_word}-{digest}"

    def load(self, word: str, config: AppConfig) -> WordLesson | None:
        directory = self.directory_for(word, config)
        metadata = directory / "lesson.json"
        if not metadata.exists():
            return None
        try:
            lesson = WordLesson.from_dict(json.loads(metadata.read_text(encoding="utf-8")))
            lesson.resolve_paths(directory)
            paths = [Path(lesson.lesson_audio_path), Path(lesson.full_audio_path)]
            paths.extend(Path(chunk.clip_path) for chunk in lesson.chunks)
            if lesson.word != word or not lesson.chunks or any(not path.is_file() for path in paths):
                return None
            return lesson
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def save(self, lesson: WordLesson, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        payload = lesson.to_dict()
        temp = directory / "lesson.json.tmp"
        final = directory / "lesson.json"
        with self._lock:
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(final)

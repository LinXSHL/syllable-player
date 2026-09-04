from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import CACHE_ROOT


class FavoritesStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CACHE_ROOT / "user" / "favorites.json"
        self._lock = threading.Lock()

    def all(self) -> set[str]:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            return {str(value) for value in values}
        except (OSError, ValueError, TypeError):
            return set()

    def contains(self, word: str) -> bool:
        return word in self.all()

    def toggle(self, word: str) -> bool:
        with self._lock:
            values = self.all()
            active = word not in values
            if active:
                values.add(word)
            else:
                values.discard(word)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(sorted(values), ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
            return active

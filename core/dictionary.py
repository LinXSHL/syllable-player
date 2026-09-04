from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

from .config import DATA_ROOT


@lru_cache(maxsize=1)
def _local_entries() -> dict[str, dict[str, str]]:
    path = DATA_ROOT / "examples_bank.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


@lru_cache(maxsize=256)
def lookup_definition(word: str, timeout: float = 2.5) -> tuple[str, str]:
    """Best-effort learning text; pronunciation playback never depends on it."""
    local = _local_entries().get(word)
    if local:
        return str(local.get("definition", "")), str(local.get("example", ""))
    url = "https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(word)
    request = urllib.request.Request(url, headers={"User-Agent": "SyllablePlayer/2.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return "", ""
    try:
        meanings = data[0]["meanings"]
        for meaning in meanings:
            for definition in meaning.get("definitions", []):
                text = str(definition.get("definition", "")).strip()
                example = str(definition.get("example", "")).strip()
                if text:
                    return text, example
    except (IndexError, KeyError, TypeError):
        pass
    return "", ""

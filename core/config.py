from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = PROJECT_ROOT / "cache"
MODEL_ROOT = PROJECT_ROOT / ".models" / "mfa"
RUNTIME_ROOT = PROJECT_ROOT / ".runtime"
DATA_ROOT = PROJECT_ROOT / "data"


@dataclass(frozen=True, slots=True)
class AppConfig:
    voice: str = "en-US-AriaNeural"
    speech_rate: str = "-8%"
    acoustic_model: str = "english_us_arpa"
    g2p_model: str = "english_us_arpa"
    cache_schema: int = 2
    inter_chunk_silence_ms: int = 180
    before_full_word_silence_ms: int = 350
    cut_search_ms: float = 3.0
    fade_ms: float = 5.0
    full_word_lead_ms: float = 65.0
    full_word_tail_ms: float = 100.0
    strict_alignment: bool = True

    @property
    def mfa_root(self) -> Path:
        configured = os.environ.get("SYLLABLE_PLAYER_MFA_ROOT")
        return Path(configured) if configured else MODEL_ROOT


DEFAULT_CONFIG = AppConfig()

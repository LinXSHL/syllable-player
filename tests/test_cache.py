from pathlib import Path

from core.cache import LessonCache
from core.config import AppConfig


def test_cache_identity_changes_when_alignment_configuration_changes(tmp_path: Path) -> None:
    cache = LessonCache(tmp_path)
    base = cache.directory_for("everyone", AppConfig(cache_schema=2))
    upgraded = cache.directory_for("everyone", AppConfig(cache_schema=3))
    assert base != upgraded

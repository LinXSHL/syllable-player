import os

import pytest

from core.pipeline import LessonBuilder


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_LIVE_ALIGNMENT") != "1", reason="explicit live opt-in required")
def test_live_everyone_alignment() -> None:
    lesson = LessonBuilder().build("everyone")
    assert [(chunk.grapheme, chunk.ipa) for chunk in lesson.chunks] == [
        ("eve", "ˈev"), ("ry", "ri"), ("one", "wʌn")
    ]
    assert lesson.timeline[-1].kind == "full_word"

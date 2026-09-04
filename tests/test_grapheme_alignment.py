import pytest

from core.grapheme_alignment import align_grapheme_chunks
from core.phonology import syllabify_phones


@pytest.mark.parametrize(
    ("word", "phones", "expected"),
    [
        ("everyone", ("EH1", "V", "R", "IY0", "W", "AH2", "N"), ["eve", "ry", "one"]),
        ("banana", ("B", "AH0", "N", "AE1", "N", "AH0"), ["ba", "na", "na"]),
        ("beautiful", ("B", "Y", "UW1", "T", "AH0", "F", "AH0", "L"), ["beau", "ti", "ful"]),
        ("queue", ("K", "Y", "UW1"), ["queue"]),
        ("family", ("F", "AE1", "M", "AH0", "L", "IY0"), ["fa", "mi", "ly"]),
        ("record", ("R", "AH0", "K", "AO1", "R", "D"), ["re", "cord"]),
        ("strengths", ("S", "T", "R", "EH1", "NG", "K", "TH", "S"), ["strengths"]),
        ("co-op", ("K", "OW1", "AA2", "P"), ["co-", "op"]),
    ],
)
def test_common_and_complex_words_cover_spelling_and_phones(word, phones, expected) -> None:
    chunks = align_grapheme_chunks(word, phones, syllabify_phones(phones))
    assert [chunk.grapheme for chunk in chunks] == expected
    assert "".join(chunk.grapheme for chunk in chunks) == word
    assert tuple(phone for chunk in chunks for phone in chunk.arpabet) == phones


def test_everyone_exact_learning_mapping() -> None:
    phones = ("EH1", "V", "R", "IY0", "W", "AH2", "N")
    chunks = align_grapheme_chunks("everyone", phones, syllabify_phones(phones))
    assert [(chunk.grapheme, chunk.ipa) for chunk in chunks] == [
        ("eve", "ˈev"), ("ry", "ri"), ("one", "wʌn")
    ]


def test_oov_style_pronunciation_still_obeys_coverage_invariants() -> None:
    word = "codexian"
    phones = ("K", "OW1", "D", "EH0", "K", "S", "IY0", "AH0", "N")
    chunks = align_grapheme_chunks(word, phones, syllabify_phones(phones))
    assert "".join(chunk.grapheme for chunk in chunks) == word
    assert tuple(phone for chunk in chunks for phone in chunk.arpabet) == phones

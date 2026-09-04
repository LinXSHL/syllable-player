from core.phonology import full_pronunciation_ipa, syllabify_phones, validate_word


def test_everyone_phone_chunks_match_reference() -> None:
    phones = ("EH1", "V", "R", "IY0", "W", "AH2", "N")
    assert syllabify_phones(phones) == [(0, 2), (2, 4), (4, 7)]
    assert full_pronunciation_ipa(phones) == "/ˈev.ri.wʌn/"


def test_maximal_onset_for_banana() -> None:
    phones = ("B", "AH0", "N", "AE1", "N", "AH0")
    assert syllabify_phones(phones) == [(0, 2), (2, 4), (4, 6)]


def test_word_validation() -> None:
    assert validate_word("  Mother-in-law ") == "mother-in-law"
    assert validate_word("don't") == "don't"


def test_word_validation_rejects_sentences_and_digits() -> None:
    for value in ("two words", "word2", "", "hello!"):
        try:
            validate_word(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid value accepted: {value!r}")

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Sequence


VOWELS = {
    "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER",
    "EY", "IH", "IY", "OW", "OY", "UH", "UW",
}

ARPABET_IPA = {
    "AA": "ɑ", "AE": "æ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ",
    "EH": "e", "EY": "eɪ", "IH": "ɪ", "IY": "i", "OW": "oʊ",
    "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f",
    "G": "ɡ", "HH": "h", "JH": "dʒ", "K": "k", "L": "l",
    "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "r",
    "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v",
    "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ", "DX": "ɾ",
}

# Permissible General American onsets. This is used only to group an already
# known pronunciation; it never invents the pronunciation itself.
ONSET_CLUSTERS = {
    ("P",), ("B",), ("T",), ("D",), ("K",), ("G",), ("F",), ("V",),
    ("TH",), ("DH",), ("S",), ("Z",), ("SH",), ("ZH",), ("CH",),
    ("JH",), ("M",), ("N",), ("NG",), ("L",), ("R",), ("W",),
    ("Y",), ("HH",),
    ("P", "R"), ("B", "R"), ("T", "R"), ("D", "R"),
    ("K", "R"), ("G", "R"), ("F", "R"), ("TH", "R"),
    ("P", "L"), ("B", "L"), ("K", "L"), ("G", "L"), ("F", "L"),
    ("T", "W"), ("D", "W"), ("K", "W"), ("G", "W"),
    ("S", "P"), ("S", "T"), ("S", "K"), ("S", "M"), ("S", "N"),
    ("S", "F"), ("S", "W"), ("S", "L"), ("S", "R"),
    ("S", "P", "R"), ("S", "P", "L"), ("S", "T", "R"),
    ("S", "K", "R"), ("S", "K", "W"), ("S", "K", "L"),
}


def normalize_phone(phone: str) -> str:
    """Normalize MFA/CMU phone labels while retaining lexical stress."""
    value = phone.strip().upper()
    value = re.sub(r"_(?:B|I|E|S)$", "", value)
    return value


def phone_base(phone: str) -> str:
    return re.sub(r"[012]$", "", normalize_phone(phone))


def phone_stress(phone: str) -> int | None:
    match = re.search(r"([012])$", normalize_phone(phone))
    return int(match.group(1)) if match else None


def is_vowel(phone: str) -> bool:
    return phone_base(phone) in VOWELS


def phone_to_ipa(phone: str) -> str:
    base = phone_base(phone)
    stress = phone_stress(phone)
    if base == "AH":
        return "ə" if stress == 0 else "ʌ"
    if base == "ER":
        return "ɚ" if stress == 0 else "ɝ"
    return ARPABET_IPA.get(base, base.lower())


def phones_to_ipa(phones: Iterable[str], *, show_stress: bool = True) -> str:
    values = tuple(normalize_phone(p) for p in phones)
    prefix = ""
    if show_stress:
        stresses = [phone_stress(p) for p in values if is_vowel(p)]
        if 1 in stresses:
            prefix = "ˈ"
        # Secondary stress is intentionally not displayed as a chunk marker:
        # it distracts beginners and the reference interaction suppresses it.
    return prefix + "".join(phone_to_ipa(p) for p in values)


def full_pronunciation_ipa(phones: Sequence[str]) -> str:
    syllables = syllabify_phones(phones)
    return "/" + ".".join(phones_to_ipa(phones[a:b]) for a, b in syllables) + "/"


def syllabify_phones(phones: Sequence[str]) -> list[tuple[int, int]]:
    """Split a known phone sequence using vowel nuclei and maximal onsets."""
    values = tuple(normalize_phone(p) for p in phones)
    nuclei = [i for i, p in enumerate(values) if is_vowel(p)]
    if not nuclei:
        return [(0, len(values))] if values else []
    if len(nuclei) == 1:
        return [(0, len(values))]

    boundaries = [0]
    for left_nucleus, right_nucleus in zip(nuclei, nuclei[1:]):
        consonants = tuple(phone_base(p) for p in values[left_nucleus + 1:right_nucleus])
        onset_size = 0
        for size in range(len(consonants), 0, -1):
            if consonants[-size:] in ONSET_CLUSTERS:
                onset_size = size
                break
        boundary = right_nucleus - onset_size
        boundary = max(boundaries[-1] + 1, boundary)
        boundaries.append(boundary)
    boundaries.append(len(values))
    return [(a, b) for a, b in zip(boundaries, boundaries[1:]) if b > a]


@lru_cache(maxsize=1)
def _cmu_dictionary() -> dict[str, list[list[str]]]:
    try:
        import cmudict
    except ImportError as exc:  # pragma: no cover - setup catches this
        raise RuntimeError("缺少 cmudict；请先运行 setup.ps1。") from exc
    return cmudict.dict()


def cmudict_pronunciations(word: str) -> list[tuple[str, ...]]:
    raw = _cmu_dictionary().get(word.lower(), [])
    seen: set[tuple[str, ...]] = set()
    result: list[tuple[str, ...]] = []
    for pronunciation in raw:
        normalized = tuple(normalize_phone(p) for p in pronunciation)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def validate_word(value: str) -> str:
    word = value.strip().lower().replace("’", "'")
    if not re.fullmatch(r"[a-z]+(?:['-][a-z]+)*", word):
        raise ValueError("请输入只包含英文字母的单词；内部可含一个撇号或连字符。")
    if len(word) > 64:
        raise ValueError("单词过长；请输入 64 个字符以内的英文单词。")
    return word

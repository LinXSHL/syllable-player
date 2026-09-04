from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

from .config import DATA_ROOT
from .models import PronunciationChunk
from .phonology import phone_base, phones_to_ipa


class GraphemeAlignmentError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Graphone:
    grapheme_start: int
    grapheme_end: int
    phone_start: int
    phone_end: int
    cost: float


def _bases(phones: Iterable[str]) -> tuple[str, ...]:
    return tuple(phone_base(p) for p in phones)


# These correspondences are not a pronunciation generator. They constrain a
# monotonic alignment between a dictionary/model pronunciation and its written
# form. Ambiguity is resolved globally by dynamic programming.
SINGLE_RULES: dict[str, tuple[tuple[tuple[str, ...], float], ...]] = {
    "a": ((('AE',), .12), (('AH',), .28), (('EY',), .35), (('AA',), .48), (('AO',), .55)),
    "b": ((('B',), .05),), "c": ((('K',), .12), (('S',), .28)),
    "d": ((('D',), .05),), "e": ((('EH',), .15), (('IY',), .22), (('IH',), .3), (('AH',), .5), ((), .48)),
    "f": ((('F',), .05),), "g": ((('G',), .1), (('JH',), .3), (('K',), .6)),
    "h": ((('HH',), .08), ((), .75)), "i": ((('IH',), .13), (('IY',), .24), (('AY',), .3), (('AH',), .5)),
    "j": ((('JH',), .05),), "k": ((('K',), .05), ((), .8)),
    "l": ((('L',), .05),), "m": ((('M',), .05),), "n": ((('N',), .05), (('NG',), .65)),
    "o": ((('AA',), .22), (('AO',), .24), (('OW',), .22), (('AH',), .3), (('UW',), .65)),
    "p": ((('P',), .05),), "q": ((('K',), .25),), "r": ((('R',), .05),),
    "s": ((('S',), .08), (('Z',), .2), (('SH',), .55), ((), .85)),
    "t": ((('T',), .06), (('DX',), .22), (('CH',), .65), ((), .9)),
    "u": ((('AH',), .2), (('UW',), .22), (('UH',), .32), (('Y', 'UW'), .38), (('IH',), .75)),
    "v": ((('V',), .05),), "w": ((('W',), .06), ((), .75)),
    "x": ((('K', 'S'), .12), (('G', 'Z'), .3), (('Z',), .55)),
    "y": ((('Y',), .15), (('IY',), .16), (('IH',), .28), (('AY',), .34)),
    "z": ((('Z',), .05),), "'": (((), .0),), "-": (((), .0),),
}


MULTI_RULES: dict[str, tuple[tuple[tuple[str, ...], float], ...]] = {
    "bb": ((('B',), .08),), "cc": ((('K',), .16), (('K', 'S'), .36)),
    "dd": ((('D',), .08),), "ff": ((('F',), .08),), "gg": ((('G',), .1),),
    "ll": ((('L',), .08),), "mm": ((('M',), .08),), "nn": ((('N',), .08),),
    "pp": ((('P',), .08),), "rr": ((('R',), .08),), "ss": ((('S',), .1), (('Z',), .25)),
    "tt": ((('T',), .08),), "zz": ((('Z',), .08),),
    "ch": ((('CH',), .03), (('K',), .4), (('SH',), .55)),
    "ck": ((('K',), .03),), "dg": ((('JH',), .3),), "dge": ((('JH',), .04),),
    "gh": (((), .28), (('G',), .5), (('F',), .6)), "gn": ((('N',), .18),),
    "kn": ((('N',), .12),), "mb": ((('M',), .2),), "ng": ((('NG',), .03), (('N', 'JH'), .42)),
    "nk": ((('NG', 'K'), .08),), "ph": ((('F',), .03),), "ps": ((('S',), .22),),
    "qu": ((('K', 'W'), .08), (('K',), .35),), "rh": ((('R',), .16),),
    "sc": ((('S',), .3), (('S', 'K'), .35),), "sh": ((('SH',), .03),),
    "th": ((('TH',), .03), (('DH',), .08)), "tch": ((('CH',), .03),),
    "wh": ((('W',), .08), (('HH', 'W'), .3)), "wr": ((('R',), .12),),
    "ai": ((('EY',), .08), (('EH',), .5)), "ay": ((('EY',), .08),),
    "au": ((('AO',), .1), (('AA',), .42)), "aw": ((('AO',), .08),),
    "ea": ((('IY',), .08), (('EH',), .18), (('EY',), .4)), "ee": ((('IY',), .04),),
    "ei": ((('IY',), .22), (('EY',), .25), (('AY',), .45)), "ey": ((('IY',), .13), (('EY',), .2)),
    "ie": ((('IY',), .18), (('AY',), .2)), "igh": ((('AY',), .04),),
    "oa": ((('OW',), .06),), "oe": ((('OW',), .12), (('UW',), .5)),
    "oi": ((('OY',), .06),), "oy": ((('OY',), .06),),
    "oo": ((('UW',), .06), (('UH',), .15)), "ou": ((('AW',), .12), (('AH',), .2), (('UW',), .25), (('OW',), .38)),
    "ow": ((('AW',), .1), (('OW',), .12)), "ue": ((('UW',), .15), (('Y', 'UW'), .28)),
    "ui": ((('UW',), .2), (('IH',), .32)), "ew": ((('UW',), .16), (('Y', 'UW'), .2)),
    "ar": ((('AA', 'R'), .08), (('ER',), .4)), "er": ((('ER',), .08),),
    "ir": ((('ER',), .1),), "or": ((('AO', 'R'), .12), (('ER',), .45)), "ur": ((('ER',), .1),),
    "air": ((('EH', 'R'), .09),), "ear": ((('IH', 'R'), .15), (('ER',), .28)),
    "eau": ((('OW',), .25), (('Y', 'UW'), .12)),
    "eigh": ((('EY',), .04), (('AY',), .35)),
    "ough": ((('OW',), .18), (('AO',), .22), (('AH', 'F'), .3), (('AW',), .32), (('UW',), .5)),
    "augh": ((('AO',), .15), (('AE', 'F'), .4)),
    "tion": ((('SH', 'AH', 'N'), .04),), "sion": ((('ZH', 'AH', 'N'), .08), (('SH', 'AH', 'N'), .15)),
    "cian": ((('SH', 'AH', 'N'), .08),), "ture": ((('CH', 'ER'), .12), (('CH', 'UH', 'R'), .3)),
    "one": ((('W', 'AH', 'N'), .02),),
    "queue": ((('K', 'Y', 'UW'), .01),),
    "beau": ((('B', 'Y', 'UW'), .03), (('B', 'OW'), .2)),
}


def _rule_candidates(text: str) -> tuple[tuple[tuple[str, ...], float], ...]:
    if len(text) == 1:
        return SINGLE_RULES.get(text, ())
    return MULTI_RULES.get(text, ())


def align_graphones(word: str, phones: Sequence[str]) -> tuple[list[Graphone], float]:
    target = _bases(phones)
    n, m = len(word), len(target)
    best: dict[tuple[int, int], tuple[float, tuple[int, int, float] | None]] = {(0, 0): (0.0, None)}

    for i in range(n + 1):
        for j in range(m + 1):
            current = best.get((i, j))
            if current is None or i == n:
                continue
            current_cost = current[0]
            for letters_len in range(1, min(5, n - i) + 1):
                written = word[i:i + letters_len]
                for expected, rule_cost in _rule_candidates(written):
                    count = len(expected)
                    if j + count > m or target[j:j + count] != expected:
                        continue
                    state = (i + letters_len, j + count)
                    cost = current_cost + rule_cost
                    if state not in best or cost < best[state][0]:
                        best[state] = (cost, (i, j, rule_cost))

            # A guarded escape hatch lets unusual/OOV spellings be represented,
            # but its high cost makes low-confidence results fail strict mode.
            if j < m and word[i].isalpha():
                state = (i + 1, j + 1)
                cost = current_cost + 5.5
                if state not in best or cost < best[state][0]:
                    best[state] = (cost, (i, j, 5.5))
            state = (i + 1, j)
            cost = current_cost + 7.0
            if state not in best or cost < best[state][0]:
                best[state] = (cost, (i, j, 7.0))

    final = best.get((n, m))
    if final is None:
        raise GraphemeAlignmentError("无法把该拼写与实际发音可靠对应。")

    graphones: list[Graphone] = []
    cursor = (n, m)
    while cursor != (0, 0):
        _, previous = best[cursor]
        if previous is None:
            raise GraphemeAlignmentError("拼写—发音对齐路径不完整。")
        prev_i, prev_j, edge_cost = previous
        graphones.append(Graphone(prev_i, cursor[0], prev_j, cursor[1], edge_cost))
        cursor = (prev_i, prev_j)
    graphones.reverse()
    return graphones, final[0]


@lru_cache(maxsize=1)
def _overrides() -> dict[str, list[dict[str, object]]]:
    path = DATA_ROOT / "alignment_overrides.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _chunks_from_override(word: str, phones: Sequence[str]) -> list[PronunciationChunk] | None:
    rows = _overrides().get(word)
    if not rows:
        return None
    if "".join(str(row["grapheme"]) for row in rows) != word:
        raise GraphemeAlignmentError(f"{word} 的人工校正规则没有完整覆盖拼写。")
    cursor_g = cursor_p = 0
    chunks: list[PronunciationChunk] = []
    actual = _bases(phones)
    for index, row in enumerate(rows):
        grapheme = str(row["grapheme"])
        expected = tuple(str(x).upper() for x in row["arpabet"])
        if actual[cursor_p:cursor_p + len(expected)] != expected:
            return None
        next_g, next_p = cursor_g + len(grapheme), cursor_p + len(expected)
        chunks.append(PronunciationChunk(
            index=index, grapheme=grapheme, grapheme_start=cursor_g, grapheme_end=next_g,
            phone_start=cursor_p, phone_end=next_p, arpabet=tuple(phones[cursor_p:next_p]),
            ipa=phones_to_ipa(phones[cursor_p:next_p]), alignment_cost=0.0,
        ))
        cursor_g, cursor_p = next_g, next_p
    return chunks if cursor_p == len(phones) else None


def align_grapheme_chunks(
    word: str,
    phones: Sequence[str],
    phone_chunks: Sequence[tuple[int, int]],
    *,
    strict: bool = True,
) -> list[PronunciationChunk]:
    """Return learner chunks whose spelling and phone ranges each cover once."""
    corrected = _chunks_from_override(word, phones)
    if corrected is not None:
        return corrected

    graphones, total_cost = align_graphones(word, phones)
    normalized_cost = total_cost / max(1, len(phones))
    if strict and normalized_cost > 2.2:
        raise GraphemeAlignmentError(
            "已找到发音，但拼写—发音对应的可信度不足；程序不会显示猜测性分段。"
        )

    # A graphone such as x↔/ks/ can straddle a phonological syllable boundary.
    # It cannot be highlighted as two half-letters, so merge the two adjacent
    # learning groups while keeping every phone and grapheme intact.
    safe_phone_chunks: list[tuple[int, int]] = []
    for phone_start, phone_end in phone_chunks:
        if safe_phone_chunks:
            boundary = safe_phone_chunks[-1][1]
            crosses = any(
                graphone.phone_start < boundary < graphone.phone_end
                for graphone in graphones
            )
            if crosses:
                previous_start, _ = safe_phone_chunks[-1]
                safe_phone_chunks[-1] = (previous_start, phone_end)
                continue
        safe_phone_chunks.append((phone_start, phone_end))

    grapheme_boundaries = [0]
    for _, phone_end in safe_phone_chunks[:-1]:
        boundary: int | None = None
        for graphone in graphones:
            if graphone.phone_end <= phone_end:
                boundary = graphone.grapheme_end
            elif graphone.phone_start >= phone_end:
                break
        if boundary is None or boundary <= grapheme_boundaries[-1]:
            raise GraphemeAlignmentError("无法确定发音组之间的拼写边界。")
        grapheme_boundaries.append(boundary)
    grapheme_boundaries.append(len(word))

    chunks: list[PronunciationChunk] = []
    for index, ((phone_start, phone_end), (g_start, g_end)) in enumerate(
        zip(safe_phone_chunks, zip(grapheme_boundaries, grapheme_boundaries[1:]))
    ):
        relevant_cost = sum(
            item.cost for item in graphones
            if item.grapheme_start >= g_start and item.grapheme_end <= g_end
        )
        selected = tuple(phones[phone_start:phone_end])
        chunks.append(PronunciationChunk(
            index=index, grapheme=word[g_start:g_end], grapheme_start=g_start,
            grapheme_end=g_end, phone_start=phone_start, phone_end=phone_end,
            arpabet=selected, ipa=phones_to_ipa(selected), alignment_cost=relevant_cost,
        ))

    if "".join(chunk.grapheme for chunk in chunks) != word:
        raise GraphemeAlignmentError("拼写分段没有完整覆盖单词。")
    if tuple(p for chunk in chunks for p in chunk.arpabet) != tuple(phones):
        raise GraphemeAlignmentError("音素分段没有完整覆盖实际发音。")
    return chunks

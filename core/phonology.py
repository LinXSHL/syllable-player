# -*- coding: utf-8 -*-
"""
音节学引擎：拼写切分 + 音素切分 + ARPAbet→IPA + 对齐校验
输出统一的 segments 结构：[{spell, ipa, arpabet, n_ph, vowel_n_ph}, ...]
"""
import json
import os
import re

import pronouncing
import pyphen

# ---------------- ARPAbet -> IPA 映射（去掉了重音数字，重音单独处理） ----------------
ARPABET_TO_IPA = {
    # 元音
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "EH": "e", "ER": "ər",
    "IH": "ɪ", "IY": "i", "UH": "ʊ", "UW": "u", "AX": "ə", "AXR": "ər",
    "EY": "eɪ", "AY": "aɪ", "OW": "oʊ", "AW": "aʊ", "OY": "ɔɪ",
    # 辅音
    "P": "p", "B": "b", "T": "t", "D": "d", "K": "k", "G": "ɡ",
    "F": "f", "V": "v", "TH": "θ", "DH": "ð", "S": "s", "Z": "z",
    "SH": "ʃ", "ZH": "ʒ", "HH": "h", "CH": "tʃ", "JH": "dʒ",
    "M": "m", "N": "n", "NG": "ŋ", "L": "l", "R": "r",
    "W": "w", "Y": "j", "Q": "ʔ", "DX": "ɾ", "NX": "ɾ̃", "EL": "l̩", "EM": "m̩", "EN": "n̩",
}

# 合法的词首辅音丛（maximal onset 判断用），基于 ARPAbet 符号
_VALID_ONSETS = {
    "P", "B", "T", "D", "K", "G", "F", "V", "TH", "DH", "S", "Z", "SH", "ZH",
    "HH", "CH", "JH", "M", "N", "NG", "L", "R", "W", "Y",
    "P R", "B R", "T R", "D R", "K R", "G R", "F R", "TH R", "SH R",
    "P L", "B L", "K L", "G L", "F L", "S L",
    "P Y", "B Y", "T Y", "D Y", "K Y", "G Y", "F Y", "V Y", "M Y", "N Y", "HH Y", "L Y", "R Y", "W Y", "S Y",
    "S P", "S T", "S K", "S M", "S N", "S F", "S W", "T W", "D W", "K W", "G W", "S TH",
    "S P R", "S T R", "S K R", "S P L", "S K W", "S P Y", "S T Y", "S K Y", "TH W", "K L Y",
    "T S", "D Z", "P S", "K S",
}

_VOWELS_LETTERS = "aeiouy"
_DIC = pyphen.Pyphen(lang="en_US")

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OVERRIDES_PATH = os.path.join(_BASE_DIR, "data", "overrides.json")


def _load_overrides():
    if os.path.exists(_OVERRIDES_PATH):
        try:
            with open(_OVERRIDES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _is_vowel_phoneme(ph):
    return ph[-1].isdigit()


def syllabify_phonemes(phones):
    """
    把 ARPAbet 音素列表切成音节（maximal onset 原则）。
    输入: ["EH1", "V", "R", "IY0", "W", "AH2", "N"]
    输出: [["EH1", "V"], ["R", "IY0"], ["W", "AH2", "N"]]
    """
    vowel_idx = [i for i, ph in enumerate(phones) if _is_vowel_phoneme(ph)]
    if not vowel_idx:
        return [phones]

    # 边界点：音节 k 从哪个下标开始
    bounds = [0]
    for a, b in zip(vowel_idx, vowel_idx[1:]):
        cluster = phones[a + 1: b]
        # 从长到短找合法 onset 后缀
        split_at = a + 1  # 默认全部归后一音节
        base = [re.sub(r"\d", "", p) for p in cluster]
        best = None
        for length in range(len(cluster), 0, -1):
            cand = " ".join(base[len(cluster) - length:])
            if cand in _VALID_ONSETS:
                best = length
                break
        if best is None:  # 没有合法 onset（理论上单辅音总在表里，这里兜底）
            best = len(cluster)
        split_at = b - best
        bounds.append(split_at)
    bounds.append(len(phones))

    syllables = []
    for s, e in zip(bounds, bounds[1:]):
        if s < e:
            syllables.append(phones[s:e])
    return syllables


def syllable_to_ipa(syllable_phones):
    """单个音节的 ARPAbet -> IPA 字符串；主重音(1)加 '，次重音(2)不单独标注"""
    stress = ""
    parts = []
    for ph in syllable_phones:
        if ph[-1] == "1":
            stress = "'"
        base = re.sub(r"\d", "", ph)
        # 非重读的 AH（即 AH0）实际发弱化的 ə
        if base == "AH" and ph[-1] == "0":
            parts.append("ə")
            continue
        parts.append(ARPABET_TO_IPA.get(base, base.lower()))
    return stress + "".join(parts)


def _vowel_groups(text):
    """拼写中元音字母组的区间列表，如 'everyone' -> [(0,1,'e'),(2,4,'ery'...)] 返回 (start,end)"""
    groups = []
    i = 0
    while i < len(text):
        if text[i] in _VOWELS_LETTERS:
            j = i
            while j < len(text) and text[j] in _VOWELS_LETTERS:
                j += 1
            groups.append((i, j))
            i = j
        else:
            i += 1
    return groups


def _split_spelling_by_rules(word, n_target):
    """
    按元音字母组把拼写切成 n_target 段（近似切分）。
    思路：定位前 n_target 个元音组作为各音节的核，元音组之间的辅音按 maximal onset 近似分配。
    """
    word = word.lower()
    groups = _vowel_groups(word)
    if len(groups) < n_target:
        return None
    nuclei = groups[:n_target]
    cuts = [0]
    for (s1, e1), (s2, e2) in zip(nuclei, nuclei[1:]):
        cons = word[e1:s2]
        if len(cons) <= 1:
            cut = e1 + len(cons)  # 0或1个辅音：辅音归后一音节
            if len(cons) == 1:
                cut = e1
        else:
            cut = e1 + len(cons) // 2  # 辅音丛均分（近似）
        cuts.append(cut)
    cuts.append(len(word))
    chunks = [word[a:b] for a, b in zip(cuts, cuts[1:]) if word[a:b]]
    if len(chunks) != n_target:
        return None
    return chunks


def split_spelling(word, n_target):
    """
    拼写切分，目标 n_target 段。
    回退链：overrides.json -> pyphen -> 元音组规则 -> 等长切分
    返回 (chunks, approx: bool)
    """
    w = word.lower()
    overrides = _load_overrides()
    if w in overrides and len(overrides[w]) == n_target:
        return overrides[w], False

    hyph = _DIC.inserted(w)  # 如 eve-ry-one
    chunks = [c for c in hyph.split("-") if c]
    if len(chunks) == n_target:
        return chunks, False

    rule_chunks = _split_spelling_by_rules(w, n_target)
    if rule_chunks:
        return rule_chunks, True

    # 最终兜底：等长切分
    L = len(w)
    base, rem = divmod(L, n_target)
    chunks, pos = [], 0
    for k in range(n_target):
        size = base + (1 if k < rem else 0)
        chunks.append(w[pos:pos + size])
        pos += size
    return [c for c in chunks if c], True


def analyze(word):
    """
    主入口：输入单词，输出 segments 列表与元信息。
    返回 dict:
    {
      "word": ..., "ok": bool, "approx": bool, "reason": str|None,
      "segments": [{"i","spell","ipa","arpabet","n_ph","n_vowel"}...],
      "ipa_full": "/'evriwʌn/"
    }
    """
    w = word.strip().lower()
    if not re.fullmatch(r"[a-z][a-z'\-]*", w):
        return {"word": word, "ok": False, "approx": False,
                "reason": "请输入英文字母组成的单词", "segments": [], "ipa_full": ""}

    phones_list = pronouncing.phones_for_word(w)
    if not phones_list:
        return {"word": w, "ok": False, "approx": False,
                "reason": "词典未收录该词（CMUdict OOV）", "segments": [], "ipa_full": ""}

    phones = phones_list[0].split()
    syl_phones = syllabify_phonemes(phones)
    n = len(syl_phones)
    spell_chunks, approx = split_spelling(w, n)

    segments = []
    for i, sp in enumerate(syl_phones):
        segments.append({
            "i": i,
            "spell": spell_chunks[i] if i < len(spell_chunks) else "",
            "ipa": syllable_to_ipa(sp),
            "arpabet": sp,
            "n_ph": len(sp),
            "n_vowel": sum(1 for p in sp if _is_vowel_phoneme(p)),
        })
    return {
        "word": w, "ok": True, "approx": approx,
        "reason": None if not approx else "拼写切分为近似结果",
        "segments": segments,
        "ipa_full": "/" + "".join(s["ipa"] for s in segments) + "/",
    }


if __name__ == "__main__":
    import sys
    for w in (sys.argv[1:] or ["everyone", "beautiful", "cat", "university", "schedule"]):
        r = analyze(w)
        print(w, "->", r["reason"] or "OK",
              " | ".join(f'{s["spell"]}|/{s["ipa"]}/' for s in r["segments"]))

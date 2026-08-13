# -*- coding: utf-8 -*-
"""
音节级时间轴：把整词时间窗 (start_ms, end_ms) 按各音节音素权重切分。
权重 = 辅音音素数 × 1.0 + 元音音素数 × 1.35（元音发音更长）。
后续若接入 aeneas 强制对齐，只需替换 build_segment_timeline 的实现。
"""

VOWEL_WEIGHT = 1.35
CONS_WEIGHT = 1.0


def build_segment_timeline(segments, word_start_ms, word_end_ms):
    """
    segments: phonology.analyze 输出的段列表（就地写入 start_ms/end_ms）
    返回带时间的 segments。
    """
    total = max(word_end_ms - word_start_ms, 1.0)
    weights = []
    for s in segments:
        n_v = s.get("n_vowel", 1)
        n_c = s.get("n_ph", 1) - n_v
        weights.append(n_v * VOWEL_WEIGHT + n_c * CONS_WEIGHT)
    w_sum = sum(weights) or 1.0

    cursor = word_start_ms
    for s, w in zip(segments, weights):
        dur = total * w / w_sum
        s["start_ms"] = round(cursor, 1)
        s["end_ms"] = round(cursor + dur, 1)
        cursor += dur
    return segments

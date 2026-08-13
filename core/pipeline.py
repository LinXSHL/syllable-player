# -*- coding: utf-8 -*-
"""
数据流水线（两阶段）：
- build_core(word)：音节切分 + 单词 TTS + 词典（并行快路径），UI 拿到即可首渲染
- build_extras(word, data)：例句 TTS（词级时间戳）+ 配图（慢路径），完成后回填缓存
缓存命中直接返回完整数据（extras_pending=False）。
"""
import os
from concurrent.futures import ThreadPoolExecutor

from core import cache, dictionary, images, phonology, timing, tts

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = cache.CACHE_DIR


def build_core(word):
    """阶段1：返回核心 WordData。出错返回 {"word":..., "error": "..."}。"""
    w = word.strip().lower()

    hit = cache.load(w)
    if hit:
        audio = (hit.get("audio") or {}).get("word") or ""
        if audio and os.path.exists(audio):
            hit["from_cache"] = True
            # 例句时间戳或配图缺失时，标记需要阶段2补抓
            hit["extras_pending"] = not (
                hit.get("example_words") and hit.get("image_path"))
            return hit
        # 缓存缺音频：视为未缓存，重建

    ph = phonology.analyze(w)
    if not ph["ok"]:
        return {"word": w, "error": ph["reason"] or "切分失败"}

    word_mp3 = os.path.join(CACHE_DIR, f"{w}.mp3")
    dict_info, word_window = {}, (0.0, 1500.0)
    errors = []

    # 硬性超时：任何在线模块最多等 25s，超时降级但保证界面及时渲染
    pool = ThreadPoolExecutor(max_workers=2)
    fut_tts = pool.submit(tts.synth_word, w, word_mp3)
    fut_dict = pool.submit(dictionary.lookup, w)
    try:
        word_window = fut_tts.result(timeout=25)
    except Exception as e:
        errors.append(f"语音合成超时/失败：{type(e).__name__}")
    try:
        dict_info = fut_dict.result(timeout=25)
    except Exception as e:
        errors.append(f"词典查询超时/失败：{type(e).__name__}")
    pool.shutdown(wait=False, cancel_futures=True)

    segments = timing.build_segment_timeline(ph["segments"], *word_window)

    data = {
        "word": w,
        "approx": ph["approx"],
        "notice": ph["reason"],
        "errors": errors,
        "ipa_full": ph["ipa_full"],
        "segments": segments,
        "pos": dict_info.get("pos", ""),
        "definition_en": dict_info.get("definition_en", ""),
        "definition_zh": dict_info.get("definition_zh", ""),
        "example_en": dict_info.get("example_en", ""),
        "example_zh": dict_info.get("example_zh", ""),
        "example_words": [],
        "image_path": "",
        "audio": {"word": word_mp3 if os.path.exists(word_mp3) else "",
                  "example": ""},
        "extras_pending": True,
        "from_cache": False,
    }
    cache.save(w, data)
    return data


def build_extras(word, data):
    """阶段2：例句 TTS + 配图。返回补丁 dict（含 word 供 last-wins 校验）。"""
    w = word.strip().lower()
    example = data.get("example_en") or ""
    ex_mp3 = os.path.join(CACHE_DIR, f"{w}_ex.mp3")

    def _do_ex_tts():
        if not example:
            return [], ""
        try:
            bounds = tts.synth_sentence(example, ex_mp3)
            return bounds, ex_mp3
        except Exception:
            return [], ""

    # 例句 TTS 与配图同样加硬超时
    pool = ThreadPoolExecutor(max_workers=2)
    fut_ex = pool.submit(_do_ex_tts)
    fut_img = pool.submit(images.fetch_image, w, CACHE_DIR)
    try:
        ex_bounds, ex_path = fut_ex.result(timeout=25)
    except Exception:
        ex_bounds, ex_path = [], ""
    try:
        image_path = fut_img.result(timeout=25)
    except Exception:
        image_path = None
    pool.shutdown(wait=False, cancel_futures=True)

    patch = {
        "word": w,
        "example_words": [
            {"text": t, "start_ms": round(s, 1), "end_ms": round(e, 1)}
            for (t, s, e) in ex_bounds
        ],
        "audio_example": ex_path if ex_path and os.path.exists(ex_path) else "",
        "image_path": image_path or "",
    }

    # 回填缓存（以磁盘上的最新 JSON 为准合并，避免覆盖并发更新的字段）
    cached = cache.load(w) or dict(data)
    cached["example_words"] = patch["example_words"]
    cached.setdefault("audio", {})["example"] = patch["audio_example"]
    cached["image_path"] = patch["image_path"]
    cached["extras_pending"] = False
    cache.save(w, cached)
    return patch


if __name__ == "__main__":
    import json
    d = build_core("everyone")
    print(json.dumps(d, ensure_ascii=False, indent=2)[:1200])

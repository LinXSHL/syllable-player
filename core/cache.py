# -*- coding: utf-8 -*-
"""本地缓存：每个单词一份 JSON（含音频/图片路径），二次查询完全离线。"""
import json
import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_BASE_DIR, "data", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _json_path(word):
    return os.path.join(CACHE_DIR, f"{word.lower()}.json")


def load(word):
    path = _json_path(word)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 音频文件必须真实存在，否则视为缓存失效
        audio = data.get("audio", {})
        if audio.get("word") and not os.path.exists(audio["word"]):
            return None
        return data
    except Exception:
        return None


def save(word, data):
    path = _json_path(word)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def list_cached_words():
    words = []
    for fn in sorted(os.listdir(CACHE_DIR)):
        if fn.endswith(".json"):
            words.append(fn[:-5])
    return words

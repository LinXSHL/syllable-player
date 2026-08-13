# -*- coding: utf-8 -*-
"""
词典模块：Free Dictionary API（免密钥）取词性/英文释义/例句，deep-translator 翻译成中文。
"""
import json
import os

import requests
from deep_translator import GoogleTranslator

DICT_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
_TIMEOUT = 10

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXAMPLES_BANK_PATH = os.path.join(_BASE_DIR, "data", "examples_bank.json")


def _load_examples_bank():
    if os.path.exists(_EXAMPLES_BANK_PATH):
        try:
            with open(_EXAMPLES_BANK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _translate_zh(text):
    """英文 -> 中文，双引擎兜底：Google -> MyMemory，全失败返回空串。"""
    if not text:
        return ""
    try:
        r = GoogleTranslator(source="en", target="zh-CN").translate(text)
        if r:
            return r
    except Exception:
        pass
    try:
        from deep_translator import MyMemoryTranslator
        r = MyMemoryTranslator(source="en-US", target="zh-CN").translate(text)
        if r:
            return r
    except Exception:
        pass
    return ""


def _get_json(url, retries=2):
    """带重试的 GET，网络抖动时静默重试。"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=8 + attempt * 6)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    return None


def lookup(word):
    """
    返回 {pos, definition_en, definition_zh, example_en, example_zh}
    任何字段缺失都给空字符串，绝不抛异常。
    """
    result = {"pos": "", "definition_en": "", "definition_zh": "",
              "example_en": "", "example_zh": ""}
    data = _get_json(DICT_API.format(word=word.lower()))
    if not data:
        return result
    try:
        # 第一遍：取词性与第一条释义；同时全局搜集第一个带 example 的例句
        example_found = ""
        for entry in data:
            for meaning in entry.get("meanings", []):
                pos = meaning.get("partOfSpeech", "")
                for d in meaning.get("definitions", []):
                    if not example_found and d.get("example"):
                        example_found = d["example"]
                    if not result["definition_en"] and d.get("definition"):
                        result["pos"] = pos
                        result["definition_en"] = d["definition"]
            if result["definition_en"] and example_found:
                break
        result["example_en"] = example_found
    except Exception:
        return result

    # 例句兜底：词典没给例句时，查内置例句库；再不行用通用模板
    if not result["example_en"]:
        result["example_en"] = _load_examples_bank().get(word.lower(), "")
    if not result["example_en"]:
        result["example_en"] = f"I like the word \"{word}\"."

    result["definition_zh"] = _translate_zh(result["definition_en"])
    result["example_zh"] = _translate_zh(result["example_en"])
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(lookup("everyone"), ensure_ascii=False, indent=2))

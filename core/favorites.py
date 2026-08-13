# -*- coding: utf-8 -*-
"""收藏管理：data/favorites.json"""
import json
import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAV_PATH = os.path.join(_BASE_DIR, "data", "favorites.json")


def _load():
    if not os.path.exists(FAV_PATH):
        return []
    try:
        with open(FAV_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(items):
    os.makedirs(os.path.dirname(FAV_PATH), exist_ok=True)
    with open(FAV_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def all():
    return _load()


def contains(word):
    return word.lower() in _load()


def toggle(word):
    word = word.lower()
    items = _load()
    if word in items:
        items.remove(word)
        fav = False
    else:
        items.append(word)
        fav = True
    _save(items)
    return fav

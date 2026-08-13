# -*- coding: utf-8 -*-
"""
配图模块：为单词找一张辅助理解的图片，三级回退：
1. Openverse（开放版权图库，语义匹配最好，但国内连通性差）
2. LoremFlickr（Flickr 图源，按关键词匹配，免密钥）
3. Lorem Picsum（随机风景图，保底，保证 UI 不空）
"""
import os

import requests

_TIMEOUT = 6
_UA = {"User-Agent": "syllable-player/1.0 (educational)"}


def _download(url, path, timeout=_TIMEOUT):
    try:
        r = requests.get(url, headers=_UA, timeout=timeout)
        if r.status_code == 200 and len(r.content) > 2000:
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    except Exception:
        pass
    return None


def _from_openverse(word, path):
    try:
        resp = requests.get(
            "https://api.openverse.org/v1/images/",
            params={"q": word, "page_size": 5, "license_type": "all-cc"},
            headers=_UA, timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        for item in resp.json().get("results", []):
            url = item.get("url")
            if url and _download(url, path):
                return path
    except Exception:
        pass
    return None


def fetch_image(word, save_dir):
    """返回本地图片路径；全部图源失败时返回 None。"""
    w = word.lower()
    path = os.path.join(save_dir, f"{w}.jpg")
    return (
        _from_openverse(w, path)
        or _download(f"https://loremflickr.com/400/300/{w}", path, timeout=15)
        or _download(f"https://picsum.photos/seed/{w}/400/300", path, timeout=15)
    )


if __name__ == "__main__":
    import tempfile
    print(fetch_image("cat", tempfile.gettempdir()))

# -*- coding: utf-8 -*-
"""离屏冒烟测试：加载生命周期、last-wins、两阶段渲染、播放链路。"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()


def pump(seconds=0.05):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def wait_loaders(timeout=120):
    deadline = time.time() + timeout
    while win.loaders and time.time() < deadline:
        pump(0.1)
    pump(0.3)


# 1) 启动自动加载 everyone（缓存）——应毫秒级完整渲染
wait_loaders()
assert win.data and win.data["word"] == "everyone", "everyone 未渲染"
assert len(win.seg_row.pairs) == 3, "音节数不对"
assert win.data["extras_pending"] is False, "缓存词不应有 extras_pending"
assert win.data["example_words"], "缓存词例句时间戳缺失"
print("1) 缓存词 everyone 秒开渲染 OK")

# 2) last-wins：快速连查 3 个缓存词，最终只渲染最后一词
for w in ("cat", "banana", "family"):
    win.input.setText(w)
    win.on_search()
wait_loaders()
assert win.data["word"] == "family", f"last-wins 失效：{win.data['word']}"
assert not win.loaders, "loaders 集合未清空（线程泄漏）"
print("2) 连查 3 词 last-wins + 线程回收 OK")

# 3) 过期结果被丢弃
win._on_core_ready({"word": "apple", "segments": []})
assert win.data["word"] == "family", "过期结果未被丢弃"
print("3) 过期 coreReady 丢弃 OK")

# 4) 失败路径：红字提示而非卡死
win._req_word = "ghost"
win._on_failed({"word": "ghost", "error": "RuntimeError: boom"})
assert "加载失败" in win.lbl_status.text(), "失败未显示状态文字"
assert "#c0392b" in win.lbl_status.styleSheet(), "失败未标红"
print("4) 失败红字提示 OK")

# 5) 新词两阶段加载（真实网络）
win._req_word = None
win.input.setText("orange")
win.on_search()
# 等 core 完成（extras 可能仍在跑）
deadline = time.time() + 90
while time.time() < deadline:
    pump(0.2)
    if win.data and win.data.get("word") == "orange":
        break
assert win.data and win.data["word"] == "orange", "orange core 未渲染"
core_has_no_ts = not win.data.get("example_words")
print(f"5) orange 首渲染 OK（extras_pending={win.data['extras_pending']}，"
      f"首渲染时例句时间戳为空={core_has_no_ts}）")
wait_loaders()
assert win.data["word"] == "orange", "extras 阶段覆盖了当前词？"
if win.data.get("example_words"):
    assert "start_ms" in win.data["example_words"][0], "例句词级时间戳缺失"
print(f"   orange extras 补齐 OK（例句词数={len(win.data.get('example_words') or [])}，"
      f"图片={'Y' if win.data.get('image_path') else 'N'}）")

# 6) 播放链路：文件存在 + setSource 无异常 + 单段定位延迟到 LoadedMedia
win.on_play_word()
pump(0.5)
assert win.player.source().isLocalFile(), "播放源未设置"
seg = win.data["segments"][1]
win.on_play_segment(1)
assert win._pending_pos == seg["start_ms"], "单段定位未挂起"
win._on_media_status(QMediaPlayer.LoadedMedia)
assert win._pending_pos is None, "LoadedMedia 后定位未生效"
print("6) 播放链路 OK（源设置/单段延迟定位）")

print("\nALL SMOKE TESTS PASSED")

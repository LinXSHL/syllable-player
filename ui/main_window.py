# -*- coding: utf-8 -*-
"""主窗口：搜索、音节高亮播放、释义、例句、配图、收藏。

关键设计：
- WordLoader 两阶段信号（coreReady / extrasReady / failed），全程有可见状态文字；
- self.loaders 集合持有强引用，防止运行中的 QThread 被 GC 强杀；
- last-wins：self._req_word 记录最新请求词，过期线程的结果一律丢弃。
"""
import bisect
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core import favorites, pipeline
from ui.widgets import SegmentRow, WordHighlightLabel


class WordLoader(QThread):
    """后台加载单词数据（网络请求不阻塞 UI），任何异常都转为 failed 信号。"""
    coreReady = Signal(dict)    # 阶段1：音节/音标/单词音频/释义
    extrasReady = Signal(dict)  # 阶段2：例句词级时间戳/例句音频/配图
    failed = Signal(dict)       # {"word":..., "error":...}

    def __init__(self, word):
        super().__init__()
        self.word = word

    def run(self):
        try:
            data = pipeline.build_core(self.word)
            self.coreReady.emit(data)
            if not data.get("error") and data.get("extras_pending"):
                self.extrasReady.emit(pipeline.build_extras(self.word, data))
        except Exception as e:
            self.failed.emit({"word": self.word.strip().lower(),
                              "error": f"{type(e).__name__}: {e}"})


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("音节拆分跟读 · Syllable Player")
        self.resize(860, 680)

        self.data = None          # 当前 WordData
        self.loaders = set()      # 在飞加载线程（强引用，防 GC 强杀）
        self._req_word = None     # 最新请求词（last-wins）
        self._seg_start = None    # 单段试听的结束点
        self._pending_pos = None  # 待定位的播放位置（LoadedMedia 后生效）
        self._mode = "word"       # 当前播放器装的是 word / example

        # ---- 播放器 ----
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.audio_out.setVolume(1.0)
        self.player.setAudioOutput(self.audio_out)
        self.player.positionChanged.connect(self._on_position)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_player_error)

        # ---- 顶部：搜索 + 收藏 ----
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入英文单词，如 everyone")
        self.input.returnPressed.connect(self.on_search)
        btn_search = QPushButton("查询")
        btn_search.clicked.connect(self.on_search)
        self.btn_fav = QPushButton("☆ 收藏")
        self.btn_fav.setCheckable(True)
        self.btn_fav.clicked.connect(self.on_fav)

        top = QHBoxLayout()
        top.addWidget(self.input, 1)
        top.addWidget(btn_search)
        top.addWidget(self.btn_fav)

        # ---- 中部：音节区 ----
        self.lbl_word = QLabel("")
        f = self.lbl_word.font(); f.setPointSize(f.pointSize() + 8); f.setBold(True)
        self.lbl_word.setFont(f)
        self.lbl_ipa_full = QLabel("")
        self.lbl_ipa_full.setStyleSheet("color:#666;")
        self.seg_row = SegmentRow()
        self.btn_play = QPushButton("▶ 播放发音")
        self.btn_play.clicked.connect(self.on_play_word)
        self.lbl_notice = QLabel("")
        self.lbl_notice.setStyleSheet("color:#b8860b;")

        seg_box = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(self.lbl_word)
        head.addWidget(self.lbl_ipa_full)
        head.addStretch(1)
        head.addWidget(self.btn_play)
        seg_box.addLayout(head)
        seg_box.addWidget(self.seg_row)
        seg_box.addWidget(self.lbl_notice)

        # ---- 释义区 ----
        self.lbl_pos = QLabel("")
        self.lbl_def_en = QLabel("")
        self.lbl_def_zh = QLabel("")
        for lb in (self.lbl_def_en, self.lbl_def_zh):
            lb.setWordWrap(True)
        self.lbl_def_zh.setStyleSheet("color:#333;")

        info_box = QVBoxLayout()
        info_box.addWidget(self.lbl_pos)
        info_box.addWidget(self.lbl_def_en)
        info_box.addWidget(self.lbl_def_zh)

        # ---- 例句 + 图片 ----
        self.example_words = WordHighlightLabel()
        self.lbl_ex_zh = QLabel("")
        self.lbl_ex_zh.setWordWrap(True)
        self.btn_play_ex = QPushButton("▶ 例句")
        self.btn_play_ex.clicked.connect(self.on_play_example)

        self.lbl_image = QLabel("配图加载中…")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setFixedSize(240, 180)
        self.lbl_image.setFrameShape(QFrame.StyledPanel)

        ex_col = QVBoxLayout()
        ex_head = QHBoxLayout()
        ex_head.addWidget(QLabel("例句"))
        ex_head.addStretch(1)
        ex_head.addWidget(self.btn_play_ex)
        ex_col.addLayout(ex_head)
        ex_col.addWidget(self.example_words)
        ex_col.addWidget(self.lbl_ex_zh)
        ex_col.addStretch(1)

        ex_row = QHBoxLayout()
        ex_row.addLayout(ex_col, 1)
        ex_row.addWidget(self.lbl_image)

        # ---- 收藏列表 ----
        self.fav_list = QListWidget()
        self.fav_list.setMaximumWidth(160)
        self.fav_list.itemClicked.connect(self._on_fav_item)
        self._refresh_fav_list()

        # ---- 进度条 + 状态文字 ----
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#666;")

        # ---- 组装 ----
        left = QVBoxLayout()
        left.addLayout(top)
        left.addWidget(self.progress)
        left.addWidget(self.lbl_status)
        left.addSpacing(4)
        left.addLayout(seg_box)
        line = QFrame(); line.setFrameShape(QFrame.HLine)
        left.addWidget(line)
        left.addLayout(info_box)
        line2 = QFrame(); line2.setFrameShape(QFrame.HLine)
        left.addWidget(line2)
        left.addLayout(ex_row)
        left.addStretch(1)

        main = QHBoxLayout()
        main.addLayout(left, 1)
        side = QVBoxLayout()
        side.addWidget(QLabel("⭐ 我的收藏"))
        side.addWidget(self.fav_list)
        main.addLayout(side)

        container = QWidget()
        container.setLayout(main)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        self.setCentralWidget(container)

        self.seg_row.segClicked.connect(self.on_play_segment)

        # 启动即演示 everyone
        self.input.setText("everyone")
        self.on_search()

    # ---------------- 状态栏小字 ----------------
    def _status_info(self, text):
        self.lbl_status.setStyleSheet("color:#666;")
        self.lbl_status.setText(text)

    def _status_error(self, text):
        self.lbl_status.setStyleSheet("color:#c0392b;")
        self.lbl_status.setText(text)

    # ---------------- 搜索 / 加载 ----------------
    def on_search(self):
        word = self.input.text().strip()
        if not word:
            return
        self._stop()
        self._req_word = word.lower()
        self.progress.show()
        self.btn_play.setEnabled(False)
        self._status_info(f"⏳ 正在加载：{word}（首次查询需联网，约 5-20 秒）")
        loader = WordLoader(word)
        self.loaders.add(loader)  # 强引用，防止线程被 GC 强杀
        loader.coreReady.connect(self._on_core_ready)
        loader.extrasReady.connect(self._on_extras_ready)
        loader.failed.connect(self._on_failed)
        loader.finished.connect(lambda l=loader: self._loader_done(l))
        loader.start()

    def _loader_done(self, loader):
        self.loaders.discard(loader)
        loader.deleteLater()

    def _is_current(self, payload):
        return (payload.get("word") or "").lower() == (self._req_word or "")

    def _on_core_ready(self, data):
        if not self._is_current(data):
            return  # 过期结果，丢弃
        self.progress.hide()
        self.btn_play.setEnabled(True)
        if data.get("error"):
            self._status_error(f"无法处理「{data.get('word')}」：{data['error']}")
            QMessageBox.warning(self, "无法处理", data["error"])
            return
        self._status_info("")
        self.data = data
        self._mode = "word"
        self.lbl_word.setText(data["word"])
        self.lbl_ipa_full.setText(data.get("ipa_full", ""))
        self.seg_row.set_segments(data["segments"])
        notice = data.get("notice") or ""
        if data.get("errors"):
            notice = (notice + "　" + "；".join(data["errors"])).strip("　")
        self.lbl_notice.setText(notice)
        self.lbl_pos.setText(f"词性：{data.get('pos') or '—'}")
        self.lbl_def_en.setText(f"英释：{data.get('definition_en') or '—'}")
        self.lbl_def_zh.setText(f"中释：{data.get('definition_zh') or '—'}")
        self.lbl_ex_zh.setText(data.get("example_zh") or "")
        self.btn_fav.setChecked(favorites.contains(data["word"]))
        self._update_fav_btn()

        if data.get("extras_pending"):
            # 先用纯文本渲染例句（无时间戳），音频/配图待阶段2补齐
            ex = data.get("example_en") or ""
            self.example_words.set_words([{"text": t} for t in ex.split()] if ex else [])
            self.lbl_image.setText("配图加载中…")
            self.lbl_image.setPixmap(QPixmap())
        else:
            self.example_words.set_words(data.get("example_words") or [])
            self._show_image(data.get("image_path") or "")

    def _on_extras_ready(self, patch):
        if not self._is_current(patch) or not self.data:
            return
        self.data["example_words"] = patch.get("example_words") or []
        self.data.setdefault("audio", {})["example"] = patch.get("audio_example", "")
        self.data["image_path"] = patch.get("image_path", "")
        self.example_words.set_words(self.data["example_words"])
        self._show_image(self.data["image_path"])

    def _on_failed(self, err):
        if not self._is_current(err):
            return
        self.progress.hide()
        self.btn_play.setEnabled(True)
        self._status_error(f"加载失败：{err.get('error')}，请检查网络后重试")

    def _show_image(self, path):
        if path and os.path.exists(path):
            pm = QPixmap(path)
            if not pm.isNull():
                self.lbl_image.setPixmap(pm.scaled(
                    self.lbl_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self.lbl_image.setText("（暂无配图）")
        self.lbl_image.setPixmap(QPixmap())

    # ---------------- 收藏 ----------------
    def on_fav(self):
        if not self.data:
            return
        fav = favorites.toggle(self.data["word"])
        self.btn_fav.setChecked(fav)
        self._update_fav_btn()
        self._refresh_fav_list()

    def _update_fav_btn(self):
        self.btn_fav.setText("★ 已收藏" if self.btn_fav.isChecked() else "☆ 收藏")

    def _refresh_fav_list(self):
        self.fav_list.clear()
        for w in favorites.all():
            self.fav_list.addItem(QListWidgetItem(w))

    def _on_fav_item(self, item):
        self.input.setText(item.text())
        self.on_search()

    # ---------------- 播放 ----------------
    def on_play_word(self):
        if not self.data or not self.data["audio"].get("word"):
            self._status_error("暂无该词音频，请重新查询")
            return
        self._play(self.data["audio"]["word"], "word")

    def on_play_example(self):
        if not self.data:
            return
        if not self.data["audio"].get("example"):
            self._status_info("例句音频仍在加载，请稍候…")
            return
        self._play(self.data["audio"]["example"], "example")

    def on_play_segment(self, index):
        """点击某个音节：只播放该段时间窗。"""
        if not self.data or not self.data["audio"].get("word"):
            return
        seg = self.data["segments"][index]
        self._play(self.data["audio"]["word"], "word")
        # 媒体加载完成后再定位（直接 setPosition 会被后端忽略）
        self._pending_pos = seg["start_ms"]
        self._seg_start = seg["end_ms"]

    def _play(self, path, mode):
        self._stop()
        if not path or not os.path.exists(path):
            self._status_error("音频文件缺失，请重新查询该词")
            return
        self._mode = mode
        self.audio_out.setVolume(1.0)
        self.player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
        self.player.play()
        if self.data:
            self._status_info(f"🔊 播放中：{self.data['word']}")

    def _stop(self):
        self._seg_start = None
        self._pending_pos = None
        self.player.stop()
        self.seg_row.reset()
        self.example_words.reset()

    def _on_player_error(self, error, msg=""):
        self._status_error(f"播放出错：{msg or error}（可尝试重启程序）")

    def _on_media_status(self, status):
        if status == QMediaPlayer.LoadedMedia and self._pending_pos is not None:
            pos, self._pending_pos = self._pending_pos, None
            self.player.setPosition(int(pos))

    # ---------------- 同步高亮核心 ----------------
    def _on_position(self, ms):
        # 单段试听：到达段尾即停
        if self._seg_start is not None and ms >= self._seg_start:
            self._seg_start = None
            self.player.pause()
            self.seg_row.reset()
            return

        if self._mode == "word" and self.data:
            segs = self.data["segments"]
            starts = [s["start_ms"] for s in segs]
            idx = bisect.bisect_right(starts, ms) - 1
            if 0 <= idx < len(segs) and ms <= segs[idx]["end_ms"]:
                self.seg_row.set_active(idx)
            else:
                self.seg_row.reset()
        elif self._mode == "example" and self.data:
            words = self.data.get("example_words") or []
            if not words or "start_ms" not in words[0]:
                return
            starts = [w["start_ms"] for w in words]
            idx = bisect.bisect_right(starts, ms) - 1
            if 0 <= idx < len(words) and ms <= words[idx]["end_ms"] + 200:
                self.example_words.set_active(idx)
            else:
                self.example_words.reset()

    def _on_state(self, state):
        if state == QMediaPlayer.StoppedState:
            self.seg_row.reset()
            self.example_words.reset()
            if self.lbl_status.text().startswith("🔊"):
                self._status_info("")

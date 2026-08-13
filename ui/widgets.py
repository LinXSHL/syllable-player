# -*- coding: utf-8 -*-
"""自定义控件：音节分段标签组（拼写 + 音标两行，按段同步高亮）。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

STYLE_DEFAULT = """
QLabel { padding: 6px 10px; border-radius: 8px; background: transparent; }
"""
STYLE_IPA_ACTIVE = """
QLabel { padding: 6px 10px; border-radius: 8px;
         background: #e74c3c; color: #ffffff; font-weight: bold; }
"""
STYLE_SPELL_ACTIVE = """
QLabel { padding: 6px 10px; border-radius: 8px; background: #fdebd0; }
"""
STYLE_APPROX = """
QLabel { padding: 6px 10px; border-radius: 8px; background: #fff3cd; }
"""


class SegmentPair(QWidget):
    """一段音节：上 IPA、下拼写，纵向排列；点击发出 segClicked(index)。"""
    clicked = Signal(int)

    def __init__(self, index, spell, ipa, parent=None):
        super().__init__(parent)
        self.index = index
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        self.ipa_label = QLabel(f"/{ipa}/")
        self.ipa_label.setAlignment(Qt.AlignCenter)
        self.spell_label = QLabel(spell)
        self.spell_label.setAlignment(Qt.AlignCenter)
        f = self.spell_label.font()
        f.setPointSize(f.pointSize() + 6)
        f.setBold(True)
        self.spell_label.setFont(f)
        layout.addWidget(self.ipa_label)
        layout.addWidget(self.spell_label)
        self.reset()

    def reset(self):
        self.ipa_label.setStyleSheet(STYLE_DEFAULT)
        self.spell_label.setStyleSheet(STYLE_DEFAULT)

    def set_active(self, on):
        if on:
            self.ipa_label.setStyleSheet(STYLE_IPA_ACTIVE)      # 当前音标：红底
            self.spell_label.setStyleSheet(STYLE_SPELL_ACTIVE)  # 当前拼写：浅底
        else:
            self.reset()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)


class SegmentRow(QWidget):
    """一行音节：多个 SegmentPair 横向排列，段间加分隔竖线。"""
    segClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.addStretch(1)
        self.pairs = []

    def set_segments(self, segments):
        # 清空旧内容
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.pairs = []
        self._layout.addStretch(1)
        for seg in segments:
            pair = SegmentPair(seg["i"], seg["spell"], seg["ipa"])
            pair.clicked.connect(self.segClicked.emit)
            self._layout.addWidget(pair)
            self.pairs.append(pair)
            if seg["i"] < len(segments) - 1:
                sep = QLabel("｜")
                sep.setStyleSheet("color:#bbb; font-size:20px;")
                self._layout.addWidget(sep)
        self._layout.addStretch(1)

    def set_active(self, index):
        for p in self.pairs:
            p.set_active(p.index == index)

    def reset(self):
        for p in self.pairs:
            p.reset()


class WordHighlightLabel(QWidget):
    """例句逐词高亮控件：把例句按词渲染成一串 QLabel，按时间窗高亮当前词。"""
    STYLE_WORD = "QLabel { padding: 2px 3px; border-radius: 4px; }"
    STYLE_WORD_ACTIVE = ("QLabel { padding: 2px 3px; border-radius: 4px;"
                         " background: #fdebd0; font-weight: bold; }")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch(1)
        self.labels = []

    def set_words(self, words):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.labels = []
        self._layout.addStretch(1)
        for w in words:
            lb = QLabel(w["text"])
            lb.setStyleSheet(self.STYLE_WORD)
            f = lb.font()
            f.setPointSize(f.pointSize() + 2)
            lb.setFont(f)
            self._layout.addWidget(lb)
            self.labels.append(lb)
        self._layout.addStretch(1)

    def set_active(self, index):
        for i, lb in enumerate(self.labels):
            lb.setStyleSheet(self.STYLE_WORD_ACTIVE if i == index else self.STYLE_WORD)

    def reset(self):
        self.set_active(-1)

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from core.models import WordLesson


class PronunciationDisplay(QWidget):
    chunk_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._word_labels: list[QLabel] = []
        self._ipa_buttons: list[QToolButton] = []
        self._active: int | None = None
        self._word_length = 1
        self._ipa_length = 1

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(22)
        self.word_row = QHBoxLayout()
        self.word_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.word_row.setSpacing(0)
        self.ipa_row = QHBoxLayout()
        self.ipa_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ipa_row.setSpacing(10)
        root.addLayout(self.word_row)
        root.addLayout(self.ipa_row)

    @staticmethod
    def _clear(layout: QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def set_lesson(self, lesson: WordLesson) -> None:
        self._clear(self.word_row)
        self._clear(self.ipa_row)
        self._word_labels.clear()
        self._ipa_buttons.clear()
        graphemes = [chunk.grapheme for chunk in lesson.chunks] or [lesson.word]
        self._word_length = max(1, sum(len(value) for value in graphemes))
        self._ipa_length = max(1, sum(len(chunk.ipa) + 2 for chunk in lesson.chunks))
        for grapheme in graphemes:
            label = QLabel(grapheme)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._word_labels.append(label)
            self.word_row.addWidget(label)
        for chunk in lesson.chunks:
            button = QToolButton()
            button.setText(f"/{chunk.ipa}/")
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip("单独播放这个真实切片")
            button.clicked.connect(lambda checked=False, i=chunk.index: self.chunk_clicked.emit(i))
            self._ipa_buttons.append(button)
            self.ipa_row.addWidget(button)
        if not lesson.chunks and lesson.display_ipa:
            full = QLabel(lesson.display_ipa)
            full.setObjectName("fallbackIpa")
            full.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.ipa_row.addWidget(full)
        self.set_active(None)
        self._update_fonts()

    def set_active(self, index: int | None) -> None:
        self._active = index
        for i, label in enumerate(self._word_labels):
            active = i == index
            label.setStyleSheet(
                "color: #17375e; background: #ffe2ce; border-radius: 10px; padding: 5px 3px;"
                if active else
                "color: #17375e; background: transparent; padding: 5px 3px;"
            )
        for i, button in enumerate(self._ipa_buttons):
            active = i == index
            button.setStyleSheet(
                "QToolButton { color: %s; background: #f3ead7; border: none; "
                "border-radius: 12px; padding: 8px 12px; } "
                "QToolButton:hover { background: #eadfc7; }" % ("#e43d30" if active else "#151515")
            )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._update_fonts()

    def _update_fonts(self) -> None:
        word_size = max(16, min(68, int(self.width() / (self._word_length * .72))))
        ipa_size = max(15, min(30, int(self.width() / (self._ipa_length * 1.05))))
        for label in self._word_labels:
            label.setFont(QFont("Segoe UI", word_size, QFont.Weight.DemiBold))
            label.adjustSize()
        for button in self._ipa_buttons:
            button.setFont(QFont("Segoe UI", ipa_size, QFont.Weight.Medium))
            button.adjustSize()

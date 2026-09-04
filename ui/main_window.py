from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.favorites import FavoritesStore
from core.models import WordLesson
from core.pipeline import LessonBuilder
from .playback import PlaybackController
from .widgets import PronunciationDisplay


class LessonWorker(QObject):
    progress = Signal(int, str)
    succeeded = Signal(int, object)
    failed = Signal(int, str)
    finished = Signal()

    def __init__(self, request_id: int, word: str) -> None:
        super().__init__()
        self.request_id = request_id
        self.word = word

    @Slot()
    def run(self) -> None:
        try:
            builder = LessonBuilder()
            lesson = builder.build(
                self.word,
                lambda message: self.progress.emit(self.request_id, message),
            )
            self.succeeded.emit(self.request_id, lesson)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("英文分段发音学习")
        self.resize(920, 780)
        self.setMinimumSize(640, 620)
        self._request_id = 0
        self._lesson: WordLesson | None = None
        self._threads: list[QThread] = []
        self._workers: list[LessonWorker] = []
        self._favorites = FavoritesStore()
        self._playback = PlaybackController(self)
        self._playback.highlight_changed.connect(self._set_highlight)
        self._playback.playback_error.connect(self._show_error)

        self.setStyleSheet("QMainWindow { background: #dff4ff; }")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #dff4ff; border: none; }")
        page = QWidget()
        page.setStyleSheet("background: #dff4ff;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(34, 30, 34, 30)
        outer.addStretch(1)

        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.card.setStyleSheet(
            "QFrame#card { background: white; border-radius: 25px; }"
            "QLineEdit { border: 2px solid #c9dce8; border-radius: 13px; padding: 11px 14px; "
            "font-size: 18px; background: #fbfdff; }"
            "QLineEdit:focus { border-color: #3688c8; }"
            "QPushButton { border: none; border-radius: 13px; padding: 11px 17px; "
            "font-size: 16px; font-weight: 600; background: #216aa5; color: white; }"
            "QPushButton:hover { background: #185b91; }"
            "QPushButton:disabled { background: #b8c6d0; }"
        )
        content = QVBoxLayout(self.card)
        content.setContentsMargins(42, 38, 42, 40)
        content.setSpacing(19)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("输入英文单词，例如 everyone")
        self.search.returnPressed.connect(self.generate)
        self.generate_button = QPushButton("分析发音")
        self.generate_button.clicked.connect(self.generate)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.generate_button)
        content.addLayout(search_row)

        self.status = QLabel("输入单词后，将从完整录音中提取真实发音片段。")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: #557083; font-size: 14px;")
        content.addWidget(self.status)

        self.display = PronunciationDisplay()
        self.display.chunk_clicked.connect(self.play_chunk)
        content.addWidget(self.display)

        self.full_ipa = QLabel("")
        self.full_ipa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.full_ipa.setFont(QFont("Segoe UI", 22))
        self.full_ipa.setStyleSheet("color: #394956;")
        content.addWidget(self.full_ipa)

        self.definition = QLabel("")
        self.definition.setWordWrap(True)
        self.definition.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.definition.setStyleSheet("font-size: 17px; color: #253746;")
        content.addWidget(self.definition)
        self.example = QLabel("")
        self.example.setWordWrap(True)
        self.example.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.example.setStyleSheet("font-size: 15px; color: #62717c; font-style: italic;")
        content.addWidget(self.example)

        controls = QHBoxLayout()
        controls.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.play_sequence = QPushButton("▶  分段 + 整词")
        self.play_sequence.clicked.connect(self.play_lesson)
        self.play_full = QPushButton("完整词")
        self.play_full.clicked.connect(self.play_full_word)
        self.favorite = QPushButton("☆ 收藏")
        self.favorite.clicked.connect(self.toggle_favorite)
        controls.addWidget(self.play_sequence)
        controls.addWidget(self.play_full)
        controls.addWidget(self.favorite)
        content.addLayout(controls)

        self.details = QLabel("")
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details.setStyleSheet("font-size: 12px; color: #8a969e;")
        content.addWidget(self.details)

        outer.addWidget(self.card)
        outer.addStretch(1)
        scroll.setWidget(page)
        self.setCentralWidget(scroll)
        self._set_controls(False)
        QTimer.singleShot(80, self._load_example)

    def _load_example(self) -> None:
        self.search.setText("everyone")
        self.generate()

    @Slot()
    def generate(self) -> None:
        value = self.search.text().strip()
        if not value:
            self._show_error("请先输入一个英文单词。")
            return
        self._request_id += 1
        request_id = self._request_id
        self._playback.stop()
        self.generate_button.setEnabled(False)
        self.status.setStyleSheet("color: #376984; font-size: 14px;")
        self.status.setText("正在准备完整单词录音……")
        self._set_controls(False)

        thread = QThread(self)
        worker = LessonWorker(request_id, value)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.succeeded.connect(self._on_lesson)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread: self._forget_thread(t))
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda w=worker: self._forget_worker(w))
        thread.start()

    def _forget_thread(self, thread: QThread) -> None:
        if thread in self._threads:
            self._threads.remove(thread)

    def _forget_worker(self, worker: LessonWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    @Slot(int, str)
    def _on_progress(self, request_id: int, message: str) -> None:
        if request_id == self._request_id:
            self.status.setText(message)

    @Slot(int, object)
    def _on_lesson(self, request_id: int, lesson: WordLesson) -> None:
        if request_id != self._request_id:
            return
        self.generate_button.setEnabled(True)
        self._lesson = lesson
        self.display.set_lesson(lesson)
        self.full_ipa.setText(lesson.display_ipa)
        self.definition.setText(lesson.definition or "释义暂不可用；发音分析不受影响。")
        self.example.setText(f"“{lesson.example}”" if lesson.example else "")
        self.details.setText(
            f"发音：{lesson.pronunciation_source}　·　时间戳：{lesson.alignment_source}"
            if lesson.chunks else ""
        )
        if lesson.warning:
            self.status.setStyleSheet("color: #a15a16; font-size: 14px;")
            self.status.setText(lesson.warning)
        else:
            mapping = "　 ".join(f"{c.grapheme} ↔ /{c.ipa}/" for c in lesson.chunks)
            self.status.setStyleSheet("color: #24704c; font-size: 14px;")
            self.status.setText(mapping)
        self._set_controls(True)
        active = self._favorites.contains(lesson.word)
        self.favorite.setText("★ 已收藏" if active else "☆ 收藏")

    @Slot(int, str)
    def _on_failure(self, request_id: int, message: str) -> None:
        if request_id != self._request_id:
            return
        self.generate_button.setEnabled(True)
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self.status.setStyleSheet("color: #b23b34; font-size: 14px;")
        self.status.setText(message)

    def _set_controls(self, have_lesson: bool) -> None:
        has_chunks = have_lesson and bool(self._lesson and self._lesson.chunks)
        has_full = have_lesson and bool(
            self._lesson and self._lesson.full_audio_path and Path(self._lesson.full_audio_path).is_file()
        )
        self.play_sequence.setEnabled(has_chunks)
        self.play_full.setEnabled(has_full)
        self.favorite.setEnabled(have_lesson and self._lesson is not None)

    @Slot(object)
    def _set_highlight(self, index: int | None) -> None:
        self.display.set_active(index)

    @Slot()
    def play_lesson(self) -> None:
        if self._lesson and self._lesson.chunks:
            self._playback.play_lesson(self._lesson)

    @Slot()
    def play_full_word(self) -> None:
        if self._lesson:
            self._playback.play_full_word(self._lesson)

    @Slot(int)
    def play_chunk(self, index: int) -> None:
        if self._lesson:
            self._playback.play_chunk(self._lesson, index)

    @Slot()
    def toggle_favorite(self) -> None:
        if not self._lesson:
            return
        active = self._favorites.toggle(self._lesson.word)
        self.favorite.setText("★ 已收藏" if active else "☆ 收藏")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._playback.stop()
        for thread in self._threads:
            thread.requestInterruption()
            thread.quit()
        super().closeEvent(event)


def run_application() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Syllable Player")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()

from __future__ import annotations

import wave
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices

from core.audio import active_chunk_at
from core.models import TimelineEvent, WordLesson


class PlaybackController(QObject):
    highlight_changed = Signal(object)
    playback_finished = Signal()
    playback_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sink: QAudioSink | None = None
        self._buffer: QBuffer | None = None
        self._timeline: Sequence[TimelineEvent] = ()
        self._static_highlight: int | None = None
        self._last_highlight: int | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._synchronize)

    def stop(self) -> None:
        self._timer.stop()
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        if self._buffer is not None:
            self._buffer.close()
            self._buffer.deleteLater()
        self._sink = None
        self._buffer = None
        self._timeline = ()
        self._static_highlight = None
        self._set_highlight(None)

    def play_lesson(self, lesson: WordLesson) -> None:
        self._play(Path(lesson.lesson_audio_path), lesson.timeline)

    def play_full_word(self, lesson: WordLesson) -> None:
        self._play(Path(lesson.full_audio_path), ())

    def play_chunk(self, lesson: WordLesson, index: int) -> None:
        if 0 <= index < len(lesson.chunks):
            self._play(Path(lesson.chunks[index].clip_path), (), static_highlight=index)

    def _play(
        self,
        path: Path,
        timeline: Sequence[TimelineEvent],
        *,
        static_highlight: int | None = None,
    ) -> None:
        self.stop()
        try:
            with wave.open(str(path), "rb") as handle:
                channels = handle.getnchannels()
                sample_rate = handle.getframerate()
                sample_width = handle.getsampwidth()
                frames = handle.readframes(handle.getnframes())
            if sample_width != 2:
                raise ValueError("音频不是 16-bit PCM")
            fmt = QAudioFormat()
            fmt.setSampleRate(sample_rate)
            fmt.setChannelCount(channels)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            device = QMediaDevices.defaultAudioOutput()
            if device.isNull():
                raise RuntimeError("没有可用的声音输出设备")
            if not device.isFormatSupported(fmt):
                raise RuntimeError("声音设备不支持生成音频的格式")
            self._buffer = QBuffer(self)
            self._buffer.setData(QByteArray(frames))
            self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            self._sink = QAudioSink(device, fmt, self)
            self._sink.stateChanged.connect(self._on_state_changed)
            self._timeline = timeline
            self._static_highlight = static_highlight
            self._last_highlight = None
            self._sink.start(self._buffer)
            self._timer.start()
            self._synchronize()
        except Exception as exc:
            self.stop()
            self.playback_error.emit(f"无法播放声音：{exc}")

    def _synchronize(self) -> None:
        if self._sink is None:
            return
        elapsed_ms = self._sink.processedUSecs() / 1000.0
        index = self._static_highlight
        if index is None:
            index = active_chunk_at(elapsed_ms, self._timeline)
        self._set_highlight(index)

    def _set_highlight(self, index: int | None) -> None:
        if index != self._last_highlight:
            self._last_highlight = index
            self.highlight_changed.emit(index)

    def _on_state_changed(self, state: QAudio.State) -> None:
        if state == QAudio.State.IdleState:
            self._timer.stop()
            self._set_highlight(None)
            self.playback_finished.emit()
        elif state == QAudio.State.StoppedState and self._sink and self._sink.error() != QAudio.Error.NoError:
            self._timer.stop()
            self._set_highlight(None)
            self.playback_error.emit("播放设备报告了声音错误。")

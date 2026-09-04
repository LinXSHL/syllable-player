from PySide6.QtCore import QCoreApplication

from ui.playback import PlaybackController


def test_highlight_clock_polling_is_within_fifty_milliseconds() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = PlaybackController()
    assert controller._timer.interval() <= 50
    controller.stop()
    assert app is not None


def test_individual_clip_keeps_its_static_highlight() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    controller = PlaybackController()

    class Sink:
        @staticmethod
        def processedUSecs() -> int:
            return 250_000

    observed = []
    controller.highlight_changed.connect(observed.append)
    controller._sink = Sink()
    controller._static_highlight = 2
    controller._synchronize()
    assert observed == [2]
    controller._sink = None
    controller.stop()
    assert app is not None

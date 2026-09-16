from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QMessageBox


def pixmap(image: Image.Image):
    image = image.convert("RGB")
    data = image.tobytes()
    return QPixmap.fromImage(
        QImage(data, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888).copy()
    )


class TaskSignals(QObject):
    done = Signal(object)
    error = Signal(str)
    finished = Signal()


class Task(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    def run(self):
        try:
            self.signals.done.emit(self.function())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


def error(parent, message):
    QMessageBox.warning(parent, "Action could not finish", str(message))

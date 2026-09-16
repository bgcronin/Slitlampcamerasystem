from pathlib import Path

from PySide6.QtCore import QObject, Signal


class Camera(QObject):
    frame = Signal(object)  # Detached PIL RGB image
    captured = Signal(object, object, object)  # immutable ticket, path, metadata
    failed = Signal(object, str)  # ticket or None, message
    status = Signal(str)
    recording_changed = Signal(bool)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info
        self.recording = False
        self.connected = False
        self.latest = None

    def connect_camera(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def capture(self, ticket):
        raise NotImplementedError

    def start_video(self, ticket):
        raise NotImplementedError

    def stop_video(self):
        raise NotImplementedError

    def settings(self) -> dict:
        return {}

    def apply_settings(self, values: dict) -> dict:
        return {key: "Unsupported by this camera interface" for key in values}

    def staging_path(self, ticket, suffix) -> Path:
        return ticket.staging / (ticket.id + suffix)

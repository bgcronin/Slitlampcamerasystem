import math
import time

from PIL import Image, ImageDraw
from PySide6.QtCore import QTimer

from .base import Camera
from .recorder import StreamRecorder
from ..models import CameraInfo


class SimulatedCamera(Camera):
    def __init__(self, parent=None):
        super().__init__(
            CameraInfo(
                "simulator",
                "Demonstration camera — simulated",
                "simulator",
                video=True,
                live=True,
                verification="Simulated",
                detail="Generated test pattern, not a patient image.",
            ),
            parent,
        )
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.values = {"brightness": 1.0}
        self.recorder = None
        self.ticket = None

    def connect_camera(self):
        self.connected = True
        self.timer.start(80)
        self.tick()
        self.status.emit("SIMULATED CAMERA · generated test pattern")

    def tick(self):
        image = Image.new("RGB", (1280, 960), (14, 22, 33))
        draw = ImageDraw.Draw(image)
        for radius in range(330, 65, -5):
            phase = radius / 30 + time.monotonic() / 4
            draw.ellipse(
                (640 - radius, 480 - radius, 640 + radius, 480 + radius),
                fill=(int(45 + 25 * math.sin(phase)), int(100 + 50 * math.cos(phase)), 120),
            )
        draw.ellipse((555, 395, 725, 565), fill=(4, 8, 14))
        draw.rectangle((30, 25, 800, 90), fill=(26, 42, 60))
        draw.text((48, 45), "SIMULATED TEST PATTERN - NOT A PATIENT IMAGE", fill="white", font_size=25)
        draw.text((45, 900), time.strftime("%H:%M:%S"), fill="white", font_size=25)
        self.latest = image
        self.frame.emit(image)
        if self.recorder:
            self.recorder.offer(image)

    def capture(self, ticket):
        if not self.connected or self.latest is None:
            self.failed.emit(ticket, "Connect the camera first.")
            return
        path = self.staging_path(ticket, ".png")
        self.latest.save(path)
        self.captured.emit(ticket, path, {"simulated": True, "capture_source": "generated pattern"})

    def start_video(self, ticket):
        if self.latest is None:
            raise ValueError("Wait for a preview frame first.")
        self.ticket = ticket
        self.recorder = StreamRecorder(self.staging_path(ticket, ".mp4"), self.latest)
        self.recording = True
        self.recording_changed.emit(True)

    def stop_video(self):
        if not self.recorder:
            return
        recorder, self.recorder = self.recorder, None
        try:
            path = recorder.finish()
            self.captured.emit(self.ticket, path, {"simulated": True, "capture_source": "generated video"})
        except Exception as exc:
            self.failed.emit(self.ticket, str(exc))
        finally:
            self.recording = False
            self.recording_changed.emit(False)

    def settings(self):
        return self.values.copy()

    def apply_settings(self, values):
        self.values.update(values)
        return {key: "Applied (simulator)" for key in values}

    def close(self):
        self.stop_video()
        self.timer.stop()
        self.connected = False

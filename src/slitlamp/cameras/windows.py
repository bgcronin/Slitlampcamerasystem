"""Qt's native camera backend, for devices exposed by installed Windows drivers.

This is NOT a proprietary Mizar SDK. A Mizar must appear in the device list to
use this backend; otherwise use Phoenix export or a vendor-provided integration.
"""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtMultimedia import (
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
    QImageCapture,
    QMediaRecorder,
    QMediaFormat,
    QVideoSink,
)

from .base import Camera
from ..models import CameraInfo


def available_devices():
    return QMediaDevices.videoInputs()


class WindowsCamera(Camera):
    def __init__(self, device, parent=None):
        super().__init__(
            CameraInfo(
                bytes(device.id()).hex(),
                device.description(),
                "windows",
                video=True,
                live=True,
                detail="Resolution and controls depend on the installed device driver.",
            ),
            parent,
        )
        self.device = device
        self.camera = QCamera(device, self)
        self.session = QMediaCaptureSession(self)
        self.session.setCamera(self.camera)
        self.sink = QVideoSink(self)
        self.session.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.on_frame)
        self.stills = QImageCapture(self)
        self.stills.setFileFormat(QImageCapture.FileFormat.JPEG)
        self.stills.setQuality(QImageCapture.Quality.VeryHighQuality)
        self.session.setImageCapture(self.stills)
        self.stills.imageSaved.connect(self.on_saved)
        self.stills.errorOccurred.connect(self.on_image_error)
        self.recorder = QMediaRecorder(self)
        self.session.setRecorder(self.recorder)
        self.recorder.setQuality(QMediaRecorder.Quality.VeryHighQuality)
        media_format = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
        media_format.setVideoCodec(QMediaFormat.VideoCodec.H264)
        self.recorder.setMediaFormat(media_format)
        self.recorder.recorderStateChanged.connect(self.on_recording)
        self.recorder.errorOccurred.connect(self.on_video_error)
        self.camera.errorOccurred.connect(self.on_camera_error)
        self.camera.activeChanged.connect(self.on_active)
        self.pending = {}
        self.video_ticket = None
        self.video_error = False

    def connect_camera(self):
        formats = self.device.videoFormats()
        if formats:
            best = max(
                formats, key=lambda f: (f.resolution().width() * f.resolution().height(), f.maxFrameRate())
            )
            self.camera.setCameraFormat(best)
        self.camera.start()

    def on_active(self, active):
        self.connected = active
        self.status.emit(f"{self.info.label} · {'connected' if active else 'disconnected'}")

    def on_frame(self, frame):
        image = frame.toImage()
        if image.isNull():
            return
        from PySide6.QtGui import QImage

        image = image.convertToFormat(QImage.Format.Format_RGB888)
        pil = Image.frombytes(
            "RGB",
            (image.width(), image.height()),
            bytes(image.constBits()),
            "raw",
            "RGB",
            image.bytesPerLine(),
        )
        self.latest = pil
        self.frame.emit(pil)

    def capture(self, ticket):
        if not self.stills.isReadyForCapture():
            self.failed.emit(
                ticket, "Camera is not ready for a still. Wait for live view or check the driver."
            )
            return
        ident = self.stills.captureToFile(str(self.staging_path(ticket, ".jpg")))
        if ident < 0:
            self.failed.emit(ticket, "The driver rejected still capture.")
        else:
            self.pending[ident] = ticket
            QTimer.singleShot(30000, lambda: self.expire_capture(ident))

    def expire_capture(self, ident):
        ticket = self.pending.pop(ident, None)
        if ticket:
            self.failed.emit(ticket, "Still capture timed out. Late files remain in staging for review.")

    def on_camera_error(self, code, message):
        pending = list(self.pending.values())
        self.pending.clear()
        for ticket in pending:
            self.failed.emit(ticket, message)
        if self.video_ticket:
            self.on_video_error(code, message)
        elif not pending:
            self.failed.emit(None, message)

    def on_saved(self, ident, path):
        ticket = self.pending.pop(ident, None)
        if ticket:
            self.captured.emit(
                ticket, Path(path), {"capture_source": "Windows driver still capture", "device": self.info.id}
            )

    def on_image_error(self, ident, code, message):
        self.failed.emit(self.pending.pop(ident, None), message)

    def start_video(self, ticket):
        if not self.connected:
            raise ValueError("Connect the camera before recording.")
        self.video_ticket = ticket
        self.video_error = False
        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(self.staging_path(ticket, ".mp4"))))
        self.recording = True  # Includes encoder startup; identity is locked immediately.
        self.recording_changed.emit(True)
        self.recorder.record()
        QTimer.singleShot(15000, self.check_recording_started)

    def check_recording_started(self):
        if self.video_ticket and self.recorder.recorderState() != QMediaRecorder.RecorderState.RecordingState:
            self.recorder.stop()
            self.on_video_error(
                None, "The driver did not start recording. Check its supported video formats."
            )

    def stop_video(self):
        self.recorder.stop()

    def on_recording(self, state):
        if state == QMediaRecorder.RecorderState.StoppedState and self.video_ticket:
            ticket, self.video_ticket = self.video_ticket, None
            path = Path(self.recorder.actualLocation().toLocalFile())
            self.recording = False
            self.recording_changed.emit(False)
            if not self.video_error:
                self.captured.emit(
                    ticket, path, {"capture_source": "Windows driver video", "device": self.info.id}
                )

    def on_video_error(self, code, message):
        self.video_error = True
        self.failed.emit(self.video_ticket, message)
        self.video_ticket = None
        self.recording = False
        self.recording_changed.emit(False)

    def settings(self):
        values = {}
        features = self.camera.supportedFeatures()
        if features & QCamera.Feature.IsoSensitivity:
            values["iso"] = self.camera.isoSensitivity()
        if features & QCamera.Feature.ExposureTime:
            values["exposure_seconds"] = self.camera.exposureTime()
        if features & QCamera.Feature.ColorTemperature:
            values["colour_temperature"] = self.camera.colorTemperature()
        if features & QCamera.Feature.ExposureCompensation:
            values["exposure_compensation"] = self.camera.exposureCompensation()
        fmt = self.camera.cameraFormat()
        values["width"] = fmt.resolution().width()
        values["height"] = fmt.resolution().height()
        return values

    def apply_settings(self, values):
        results = {}
        current = self.settings()
        setters = {
            "iso": self.camera.setManualIsoSensitivity,
            "exposure_seconds": self.camera.setManualExposureTime,
            "colour_temperature": self.camera.setColorTemperature,
            "exposure_compensation": self.camera.setExposureCompensation,
        }
        for key, value in values.items():
            if key in ("width", "height"):
                results[key] = (
                    "Current format matches"
                    if current.get(key) == value
                    else "Not applied: select a supported format"
                )
            elif key in current and key in setters:
                setters[key](int(value) if key in ("iso", "colour_temperature") else float(value))
                results[key] = "Requested; confirm live view and camera readback"
            else:
                results[key] = "Unsupported by installed driver"
        return results

    def close(self):
        if self.recording:
            self.stop_video()
        self.camera.stop()
        for ticket in self.pending.values():
            self.failed.emit(ticket, "Camera closed before capture completed.")
        self.pending.clear()
        self.connected = False

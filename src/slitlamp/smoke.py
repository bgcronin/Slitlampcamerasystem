"""Exercise the installed executable using an isolated, disposable demo archive."""

import json
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .catalog import Catalog
from .imaging import prepare_export, video_frame
from .pacs import build_dicom
from .ui.main import MainWindow


def run(report: Path) -> int:
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    report.parent.mkdir(parents=True, exist_ok=True)
    result = {"success": False, "error": "Package check did not complete."}
    with tempfile.TemporaryDirectory(prefix="slitlamp-package-check-") as folder:
        catalog = Catalog(Path(folder))
        window = MainWindow(catalog, demo=True)
        window.show()
        window.timer.stop()
        phase = "capture"
        started = time.monotonic()
        recording_started = 0.0
        timer = QTimer(window)

        def finish(success, message=""):
            timer.stop()
            result.update(success=success, error=message)
            report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            if not window.pending and not window.tasks:
                window.close()
            app.exit(0 if success else 1)

        def tick():
            nonlocal phase, recording_started
            try:
                if time.monotonic() - started > 40:
                    raise TimeoutError("Timed out waiting for packaged capture/video workflow.")
                if phase == "capture":
                    phase = "image"
                    window.capture()
                elif phase == "image" and not window.pending and not window.tasks:
                    images = catalog.search(kind="image")
                    if len(images) != 1:
                        raise RuntimeError("Packaged still capture did not save one image.")
                    exported = prepare_export(catalog, images[0]["id"], "edited")
                    if not exported.is_file() or not build_dicom(catalog, images[0]["id"]).PixelData:
                        raise RuntimeError("Packaged image export failed.")
                    window.show_live()
                    window.toggle_video()
                    recording_started = time.monotonic()
                    phase = "recording"
                elif phase == "recording" and time.monotonic() - recording_started >= 1:
                    phase = "video"
                    window.toggle_video()
                elif phase == "video" and not window.pending and not window.tasks:
                    videos = catalog.search(kind="video")
                    if len(videos) != 1:
                        raise RuntimeError("Packaged video capture did not save one video.")
                    frame = video_frame(catalog.path(videos[0]["path"]))
                    if frame.width != 1280 or frame.height != 960:
                        raise RuntimeError("Packaged video decoding returned an unexpected frame.")
                    result["checks"] = ["desktop launch", "still capture", "JPEG export", "DICOM creation",
                                        "MP4 recording", "video frame decoding"]
                    finish(True)
            except Exception as exc:
                finish(False, str(exc))

        timer.timeout.connect(tick)
        timer.start(100)
        exit_code = app.exec()
        if not result["success"]:
            report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return exit_code if result["success"] else 1

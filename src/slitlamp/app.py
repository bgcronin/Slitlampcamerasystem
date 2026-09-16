import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog

from .catalog import Catalog
from .ui.main import MainWindow
from .ui.theme import STYLE


def main(argv=None):
    parser = argparse.ArgumentParser(description="Slitlamp Studio — Windows slit lamp imaging")
    parser.add_argument("--data-dir", type=Path, help="Archive folder; defaults to Pictures/Slit Lamp Photos")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Fictional patients and simulated camera in a separate demo archive",
    )
    parser.add_argument(
        "--choose-archive", action="store_true", help="Choose a different local archive before starting"
    )
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Slitlamp Studio")
    app.setOrganizationName("Slitlamp Studio")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    pictures = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation))
    root = args.data_dir or pictures / ("Slitlamp Studio Demo" if args.demo else "Slit Lamp Photos")
    if args.choose_archive:
        chosen = QFileDialog.getExistingDirectory(None, "Select the local archive folder", str(root))
        if not chosen:
            return 0
        root = Path(chosen)
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root / ".slitlamp.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.critical(
            None,
            "Archive already open",
            "Another Slitlamp Studio instance is using this archive. Close it before opening the same archive again.",
        )
        return 1
    try:
        catalog = Catalog(root)
        if args.demo and catalog.get_setting("archive_type", None) not in (None, "demo"):
            raise ValueError("This is a live archive. Use a separate empty directory for demonstration mode.")
        if (
            args.demo
            and catalog.query("SELECT id FROM patients LIMIT 1")
            and catalog.get_setting("archive_type", None) != "demo"
        ):
            raise ValueError("Demo mode cannot be opened over an existing patient archive.")
        catalog.set_setting(
            "archive_type", "demo" if args.demo else catalog.get_setting("archive_type", "live")
        )
        window = MainWindow(catalog, args.demo)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "Could not open archive", str(exc))
        return 1
    finally:
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, QSize, QDate, QTimer, QThreadPool, QUrl, QMimeData
from PySide6.QtGui import QAction, QDrag, QIcon, QKeySequence, QShortcut, QDesktopServices, QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QComboBox,
    QDateEdit,
    QSplitter,
    QFrame,
    QStackedWidget,
    QAbstractItemView,
    QFileDialog,
    QMessageBox,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QInputDialog,
    QCheckBox,
    QSlider,
    QGraphicsView,
    QGraphicsScene,
    QScrollArea,
)

from .. import __version__
from ..catalog import Catalog, digest
from ..imaging import load_image, render, video_frame, prepare_export, copy_export, VIDEO_EXTENSIONS
from ..inbox import FolderInbox
from ..models import WorklistRow, now, uid
from ..cameras.simulator import SimulatedCamera
from ..cameras.windows import WindowsCamera, available_devices
from ..cameras.canon import CanonCamera
from .common import Task, pixmap, error
from .dialogs import WorklistDialog, PatientDialog, PresetDialog, SettingsDialog
from .editor import EditorDialog


class ImageView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = self.scene().addPixmap(QPixmap())
        self.setStyleSheet("background: #070d16; border: 1px solid #25334a; border-radius: 8px;")
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.auto_fit = True

    def display(self, image, fit=False):
        self.item.setPixmap(pixmap(image))
        self.scene().setSceneRect(self.item.boundingRect())
        if fit or self.auto_fit:
            self.fit_image()

    def fit_image(self):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.auto_fit = True

    def wheelEvent(self, event):
        self.auto_fit = False
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit:
            self.fit_image()


class Gallery(QListWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(130, 92))
        self.setGridSize(QSize(155, 145))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setMinimumHeight(172)
        self.setWordWrap(True)

    def startDrag(self, supportedActions):
        ids = self.owner.selected_ids()
        if not ids:
            return
        try:
            # Generated copies survive drag completion and app exit; cleanup is explicit.
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            paths = [
                prepare_export(
                    self.owner.catalog,
                    mid,
                    self.owner.export_mode.currentData(),
                    self.owner.export_format.currentText(),
                )
                for mid in ids
            ]
        except Exception as exc:
            error(self, exc)
            return
        finally:
            QApplication.restoreOverrideCursor()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        if self.currentItem():
            drag.setPixmap(self.currentItem().icon().pixmap(100, 75))
        drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)
        self.owner.notice("Export copies prepared. Confirm receipt in the destination application.")


def button(label, handler, primary=False):
    widget = QPushButton(label)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(handler)
    return widget


def label(text, style="muted"):
    item = QLabel(text)
    item.setObjectName(style)
    item.setWordWrap(True)
    return item


class MainWindow(QMainWindow):
    def __init__(self, catalog: Catalog, demo=False):
        super().__init__()
        self.catalog = catalog
        self.demo = demo
        self.active_session = None
        self.camera = None
        self.live = True
        self.current_media = None
        self.pending = set()
        self.deleted_batch = []
        self.tasks = set()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.inbox = FolderInbox(catalog)
        self.scan_running = self.backup_running = False
        self.last_scan = 0
        self.record_start = None
        self.setWindowTitle(f"Slitlamp Studio {__version__}" + (" · DEMO ARCHIVE" if demo else ""))
        self.resize(1520, 960)
        self.setMinimumSize(1100, 740)
        self.build_ui()
        self.build_menu()
        self.apply_shortcuts()
        self.refresh_worklist()
        self.refresh_cameras()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.notice("Local archive ready. Import a worklist, select a patient and connect a camera.")
        if demo:
            self.seed_demo()
        self.update_capture_buttons()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(12)
        header = QHBoxLayout()
        brand = label("SLITLAMP  /  STUDIO", "brand")
        brand.setWordWrap(False)
        header.addWidget(brand)
        header.addWidget(label("CAPTURE · REVIEW · ORGANISE", "eyebrow"))
        header.addStretch()
        self.storage_label = label("LOCAL ARCHIVE")
        header.addWidget(self.storage_label)
        header.addWidget(button("Settings", self.settings))
        layout.addLayout(header)
        body = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(body, 1)

        work_panel = QFrame()
        work_panel.setObjectName("panel")
        work = QVBoxLayout(work_panel)
        work.setContentsMargins(12, 16, 12, 12)
        work.addWidget(label("DAILY WORKLIST", "eyebrow"))
        self.clinic_date = QDateEdit(QDate.currentDate())
        self.clinic_date.setCalendarPopup(True)
        self.clinic_date.setDisplayFormat("ddd, dd MMM yyyy")
        self.clinic_date.dateChanged.connect(self.refresh_worklist)
        work.addWidget(self.clinic_date)
        self.patient_search = QLineEdit()
        self.patient_search.setPlaceholderText("Find name or MRN…")
        self.patient_search.textChanged.connect(self.refresh_worklist)
        work.addWidget(self.patient_search)
        self.patient_list = QListWidget()
        self.patient_list.itemDoubleClicked.connect(self.select_patient)
        work.addWidget(self.patient_list, 1)
        work.addWidget(button("Start selected patient's session", self.select_patient, True))
        patient_actions = QHBoxLayout()
        patient_actions.addWidget(button("Import list", self.import_worklist))
        patient_actions.addWidget(button("Add patient", self.add_patient))
        work.addLayout(patient_actions)
        work.addWidget(button("End session / Next patient", self.end_session))
        self.inbox_button = button("Import inbox", self.show_inbox)
        work.addWidget(self.inbox_button)
        work.addWidget(
            label("Double-click a patient to start. Patient, session and eye stay bound to every capture.")
        )
        body.addWidget(work_panel)

        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(10, 0, 10, 0)
        self.patient_title = label("Select a patient to begin", "patientTitle")
        centre_layout.addWidget(self.patient_title)
        self.patient_details = label("Name, MRN and date of birth will remain visible here.")
        centre_layout.addWidget(self.patient_details)
        viewtools = QHBoxLayout()
        self.viewer_title = label("LIVE VIEW", "eyebrow")
        viewtools.addWidget(self.viewer_title, 1)
        viewtools.addWidget(button("Live view", self.show_live))
        viewtools.addWidget(button("Fit", lambda: self.image_view.fit_image()))
        viewtools.addWidget(button("Full screen", self.full_screen))
        centre_layout.addLayout(viewtools)
        self.viewer = QStackedWidget()
        self.empty = label("Connect a camera for live view\n\nOr select an image below to review.")
        self.empty.setObjectName("preview")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_view = ImageView()
        self.video_widget = QVideoWidget()
        self.viewer.addWidget(self.empty)
        self.viewer.addWidget(self.image_view)
        self.viewer.addWidget(self.video_widget)
        self.viewer.setMinimumHeight(280)
        centre_layout.addWidget(self.viewer, 1)
        self.player = QMediaPlayer(self)
        self.player.setVideoOutput(self.video_widget)
        self.player.errorOccurred.connect(lambda code, message: self.notice("Playback: " + message))
        videobar = QHBoxLayout()
        self.play_button = button("Play / pause", self.play_pause)
        videobar.addWidget(self.play_button)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.player.durationChanged.connect(lambda length: self.seek.setRange(0, int(length)))
        self.player.positionChanged.connect(
            lambda value: self.seek.setValue(int(value)) if not self.seek.isSliderDown() else None
        )
        videobar.addWidget(self.seek, 1)
        self.frame_button = button("Save video frame", self.extract_frame)
        videobar.addWidget(self.frame_button)
        centre_layout.addLayout(videobar)
        filters = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItems(["Current session", "Patient history", "All patients", "Deleted items"])
        self.scope.currentIndexChanged.connect(self.refresh_gallery)
        filters.addWidget(self.scope)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search names, MRNs, tags, notes…")
        self.search.textChanged.connect(self.refresh_gallery)
        filters.addWidget(self.search, 1)
        self.eye_filter = QComboBox()
        for name, value in [("Both eyes", ""), ("Right", "R"), ("Left", "L")]:
            self.eye_filter.addItem(name, value)
        self.eye_filter.currentIndexChanged.connect(self.refresh_gallery)
        filters.addWidget(self.eye_filter)
        self.kind_filter = QComboBox()
        for name, value in [("All media", ""), ("Photos", "image"), ("Videos", "video")]:
            self.kind_filter.addItem(name, value)
        self.kind_filter.currentIndexChanged.connect(self.refresh_gallery)
        filters.addWidget(self.kind_filter)
        centre_layout.addLayout(filters)
        dates = QHBoxLayout()
        self.limit_dates = QCheckBox("Date range")
        self.limit_dates.toggled.connect(self.refresh_gallery)
        dates.addWidget(self.limit_dates)
        self.date_from, self.date_to = QDateEdit(QDate.currentDate()), QDateEdit(QDate.currentDate())
        for field in (self.date_from, self.date_to):
            field.setCalendarPopup(True)
            field.dateChanged.connect(self.refresh_gallery)
            dates.addWidget(field)
        self.gallery_count = label("0 items")
        dates.addWidget(self.gallery_count, 1)
        centre_layout.addLayout(dates)
        self.gallery = Gallery(self)
        self.gallery.itemSelectionChanged.connect(self.review_selection)
        self.gallery.itemDoubleClicked.connect(lambda item: self.edit_image())
        centre_layout.addWidget(self.gallery)
        gallery_actions = QHBoxLayout()
        gallery_actions.addWidget(button("Edit / annotate", self.edit_image))
        gallery_actions.addWidget(button("Delete selected", self.delete_selected))
        gallery_actions.addWidget(button("Undo delete", self.undo_delete))
        gallery_actions.addWidget(button("Restore", self.restore_selected))
        gallery_actions.addWidget(button("Remove permanently", self.purge_selected))
        centre_layout.addLayout(gallery_actions)
        body.addWidget(centre)

        controls_panel = QFrame()
        controls_panel.setObjectName("panel")
        controls = QVBoxLayout(controls_panel)
        controls.setContentsMargins(12, 16, 12, 12)
        controls.addWidget(label("CAMERA & CAPTURE", "eyebrow"))
        self.camera_choice = QComboBox()
        controls.addWidget(self.camera_choice)
        camera_actions = QHBoxLayout()
        camera_actions.addWidget(button("Connect", self.connect_camera))
        camera_actions.addWidget(button("Refresh", self.refresh_cameras))
        camera_actions.addWidget(button("Disconnect", self.disconnect_camera))
        controls.addLayout(camera_actions)
        self.camera_status = label("No camera connected")
        controls.addWidget(self.camera_status)
        self.eye = QComboBox()
        self.eye.addItem("Select eye…", "")
        self.eye.addItem("RIGHT eye · OD", "R")
        self.eye.addItem("LEFT eye · OS", "L")
        self.eye.currentIndexChanged.connect(self.update_capture_buttons)
        controls.addWidget(self.eye)
        self.capture_button = button("Capture photograph   F5", self.capture, True)
        controls.addWidget(self.capture_button)
        self.record_button = button("Record video   F6", self.toggle_video)
        controls.addWidget(self.record_button)
        self.record_indicator = label("Video: not recording")
        controls.addWidget(self.record_indicator)
        self.beep = QCheckBox("Sound after successful save")
        self.beep.setChecked(catalog_value(self.catalog, "beep", False))
        self.beep.toggled.connect(lambda value: self.catalog.set_setting("beep", value))
        controls.addWidget(self.beep)
        controls.addWidget(label("CAPTURE PRESET", "eyebrow"))
        self.preset_choice = QComboBox()
        controls.addWidget(self.preset_choice)
        preset_actions = QHBoxLayout()
        preset_actions.addWidget(button("Apply", self.apply_preset))
        preset_actions.addWidget(button("Save new", self.new_preset))
        preset_actions.addWidget(button("Edit", self.edit_preset))
        controls.addLayout(preset_actions)
        small_presets = QHBoxLayout()
        small_presets.addWidget(button("Duplicate", self.duplicate_preset))
        small_presets.addWidget(button("Delete preset", self.delete_preset))
        controls.addLayout(small_presets)
        self.preset_instructions = label("Connect a camera to configure available settings.")
        controls.addWidget(self.preset_instructions)
        controls.addWidget(label("SELECTED IMAGE / VIDEO", "eyebrow"))
        self.media_details = label("Choose an item in the gallery.")
        controls.addWidget(self.media_details)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("Tags, separated by commas")
        controls.addWidget(self.tags)
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Clinical notes for selected item…")
        self.notes.setMaximumHeight(95)
        controls.addWidget(self.notes)
        self.favourite = QCheckBox("Favourite")
        controls.addWidget(self.favourite)
        note_actions = QHBoxLayout()
        note_actions.addWidget(button("Save details", self.save_details))
        note_actions.addWidget(button("Add tags to selected", self.batch_tags))
        controls.addLayout(note_actions)
        export_strip = QHBoxLayout()
        export_strip.addWidget(label("DRAG / EXPORT", "eyebrow"))
        self.export_mode = QComboBox()
        for name, value in [
            ("Original file", "original"),
            ("Edited · no annotations", "edited"),
            ("Edited · with annotations", "annotated"),
        ]:
            self.export_mode.addItem(name, value)
        self.export_mode.setCurrentIndex(
            max(0, self.export_mode.findData(self.catalog.get_setting("export_mode", "original")))
        )
        self.export_mode.currentIndexChanged.connect(
            lambda: self.catalog.set_setting("export_mode", self.export_mode.currentData())
        )
        export_strip.addWidget(self.export_mode, 1)
        self.export_format = QComboBox()
        self.export_format.addItems(["JPEG", "PNG", "TIFF"])
        export_strip.addWidget(self.export_format)
        export_strip.addWidget(button("Preview", self.preview_export))
        export_strip.addWidget(button("Export…", self.export_files))
        centre_layout.insertLayout(centre_layout.indexOf(self.gallery), export_strip)
        controls.addWidget(button("Send selected to PACS…", self.send_pacs))
        controls.addWidget(
            label(
                "Drag selected thumbnails into email, Explorer or an application that accepts files. Originals stay in the archive."
            )
        )
        controls.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls_panel)
        body.addWidget(scroll)
        body.setSizes([280, 890, 310])

    def build_menu(self):
        groups = {
            "File": [
                ("Import worklist…", self.import_worklist),
                ("Import photos / videos…", self.import_files),
                ("Query DICOM worklist…", self.query_worklist),
                ("Open archive folder", lambda: self.open_path(self.catalog.root)),
                ("Open export copies", lambda: self.open_path(self.catalog.root / ".exports")),
                ("Settings…", self.settings),
                ("Exit", self.close),
            ],
            "Archive": [
                ("Back up now…", self.backup_now),
                ("Restore backup to a new folder…", self.restore_backup),
                ("Check archive integrity", self.check_integrity),
                ("Review interrupted captures", self.interrupted),
                ("Correct image assignment…", self.reassign),
                ("Audit history", self.show_audit),
            ],
            "Camera": [
                ("Connection diagnostic…", self.diagnostics),
                ("Capture presets", self.new_preset),
                ("Vendor import inbox", self.show_inbox),
            ],
            "PACS": [("Test connection", self.test_pacs), ("Transfer queue", self.transfer_queue)],
            "Help": [("Quick start", self.quick_start), ("Camera compatibility", self.compatibility)],
        }
        for title, actions in groups.items():
            menu = self.menuBar().addMenu(title)
            for text, callback in actions:
                action = QAction(text, self)
                action.triggered.connect(callback)
                menu.addAction(action)

    def run_task(self, function, done=None, on_error=None):
        task = Task(function)
        self.tasks.add(task)
        if done:
            task.signals.done.connect(done)
        task.signals.error.connect(on_error or (lambda message: error(self, message)))
        task.signals.finished.connect(lambda: self.tasks.discard(task))
        self.pool.start(task)
        return task

    def notice(self, text):
        self.statusBar().showMessage(text)

    def day(self):
        return self.clinic_date.date().toString("yyyy-MM-dd")

    def refresh_worklist(self, *args):
        if not hasattr(self, "patient_list"):
            return
        selected = (
            self.patient_list.currentItem().data(Qt.ItemDataRole.UserRole)
            if self.patient_list.currentItem()
            else None
        )
        self.patient_list.clear()
        for row in self.catalog.worklist(self.day(), self.patient_search.text()):
            item = QListWidgetItem(
                f"{row['name']}\nMRN {row['mrn']}  ·  {row['dob']}\n{row['appointment'] or 'Unscheduled'}  ·  {row['state']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.patient_list.addItem(item)
            if row["id"] == selected:
                self.patient_list.setCurrentItem(item)

    def import_worklist(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import today's worklist", "", "Worklists (*.csv *.xlsx)")
        if path:
            try:
                WorklistDialog(self.catalog, path, self.day(), self).exec()
                self.refresh_worklist()
            except Exception as exc:
                error(self, exc)

    def add_patient(self):
        PatientDialog(self.catalog, self.day(), self).exec()
        self.refresh_worklist()

    def busy_capture(self):
        return bool(self.pending or (self.camera and self.camera.recording))

    def select_patient(self, *args):
        if self.busy_capture():
            error(self, "Stop recording and wait for pending captures to save before changing patient.")
            return
        item = self.patient_list.currentItem()
        if not item:
            return
        try:
            if self.active_session:
                self.catalog.end_session(self.active_session["id"])
            self.active_session = self.catalog.start_session(item.data(Qt.ItemDataRole.UserRole))
            session = self.active_session
            self.patient_title.setText(session["name"])
            self.patient_details.setText(
                f"CAPTURE PATIENT · MRN {session['mrn']} · DOB {session['dob']} · Session {session['created'][11:19]}"
            )
            self.eye.setCurrentIndex(0)
            self.scope.setCurrentIndex(0)
            self.show_live()
            self.refresh_worklist()
            self.refresh_gallery()
            self.update_capture_buttons()
        except Exception as exc:
            error(self, exc)

    def end_session(self):
        if not self.active_session:
            return
        if self.busy_capture():
            error(self, "Wait for pending captures and stop recording before ending this session.")
            return
        try:
            self.catalog.end_session(self.active_session["id"])
            self.active_session = None
            self.patient_title.setText("Select the next patient")
            self.patient_details.setText("Previous session saved. No capture patient selected.")
            self.eye.setCurrentIndex(0)
            self.refresh_worklist()
            self.refresh_gallery()
            self.update_capture_buttons()
        except Exception as exc:
            error(self, exc)

    def refresh_cameras(self):
        if not hasattr(self, "camera_choice"):
            return
        self.camera_choice.clear()
        self.camera_choice.addItem("Canon EOS 200D II / 60D / 70D", ("canon", None))
        self.devices = available_devices()
        for index, device in enumerate(self.devices):
            self.camera_choice.addItem(device.description() + " · Windows device", ("windows", index))
        self.camera_choice.addItem("CSO Mizar / Phoenix · file import", ("inbox", None))
        self.camera_choice.addItem("Demonstration camera · simulated", ("simulator", None))

    def connect_camera(self):
        if self.busy_capture():
            error(self, "Finish the active capture before switching cameras.")
            return
        try:
            self.disconnect_camera()
            kind, index = self.camera_choice.currentData()
            if kind == "inbox":
                self.camera_status.setText(
                    "CSO / Phoenix import workflow. Capture in vendor software, then review imports here."
                )
                self.show_inbox()
                return
            if kind == "canon":
                folder = self.catalog.get_setting("canon_sdk", "")
                if not folder:
                    error(self, "Set the Canon 64-bit EDSDK folder in Settings first.")
                    return
                self.camera = CanonCamera(Path(folder), parent=self)
                self.camera.folder_for_orphans = self.catalog.root / ".staging"
                self.camera.orphan_file.connect(self.on_orphan)
                self.camera.settings_changed.connect(lambda values: self.refresh_presets())
                self.camera.preset_result.connect(self.preset_feedback)
            elif kind == "windows":
                self.camera = WindowsCamera(self.devices[index], self)
            else:
                self.camera = SimulatedCamera(self)
            self.camera.frame.connect(self.on_frame)
            self.camera.captured.connect(self.on_captured)
            self.camera.failed.connect(self.on_capture_error)
            self.camera.status.connect(self.camera_message)
            self.camera.recording_changed.connect(self.on_recording)
            self.camera.connect_camera()
            self.refresh_presets()
            self.update_capture_buttons()
        except Exception as exc:
            error(self, exc)

    def disconnect_camera(self):
        if self.busy_capture():
            raise ValueError("Finish the active capture before disconnecting.")
        if self.camera:
            self.camera.close()
            self.camera.deleteLater()
            self.camera = None
        self.camera_status.setText("No camera connected")
        self.update_capture_buttons()

    def camera_message(self, message):
        self.camera_status.setText(message)
        if self.camera and not self.camera.connected and self.camera.recording:
            self.camera.stop_video()
            self.notice("Camera disconnected. Recording stopped; verify the saved clip.")
        self.update_capture_buttons()

    def on_frame(self, image):
        if self.live:
            self.viewer.setCurrentWidget(self.image_view)
            self.image_view.display(image)
        self.update_capture_buttons()

    def show_live(self):
        self.live = True
        self.player.stop()
        self.current_media = None
        self.viewer_title.setText(
            "LIVE VIEW · " + (self.camera.info.label if self.camera else "connect a camera")
        )
        self.viewer.setCurrentWidget(self.image_view if self.camera and self.camera.latest else self.empty)
        self.image_view.auto_fit = True
        self.update_capture_buttons()

    def update_capture_buttons(self, *args):
        if not hasattr(self, "capture_button"):
            return
        available = bool(
            self.active_session
            and self.camera
            and self.camera.connected
            and self.eye.currentData()
            and self.live
        )
        recording = bool(self.camera and self.camera.recording)
        self.capture_button.setEnabled(available and not self.pending and not recording)
        self.record_button.setEnabled(
            recording or (available and not self.pending and self.camera.info.video)
        )
        self.eye.setEnabled(not self.busy_capture())
        self.play_button.setEnabled(bool(self.current_media and self.current_media["kind"] == "video"))
        self.frame_button.setEnabled(
            bool(self.current_media and self.current_media["kind"] == "video" and self.active_session)
        )

    def ticket(self, kind):
        if not self.active_session or not self.camera or not self.camera.connected:
            raise ValueError("Select a patient and connect a camera first.")
        if not self.live:
            raise ValueError("Return to Live view before capturing for the active patient.")
        if self.pending:
            raise ValueError("Wait for the current capture to finish.")
        ticket = self.catalog.reserve(
            self.active_session["id"],
            self.eye.currentData(),
            kind,
            self.camera.info.label,
            {"preset": self.preset_choice.currentText(), "settings": self.camera.settings()},
        )
        self.pending.add(ticket.id)
        self.update_capture_buttons()
        return ticket

    def capture(self):
        try:
            ticket = self.ticket("image")
            self.notice("Capturing…")
            try:
                self.camera.capture(ticket)
            except Exception as exc:
                self.on_capture_error(ticket, str(exc))
        except Exception as exc:
            error(self, exc)

    def toggle_video(self):
        try:
            if self.camera and self.camera.recording:
                self.notice("Finalising recording…")
                self.camera.stop_video()
            else:
                ticket = self.ticket("video")
                try:
                    self.camera.start_video(ticket)
                except Exception as exc:
                    self.on_capture_error(ticket, str(exc))
        except Exception as exc:
            error(self, exc)

    def on_recording(self, recording):
        self.record_start = time.monotonic() if recording else None
        self.record_button.setText(
            "Stop recording"
            if recording
            else "Record video   " + self.catalog.get_setting("video_shortcut", "F6")
        )
        self.record_button.setObjectName("danger" if recording else "")
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)
        if not recording:
            self.record_indicator.setText("Video: finalising / saved")
        self.update_capture_buttons()

    def on_captured(self, ticket, path, metadata):
        self.notice("Saving and verifying capture…")

        def ingest():
            meta = dict(metadata)
            companions = meta.pop("companions", [])
            result = self.catalog.finish(ticket, Path(path), meta)
            for companion in companions:
                extra = self.catalog.reserve(
                    ticket.session_id, ticket.eye, "image", ticket.camera, {"capture_group": ticket.id}
                )
                try:
                    self.catalog.finish(extra, Path(companion), {"capture_group": ticket.id})
                except Exception as exc:
                    self.catalog.fail(extra, type(exc).__name__)
                    raise
            return result

        def saved(item):
            self.pending.discard(ticket.id)
            self.notice(
                f"Saved · {item['width']} × {item['height']} · {'Right' if item['eye'] == 'R' else 'Left'} eye"
            )
            if self.beep.isChecked():
                QApplication.beep()
            self.refresh_gallery()
            self.update_capture_buttons()

        self.run_task(ingest, saved, lambda message: self.on_capture_error(ticket, message))

    def on_capture_error(self, ticket, message):
        if ticket:
            self.catalog.fail(ticket, "Capture/transfer error")
            self.pending.discard(ticket.id)
        self.notice("Capture error: " + message)
        self.update_capture_buttons()
        error(self, message)

    def on_orphan(self, path):
        path = Path(path)
        ident = uid()
        destination = self.catalog.root / ".inbox" / (ident + path.suffix.lower())
        shutil.copy2(path, destination)
        with self.catalog.transaction():
            self.catalog.db.execute(
                "INSERT INTO inbox(id,path,sha256,created) VALUES(?,?,?,?)",
                (ident, str(path), digest(path), now()),
            )
        self.notice(
            "An unassigned camera file is in the import inbox. Review its patient and eye before assigning."
        )

    def refresh_gallery(self, *args):
        if not hasattr(self, "gallery"):
            return
        params = {
            "text": self.search.text(),
            "eye": self.eye_filter.currentData(),
            "kind": self.kind_filter.currentData(),
            "deleted": self.scope.currentIndex() == 3,
        }
        if self.scope.currentIndex() in (0, 1) and not self.active_session:
            self.gallery.clear()
            self.gallery_count.setText("Select a patient to view sessions")
            return
        if self.scope.currentIndex() == 0:
            params["session_id"] = self.active_session["id"]
        elif self.scope.currentIndex() == 1:
            params["patient_id"] = self.active_session["patient_id"]
        if self.limit_dates.isChecked():
            params.update(
                start=self.date_from.date().toString("yyyy-MM-dd"),
                end=self.date_to.date().toString("yyyy-MM-dd"),
            )
        rows = self.catalog.search(**params)
        self.gallery.blockSignals(True)
        self.gallery.clear()
        for row in rows:
            prefix = "▶ " if row["kind"] == "video" else ""
            if row["favourite"]:
                prefix += "★ "
            item = QListWidgetItem(
                prefix + row["created"][11:19] + " · " + row["eye"] + "\n" + row["created"][:10]
            )
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setToolTip(
                f"{row['name']} · MRN {row['mrn']}\n{row['width']} × {row['height']} · {row['camera']}"
            )
            self.gallery.addItem(item)
        self.gallery.blockSignals(False)
        self.gallery_count.setText(f"{len(rows)} items · drag to export")
        ids = [row["id"] for row in rows]

        def thumbnails():
            results = []
            for row in rows:
                try:
                    source = self.catalog.path(row["path"])
                    if row["kind"] == "video":
                        image = video_frame(source)
                    elif source.suffix in (".cr2", ".cr3"):
                        raise ValueError("RAW")
                    else:
                        image = load_image(source)
                    image.thumbnail((260, 184))
                except Exception:
                    image = Image.new("RGB", (260, 184), (32, 47, 67))
                    ImageDraw.Draw(image).text((35, 70), "RAW / no preview", fill="white", font_size=20)
                results.append((row["id"], image))
            return results

        def loaded(results):
            icons = {mid: QIcon(pixmap(image)) for mid, image in results}
            for i in range(self.gallery.count()):
                item = self.gallery.item(i)
                mid = item.data(Qt.ItemDataRole.UserRole)
                if mid in icons:
                    item.setIcon(icons[mid])

        if ids:
            self.run_task(thumbnails, loaded, lambda message: self.notice("Some thumbnails are unavailable."))

    def selected_ids(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.gallery.selectedItems()]

    def review_selection(self):
        ids = self.selected_ids()
        if not ids:
            return
        self.live = False
        self.player.stop()
        item = self.catalog.media(ids[0])
        self.current_media = item
        self.viewer_title.setText(
            f"REVIEW · {item['name']} · MRN {item['mrn']} · {item['eye']} · {item['created'][:19].replace('T', ' ')}"
        )
        self.tags.setText(", ".join(item["tags"]))
        self.notes.setPlainText(item["notes"])
        self.favourite.setChecked(bool(item["favourite"]))
        self.media_details.setText(
            f"{item['width']} × {item['height']} · {item['kind']}\n{item['camera']}\n{len(ids)} selected"
        )
        from PySide6.QtWidgets import QCompleter

        self.tags.setCompleter(QCompleter(self.catalog.all_tags(), self.tags))
        path = self.catalog.path(item["path"])
        if item["kind"] == "video":
            self.viewer.setCurrentWidget(self.video_widget)
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.pause()
        else:
            mid = item["id"]

            def ready(image):
                if self.current_media and self.current_media["id"] == mid and not self.live:
                    self.viewer.setCurrentWidget(self.image_view)
                    self.image_view.display(image, fit=True)

            self.run_task(
                lambda: render(path, item["edits"], item["annotations"]),
                ready,
                lambda message: self.notice(
                    "Preview unavailable. RAW originals are preserved; use JPEG or RAW+JPEG for editing."
                ),
            )
        self.update_capture_buttons()

    def edit_image(self):
        ids = self.selected_ids()
        if len(ids) != 1:
            error(self, "Select one photograph to edit.")
            return
        try:
            row = self.catalog.media(ids[0])
            if row["kind"] != "image" or row["deleted_at"]:
                raise ValueError("Choose a non-deleted photograph. Extract a frame to annotate a video.")
            if EditorDialog(self.catalog, ids[0], self).exec():
                self.review_selection()
        except Exception as exc:
            error(self, exc)

    def save_details(self):
        ids = self.selected_ids()
        if len(ids) != 1:
            error(self, "Select one image to save notes, or use Add tags to selected for a batch.")
            return
        try:
            self.catalog.update_media(
                ids[0],
                tags=self.tags.text().split(","),
                notes=self.notes.toPlainText(),
                favourite=int(self.favourite.isChecked()),
            )
            self.notice("Tags and notes saved.")
        except Exception as exc:
            error(self, exc)

    def batch_tags(self):
        try:
            for mid in self.selected_ids():
                existing = self.catalog.media(mid)["tags"]
                self.catalog.update_media(mid, tags=existing + self.tags.text().split(","))
            self.notice("Tags added to selected items.")
        except Exception as exc:
            error(self, exc)

    def delete_selected(self):
        if isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit, QPlainTextEdit)):
            return
        ids = self.selected_ids()
        if ids:
            self.player.stop()
            self.catalog.delete(ids)
            self.deleted_batch = ids
            self.current_media = None
            self.refresh_gallery()
            self.viewer.setCurrentWidget(self.empty)
            self.notice(
                f"Moved {len(ids)} items to Deleted items. Undo is available; disk space has not been reclaimed."
            )

    def undo_delete(self):
        if self.deleted_batch:
            self.catalog.delete(self.deleted_batch, restore=True)
            self.deleted_batch = []
            self.refresh_gallery()
            self.notice("Deleted items restored.")

    def restore_selected(self):
        self.catalog.delete(self.selected_ids(), restore=True)
        self.refresh_gallery()

    def purge_selected(self):
        ids = self.selected_ids()
        if self.scope.currentIndex() != 3 or not ids:
            error(self, "Select items in the Deleted items view first.")
            return
        if (
            QMessageBox.question(
                self,
                "Permanently remove files?",
                f"Permanently delete {len(ids)} selected originals and their saved edits? This cannot be undone. Export copies, PACS and backups are not removed.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.player.stop()
            self.catalog.purge(ids)
            self.deleted_batch = [mid for mid in self.deleted_batch if mid not in ids]
            self.refresh_gallery()
            self.viewer.setCurrentWidget(self.empty)
        except Exception as exc:
            error(self, exc)

    def export_files(self):
        ids = self.selected_ids()
        if not ids:
            return
        destination = QFileDialog.getExistingDirectory(self, "Export selected files")
        if not destination:
            return
        mode, fmt = self.export_mode.currentData(), self.export_format.currentText()
        self.run_task(
            lambda: [
                copy_export(prepare_export(self.catalog, mid, mode, fmt), Path(destination)) for mid in ids
            ],
            lambda paths: self.notice(f"Exported {len(paths)} files. Local originals retained."),
        )

    def preview_export(self):
        ids = self.selected_ids()
        if not ids:
            return
        mode, fmt = self.export_mode.currentData(), self.export_format.currentText()

        def show(path):
            item = self.catalog.media(ids[0])
            if item["kind"] == "video":
                self.open_path(path)
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Export preview · " + mode)
            dialog.resize(1000, 720)
            layout = QVBoxLayout(dialog)
            view = ImageView()
            layout.addWidget(view, 1)
            view.display(load_image(path), fit=True)
            layout.addWidget(label(path.name))
            layout.addWidget(button("Close", dialog.accept))
            dialog.exec()

        self.run_task(lambda: prepare_export(self.catalog, ids[0], mode, fmt), show)

    def play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def extract_frame(self):
        if not self.current_media or self.current_media["kind"] != "video" or not self.active_session:
            return
        item = self.current_media
        if item["session_id"] != self.active_session["id"]:
            error(self, "Select a video from the active session before extracting a frame.")
            return
        seconds = self.player.position() / 1000
        ticket = self.catalog.reserve(
            item["session_id"],
            item["eye"],
            "image",
            item["camera"],
            {"source_video": item["id"], "seconds": seconds},
        )
        self.pending.add(ticket.id)

        def extract():
            image = video_frame(self.catalog.path(item["path"]), seconds)
            path = ticket.staging / (ticket.id + ".png")
            image.save(path)
            return path

        self.run_task(
            extract,
            lambda path: self.on_captured(ticket, path, {"source_video": item["id"], "seconds": seconds}),
            lambda msg: self.on_capture_error(ticket, msg),
        )

    def full_screen(self):
        if self.viewer.currentWidget() == self.video_widget:
            self.video_widget.setFullScreen(True)
            return
        image = self.image_view.item.pixmap()
        if image.isNull():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Image review · Escape to close")
        layout = QVBoxLayout(dialog)
        view = QGraphicsView()
        scene = QGraphicsScene(view)
        scene.addPixmap(image)
        view.setScene(scene)
        layout.addWidget(view)
        layout.addWidget(button("Close full screen", dialog.accept))
        dialog.showFullScreen()
        view.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        dialog.exec()

    def refresh_presets(self):
        self.preset_choice.clear()
        if not self.camera:
            return
        rows = self.catalog.query(
            "SELECT * FROM presets WHERE camera_key=? ORDER BY name", (self.camera.info.id,)
        )
        self.preset_choice.addItem("No preset selected", None)
        for row in rows:
            self.preset_choice.addItem(row["name"], row)

    def new_preset(self):
        if not self.camera or not self.camera.connected:
            error(self, "Connect a camera before saving a preset.")
            return
        PresetDialog(self.camera, self.catalog, parent=self).exec()
        self.refresh_presets()

    def edit_preset(self):
        if self.camera and self.preset_choice.currentData():
            PresetDialog(self.camera, self.catalog, self.preset_choice.currentData(), self).exec()
            self.refresh_presets()

    def duplicate_preset(self):
        row = self.preset_choice.currentData()
        if row:
            name, ok = QInputDialog.getText(self, "Duplicate preset", "New name", text=row["name"] + " copy")
            if ok and name:
                self.catalog.save_preset(
                    name, row["camera_key"], json.loads(row["settings"]), row["instructions"]
                )
                self.refresh_presets()

    def delete_preset(self):
        row = self.preset_choice.currentData()
        if row:
            with self.catalog.transaction():
                self.catalog.db.execute("DELETE FROM presets WHERE id=?", (row["id"],))
            self.refresh_presets()

    def apply_preset(self):
        row = self.preset_choice.currentData()
        if self.camera and row:
            if self.busy_capture():
                error(self, "Wait until capture/recording has finished before applying a preset.")
                return
            self.preset_instructions.setText(
                "Manual lamp setup: " + (row["instructions"] or "No instructions saved.")
            )
            self.preset_feedback(self.camera.apply_settings(json.loads(row["settings"])))

    def preset_feedback(self, results):
        self.notice("Preset · " + "; ".join(key + ": " + value for key, value in results.items()))

    def import_files(self):
        if not self.active_session:
            error(self, "Select a patient and start a session before importing files.")
            return
        if self.busy_capture():
            return
        if not self.eye.currentData():
            error(self, "Select Right or Left eye for the imported files.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import for the displayed capture patient",
            "",
            "Media (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.cr2 *.cr3 *.mp4 *.mov *.avi *.mkv *.m4v)",
        )
        if not paths:
            return
        patient = self.active_session
        if (
            QMessageBox.question(
                self,
                "Confirm import identity",
                f"Import {len(paths)} files for {patient['name']}\nMRN {patient['mrn']} · DOB {patient['dob']} · {self.eye.currentText()}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        for path in paths:
            source = Path(path)
            checksum = digest(source)
            if self.catalog.one(
                "SELECT id FROM media WHERE session_id=? AND sha256=? AND status='ready'",
                (patient["id"], checksum),
            ):
                self.notice("An identical file is already in this session; skipped.")
                continue
            ticket = self.catalog.reserve(
                patient["id"],
                self.eye.currentData(),
                "video" if source.suffix.lower() in VIDEO_EXTENSIONS else "image",
                "File import",
            )
            self.pending.add(ticket.id)
            self.on_captured(ticket, source, {"capture_source": "file import"})

    def show_inbox(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Vendor import inbox · confirm identity for each batch")
        dialog.resize(1000, 560)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            label(
                "Files exported by Phoenix or another camera application arrive here without a patient assignment. Originals in the vendor folder are retained."
            )
        )
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Received", "Source file", "Type"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table, 1)

        def refresh():
            rows = self.catalog.query("SELECT * FROM inbox WHERE state='review' ORDER BY created DESC")
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, value in enumerate(
                    (row["created"][:19], Path(row["path"]).name, Path(row["path"]).suffix)
                ):
                    cell = QTableWidgetItem(value)
                    cell.setData(Qt.ItemDataRole.UserRole, row["id"])
                    table.setItem(i, j, cell)

        refresh()
        target = label(
            "Current capture patient: "
            + (
                f"{self.active_session['name']} · MRN {self.active_session['mrn']}"
                if self.active_session
                else "none selected"
            )
        )
        layout.addWidget(target)
        eye = QComboBox()
        eye.addItem("Select eye…", "")
        eye.addItem("Right", "R")
        eye.addItem("Left", "L")
        layout.addWidget(eye)

        def assign():
            indices = sorted({index.row() for index in table.selectedIndexes()})
            if not self.active_session or not eye.currentData() or not indices:
                error(dialog, "Select a capture patient, an eye and one or more inbox files.")
                return
            if (
                QMessageBox.question(
                    dialog,
                    "Confirm patient and eye",
                    f"Assign {len(indices)} files to {self.active_session['name']}\nMRN {self.active_session['mrn']} · DOB {self.active_session['dob']} · {eye.currentText()} eye?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            try:
                for index in indices:
                    self.inbox.assign(
                        table.item(index, 0).data(Qt.ItemDataRole.UserRole),
                        self.active_session["id"],
                        eye.currentData(),
                    )
                refresh()
                self.refresh_gallery()
            except Exception as exc:
                error(dialog, exc)

        def preview():
            row_index = table.currentRow()
            if row_index >= 0:
                row = self.catalog.one(
                    "SELECT * FROM inbox WHERE id=?",
                    (table.item(row_index, 0).data(Qt.ItemDataRole.UserRole),),
                )
                self.open_path(self.inbox.file(row))

        actions = QHBoxLayout()
        actions.addWidget(button("Refresh", refresh))
        actions.addWidget(button("Preview file", preview))
        actions.addWidget(button("Assign selected", assign, True))
        actions.addWidget(button("Close", dialog.accept))
        layout.addLayout(actions)
        dialog.exec()

    def settings(self):
        if SettingsDialog(self.catalog, self).exec():
            self.apply_shortcuts()
            self.notice("Settings saved. Reconnect the camera for driver changes.")

    def apply_shortcuts(self):
        for shortcut in getattr(self, "shortcuts", []):
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = []
        for key, callback in [
            (self.catalog.get_setting("capture_shortcut", "F5"), self.capture),
            (self.catalog.get_setting("video_shortcut", "F6"), self.toggle_video),
            ("Delete", self.delete_selected),
        ]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.capture_button.setText(
            "Capture photograph   " + self.catalog.get_setting("capture_shortcut", "F5")
        )
        self.record_button.setText("Record video   " + self.catalog.get_setting("video_shortcut", "F6"))

    def tick(self):
        free = shutil.disk_usage(self.catalog.root).free / (1024**3)
        self.storage_label.setText(f"LOCAL ARCHIVE · {free:.1f} GB free" + (" · DEMO" if self.demo else ""))
        if self.record_start is not None:
            elapsed = int(time.monotonic() - self.record_start)
            self.record_indicator.setText(f"● RECORDING   {elapsed // 60:02}:{elapsed % 60:02}")
            if free < 0.2 and self.camera:
                self.camera.stop_video()
                self.notice("Recording stopped because storage is low.")
        count = self.catalog.one("SELECT count(*) AS n FROM inbox WHERE state='review'")["n"]
        self.inbox_button.setText(f"Import inbox · {count} to review")
        folder = self.catalog.get_setting("watch_folder", "")
        if folder and not self.scan_running and time.monotonic() - self.last_scan > 3:
            self.scan_running = True
            self.last_scan = time.monotonic()
            task = self.run_task(
                lambda: self.inbox.scan(Path(folder)),
                lambda count: self.notice(f"{count} new files awaiting patient review.") if count else None,
                lambda message: self.notice("Folder import: " + message),
            )
            task.signals.finished.connect(lambda: setattr(self, "scan_running", False))
        hours = self.catalog.get_setting("backup_hours", 24)
        dest = self.catalog.get_setting("backup_folder", "")
        last = self.catalog.get_setting("last_backup", {})
        due = (
            not last
            or (datetime.now().astimezone() - datetime.fromisoformat(last["time"])).total_seconds()
            > hours * 3600
        )
        if (
            hours
            and dest
            and due
            and not self.backup_running
            and not self.busy_capture()
            and time.monotonic() - getattr(self, "last_backup_attempt", 0) > 300
        ):
            self.last_backup_attempt = time.monotonic()
            self.perform_backup(Path(dest))

    def perform_backup(self, destination):
        if self.backup_running:
            return
        self.backup_running = True
        self.notice("Backing up archive…")
        task = self.run_task(
            lambda: self.catalog.backup(destination),
            lambda path: self.notice("Backup verified and saved: " + str(path)),
        )
        task.signals.finished.connect(lambda: setattr(self, "backup_running", False))

    def backup_now(self):
        destination = QFileDialog.getExistingDirectory(
            self, "Choose a separate backup destination", self.catalog.get_setting("backup_folder", "")
        )
        if destination:
            self.perform_backup(Path(destination))

    def restore_backup(self):
        backup = QFileDialog.getExistingDirectory(self, "Select a SlitlampBackup folder")
        if not backup:
            return
        destination = QFileDialog.getExistingDirectory(self, "Select an empty restore destination")
        if destination:
            self.run_task(
                lambda: Catalog.restore(Path(backup), Path(destination)),
                lambda _: QMessageBox.information(
                    self,
                    "Restore complete",
                    "Backup verified and restored. Launch with --data-dir pointing to that folder to open it.",
                ),
            )

    def check_integrity(self):
        def check():
            problems = []
            for row in self.catalog.query("SELECT id,path,sha256 FROM media WHERE status='ready'"):
                path = self.catalog.path(row["path"])
                if not path.is_file() or digest(path) != row["sha256"]:
                    problems.append(row["id"])
            with self.catalog.lock:
                result = self.catalog.db.execute("PRAGMA integrity_check").fetchone()[0]
            return result, problems

        self.run_task(
            check,
            lambda result: QMessageBox.information(
                self,
                "Archive integrity",
                f"Database: {result[0]}\nMedia missing or changed: {len(result[1])}\n"
                + "\n".join(result[1][:20]),
            ),
        )

    def interrupted(self):
        rows = self.catalog.query(
            "SELECT id,created,camera FROM media WHERE status='failed' ORDER BY created DESC"
        )
        QMessageBox.information(
            self,
            "Interrupted captures",
            f"{len(rows)} failed/interrupted capture records. Staging files are retained for manual review and import. Never guess their patient.\n\n"
            + str(self.catalog.root / ".staging"),
        )
        self.open_path(self.catalog.root / ".staging")

    def reassign(self):
        ids = self.selected_ids()
        if len(ids) != 1 or not self.active_session:
            error(self, "Select one image and start a session for the intended patient first.")
            return
        reason, ok = QInputDialog.getText(
            self,
            "Correct image assignment",
            f"Assign to {self.active_session['name']} · MRN {self.active_session['mrn']}\nEye: {self.eye.currentText()}\nReason for correction:",
        )
        if ok:
            try:
                self.catalog.reassign(ids[0], self.active_session["id"], self.eye.currentData(), reason)
                self.refresh_gallery()
                self.notice("Assignment corrected and audited. Existing external exports are unchanged.")
            except Exception as exc:
                error(self, exc)

    def table_dialog(self, title, headers, rows):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(1000, 600)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        return dialog, layout, table

    def show_audit(self):
        rows = self.catalog.query(
            "SELECT occurred,actor,action,target,details FROM audit ORDER BY id DESC LIMIT 500"
        )
        dialog, layout, table = self.table_dialog(
            "Audit history · latest 500 events",
            ["Time", "User", "Action", "Record", "Details"],
            [list(row.values()) for row in rows],
        )
        layout.addWidget(button("Close", dialog.accept))
        dialog.exec()

    def pacs_config(self):
        config = self.catalog.get_setting("pacs", {})
        if not config.get("host"):
            raise ValueError("Configure the PACS host, port and AE titles in Settings first.")
        return config

    def test_pacs(self):
        from ..pacs import echo

        try:
            config = self.pacs_config()
            self.run_task(
                lambda: echo(config), lambda _: self.notice("PACS acknowledged the connection test.")
            )
        except Exception as exc:
            error(self, exc)

    def send_pacs(self):
        from ..pacs import queue_transfer, send_transfer

        ids = self.selected_ids()
        if not ids:
            return
        try:
            config = self.pacs_config()
            if (
                QMessageBox.question(
                    self,
                    "Send images to PACS",
                    f"Send {len(ids)} selected images to {config['called_ae']} at {config['host']}?\nFormat: RGB DICOM Secondary Capture. Confirm the selected patients and destination support. Videos are not supported by this DICOM exporter.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            mode = self.export_mode.currentData()

            def send():
                tids = [queue_transfer(self.catalog, mid, config, mode) for mid in ids]
                for tid in tids:
                    send_transfer(self.catalog, tid)
                return len(tids)

            self.run_task(
                send,
                lambda count: self.notice(f"PACS acknowledged {count} images. Local originals retained."),
            )
        except Exception as exc:
            error(self, exc)

    def transfer_queue(self):
        from ..pacs import send_transfer

        rows = self.catalog.query(
            "SELECT id,state,attempts,updated,error FROM transfers ORDER BY updated DESC"
        )
        dialog, layout, table = self.table_dialog(
            "PACS transfer queue",
            ["Transfer", "State", "Attempts", "Updated", "Result"],
            [list(row.values()) for row in rows],
        )

        def retry():
            index = table.currentRow()
            if index >= 0 and rows[index]["state"] in ("failed", "queued"):
                tid = rows[index]["id"]
                self.run_task(
                    lambda: send_transfer(self.catalog, tid),
                    lambda _: self.notice("PACS acknowledged the retry."),
                )
                dialog.accept()

        layout.addWidget(button("Retry selected queued/failed transfer", retry))
        layout.addWidget(button("Close", dialog.accept))
        dialog.exec()

    def query_worklist(self):
        from ..pacs import query_worklist

        try:
            config = dict(self.pacs_config())
            host, ok = QInputDialog.getText(
                self, "DICOM Modality Worklist", "Worklist host (may differ from PACS)", text=config["host"]
            )
            if not ok:
                return
            port, ok = QInputDialog.getInt(
                self,
                "DICOM Modality Worklist",
                "Worklist port",
                value=int(config["port"]),
                minValue=1,
                maxValue=65535,
            )
            if not ok:
                return
            called, ok = QInputDialog.getText(
                self, "DICOM Modality Worklist", "Worklist server AE title", text=config["called_ae"]
            )
            if not ok:
                return
            config.update(host=host, port=port, called_ae=called)
            day = self.day()

            def review(rows):
                dialog, layout, table = self.table_dialog(
                    "Worklist results · review before import",
                    ["Name", "MRN", "DOB", "Date", "Time"],
                    [(r.name, r.mrn, r.dob, r.day, r.appointment) for r in rows],
                )

                def save():
                    try:
                        self.catalog.import_worklist(rows)
                        self.refresh_worklist()
                        dialog.accept()
                    except Exception as exc:
                        error(dialog, exc)

                layout.addWidget(button("Import results", save))
                layout.addWidget(button("Cancel", dialog.reject))
                dialog.exec()

            self.run_task(lambda: query_worklist(config, day), review)
        except Exception as exc:
            error(self, exc)

    def diagnostics(self):
        devices = available_devices()
        diagnostic = {
            "app_version": __version__,
            "platform": sys.platform,
            "python_bits": 64 if sys.maxsize > 2**32 else 32,
            "target_cameras": ["Canon EOS 200D II", "Canon EOS 60D", "Canon EOS 70D", "CSO Mizar"],
            "visible_windows_devices": [
                {
                    "name": d.description(),
                    "id": bytes(d.id()).hex(),
                    "formats": [
                        {
                            "width": f.resolution().width(),
                            "height": f.resolution().height(),
                            "max_fps": f.maxFrameRate(),
                        }
                        for f in d.videoFormats()
                    ],
                }
                for d in devices
            ],
            "canon_sdk_present": (Path(self.catalog.get_setting("canon_sdk", "")) / "EDSDK.dll").is_file(),
            "hardware_verified": False,
        }
        dialog = QDialog(self)
        dialog.setWindowTitle("Camera diagnostic · contains no patient records")
        dialog.resize(800, 650)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(json.dumps(diagnostic, indent=2))
        text.setReadOnly(True)
        layout.addWidget(text)

        def save():
            path, _ = QFileDialog.getSaveFileName(
                dialog, "Save diagnostic", "camera-diagnostic.json", "JSON (*.json)"
            )
            if path:
                Path(path).write_text(text.toPlainText(), encoding="utf-8")

        layout.addWidget(button("Save diagnostic", save))
        layout.addWidget(button("Close", dialog.accept))
        dialog.exec()

    def compatibility(self):
        QMessageBox.information(
            self,
            "Camera compatibility",
            "Canon EOS 200D II / 60D / 70D: implemented through the official Windows x64 EDSDK; exact hardware and driver combinations need verification. Use JPEG or RAW+JPEG. Video is the live-view stream.\n\nCSO Mizar: use direct capture only if its installed driver exposes it in the Windows device list. Otherwise export photographs/videos from Phoenix into the review inbox. A proprietary Mizar SDK is not bundled or verified.\n\nUse Camera → Connection diagnostic on the Windows capture PC.",
        )

    def quick_start(self):
        QMessageBox.information(
            self,
            "Quick start",
            "1. Import a CSV/XLSX worklist or add a patient.\n2. Double-click the patient and check name, MRN and DOB.\n3. Connect a camera and select Right or Left.\n4. Capture with F5; start/stop video with F6.\n5. Select thumbnails to review, tag or annotate.\n6. Drag selected thumbnails into email or folders.\n7. Delete poor images; use Deleted items to restore or permanently remove them.\n\nFor Canon, set your SDK folder in Settings. For Mizar, run a connection diagnostic or configure the Phoenix export folder. Set a separate backup destination before use.",
        )

    def open_path(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def seed_demo(self):
        if not self.catalog.worklist(self.day()):
            self.catalog.import_worklist(
                [
                    WorklistRow("Alex Morgan", "DEMO001", "1972-04-18", self.day(), "09:00"),
                    WorklistRow("Jamie Taylor", "DEMO002", "1986-11-03", self.day(), "09:15"),
                    WorklistRow("Alex Morgan", "DEMO003", "1955-09-21", self.day(), "09:30"),
                ]
            )
        self.refresh_worklist()
        if self.patient_list.count():
            self.patient_list.setCurrentRow(0)
            self.select_patient()
        self.camera_choice.setCurrentIndex(self.camera_choice.count() - 1)
        self.connect_camera()
        self.eye.setCurrentIndex(1)

    def closeEvent(self, event):
        if self.busy_capture() or self.tasks:
            error(self, "Finish recording/capture and wait for background work to complete before closing.")
            event.ignore()
            return
        try:
            self.timer.stop()
            self.disconnect_camera()
            self.player.stop()
            if self.active_session:
                self.catalog.end_session(self.active_session["id"])
            self.catalog.close()
            event.accept()
        except Exception as exc:
            self.timer.start()
            error(self, exc)
            event.ignore()


def catalog_value(catalog, key, default):
    return catalog.get_setting(key, default)

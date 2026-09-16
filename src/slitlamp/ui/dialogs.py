import json
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QDialogButtonBox,
    QTextEdit,
    QDateEdit,
    QSpinBox,
    QFileDialog,
    QMessageBox,
    QHeaderView,
    QDoubleSpinBox,
)

from ..worklist import read_table, map_rows
from ..models import WorklistRow
from .common import error


class WorklistDialog(QDialog):
    def __init__(self, catalog, path, clinic_day, parent=None):
        super().__init__(parent)
        self.catalog, self.day = catalog, clinic_day
        self.headings, self.source = read_table(Path(path))
        self.rows = []
        self.setWindowTitle("Import worklist · map columns and preview")
        self.resize(950, 650)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mapping = {}
        aliases = {
            "name": ["name", "patientname", "patient_name", "fullname"],
            "mrn": ["mrn", "patientid", "medicalrecordnumber", "patient_id"],
            "dob": ["dob", "dateofbirth", "birthdate", "date_of_birth"],
            "day": ["day", "date", "appointmentdate"],
            "appointment": ["appointment", "time", "appointmenttime"],
            "order_id": ["order_id", "accession", "accessionnumber"],
            "issuer": ["issuer", "organisation", "organization"],
        }
        for field, label in [
            ("name", "Patient name *"),
            ("mrn", "MRN *"),
            ("dob", "Date of birth *"),
            ("day", "Clinic date (optional)"),
            ("appointment", "Appointment time"),
            ("order_id", "Order / accession"),
            ("issuer", "MRN issuer"),
        ]:
            combo = QComboBox()
            combo.addItem("Not supplied", "")
            for heading in self.headings:
                combo.addItem(heading, heading)
                if heading.lower().replace(" ", "") in aliases[field]:
                    combo.setCurrentIndex(combo.count() - 1)
            self.mapping[field] = combo
            form.addRow(label, combo)
        self.order = QComboBox()
        self.order.addItems(["DMY", "MDY", "ISO"])
        form.addRow("Date format", self.order)
        layout.addLayout(form)
        self.summary = QLabel(
            "Review the preview before importing. No patient records are changed until Import."
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "MRN", "DOB", "Clinic date", "Time"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        preview = QPushButton("Refresh preview")
        preview.clicked.connect(self.preview)
        buttons.addWidget(preview)
        self.import_button = QPushButton("Import worklist")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self.commit)
        buttons.addWidget(self.import_button)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.preview()

    def preview(self):
        try:
            mapping = {key: box.currentData() for key, box in self.mapping.items()}
            if any(not mapping[key] for key in ("name", "mrn", "dob")):
                raise ValueError("Map name, MRN and date of birth.")
            self.rows = map_rows(self.source, mapping, self.order.currentText(), self.day)
            self.table.setRowCount(len(self.rows))
            for index, row in enumerate(self.rows):
                for column, value in enumerate((row.name, row.mrn, row.dob, row.day, row.appointment)):
                    self.table.setItem(index, column, QTableWidgetItem(value))
            self.summary.setText(f"{len(self.rows)} rows. Check MRNs and birth dates before importing.")
            self.import_button.setEnabled(bool(self.rows))
            return True
        except Exception as exc:
            self.summary.setText(str(exc))
            self.import_button.setEnabled(False)
            return False

    def commit(self):
        if not self.preview():
            return
        try:
            added, existing = self.catalog.import_worklist(self.rows)
            QMessageBox.information(
                self,
                "Worklist imported",
                f"Added {added} appointments. {existing} existing appointments retained.",
            )
            self.accept()
        except Exception as exc:
            error(self, exc)


class PatientDialog(QDialog):
    def __init__(self, catalog, day, parent=None):
        super().__init__(parent)
        self.catalog, self.day = catalog, day
        self.setWindowTitle("Add patient to worklist")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name, self.mrn, self.issuer = QLineEdit(), QLineEdit(), QLineEdit("CLINIC")
        self.dob = QDateEdit(QDate(1980, 1, 1))
        self.dob.setCalendarPopup(True)
        self.dob.setDisplayFormat("dd MMM yyyy")
        for label, field in [
            ("Full name", self.name),
            ("MRN", self.mrn),
            ("Date of birth", self.dob),
            ("MRN issuer", self.issuer),
        ]:
            form.addRow(label, field)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            self.catalog.import_worklist(
                [
                    WorklistRow(
                        self.name.text().strip(),
                        self.mrn.text().strip(),
                        self.dob.date().toString("yyyy-MM-dd"),
                        self.day,
                        issuer=self.issuer.text().strip() or "CLINIC",
                    )
                ]
            )
            self.accept()
        except Exception as exc:
            error(self, exc)


class PresetDialog(QDialog):
    def __init__(self, camera, catalog, preset=None, parent=None):
        super().__init__(parent)
        self.camera, self.catalog, self.preset = camera, catalog, preset
        self.setWindowTitle("Capture preset")
        self.resize(500, 520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(preset["name"] if preset else "")
        self.name.setPlaceholderText("e.g. Diffuse illumination")
        form.addRow("Name", self.name)
        settings = json.loads(preset["settings"]) if preset else camera.settings()
        self.inputs = {}
        options = camera.options() if hasattr(camera, "options") else {}
        for key, value in settings.items():
            if key in options and options[key]:
                control = QComboBox()
                for option in options[key]:
                    control.addItem(option["label"], option["value"])
                match = control.findData(value)
                if match >= 0:
                    control.setCurrentIndex(match)
            else:
                control = QDoubleSpinBox()
                control.setDecimals(6 if key == "exposure_seconds" else 2)
                control.setRange(-1_000_000, 1_000_000)
                control.setValue(float(value))
                if key in ("width", "height"):
                    control.setReadOnly(True)
            self.inputs[key] = control
            form.addRow(key.replace("_", " ").title(), control)
        layout.addLayout(form)
        layout.addWidget(QLabel("Manual slit lamp setup (filter, magnification, slit width)"))
        self.instructions = QTextEdit(preset["instructions"] if preset else "")
        layout.addWidget(self.instructions)
        hint = QLabel(
            "Only controls exposed by this camera are listed. Physical lamp settings must be adjusted manually."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            values = {
                key: (control.currentData() if isinstance(control, QComboBox) else control.value())
                for key, control in self.inputs.items()
            }
            self.catalog.save_preset(
                self.name.text(), self.camera.info.id, values, self.instructions.toPlainText()
            )
            self.accept()
        except Exception as exc:
            error(self, exc)


class SettingsDialog(QDialog):
    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setWindowTitle("Settings · storage and integrations")
        self.resize(650, 600)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Current archive", QLabel(str(catalog.root)))
        self.fields = {}
        for key, label in [
            ("canon_sdk", "Canon 64-bit SDK folder"),
            ("watch_folder", "Vendor export folder"),
            ("backup_folder", "Automatic backup destination"),
        ]:
            edit = QLineEdit(catalog.get_setting(key, ""))
            row = QHBoxLayout()
            row.addWidget(edit)
            browse = QPushButton("Browse…")
            browse.clicked.connect(lambda checked=False, e=edit: self.browse(e))
            row.addWidget(browse)
            form.addRow(label, row)
            self.fields[key] = edit
        for key, label, default in [
            ("capture_shortcut", "Capture shortcut", "F5"),
            ("video_shortcut", "Video shortcut", "F6"),
        ]:
            edit = QLineEdit(catalog.get_setting(key, default))
            self.fields[key] = edit
            form.addRow(label, edit)
        self.interval = QSpinBox()
        self.interval.setRange(0, 168)
        self.interval.setValue(catalog.get_setting("backup_hours", 24))
        self.interval.setSpecialValueText("Manual only")
        form.addRow("Backup interval (hours)", self.interval)
        config = catalog.get_setting("pacs", {})
        for key, label, default in [
            ("host", "PACS / worklist host", ""),
            ("port", "Port", "104"),
            ("calling_ae", "Our AE title", "SLITLAMP"),
            ("called_ae", "Server AE title", "PACS"),
        ]:
            edit = QLineEdit(str(config.get(key, default)))
            self.fields["pacs_" + key] = edit
            form.addRow(label, edit)
        layout.addLayout(form)
        notice = QLabel(
            "DICOM C-STORE uses the configured clinic network. Use an approved secure network/VPN. Worklist may use a separate endpoint when queried. Canon SDK libraries are supplied by Canon, not bundled."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self, edit):
        path = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text())
        if path:
            edit.setText(path)

    def save(self):
        try:
            config = {
                key: self.fields["pacs_" + key].text().strip()
                for key in ("host", "port", "calling_ae", "called_ae")
            }
            config["port"] = int(config["port"])
            if not 1 <= config["port"] <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
            for key in ("calling_ae", "called_ae"):
                if (
                    not config[key]
                    or len(config[key]) > 16
                    or "\\" in config[key]
                    or not config[key].isascii()
                ):
                    raise ValueError("AE titles need 1–16 ASCII characters without backslashes.")
            for key, edit in self.fields.items():
                if not key.startswith("pacs_"):
                    self.catalog.set_setting(key, edit.text().strip())
            self.catalog.set_setting("backup_hours", self.interval.value())
            self.catalog.set_setting("pacs", config)
            self.accept()
        except Exception as exc:
            error(self, exc)

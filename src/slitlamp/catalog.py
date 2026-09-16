"""SQLite catalogue and auditable, patient-bound archive operations.

Media writes are staged before being atomically renamed into the archive. A
pending row contains the final path before rename, so a crash is reconcilable.
The catalogue is local to one workstation; do not place it on a network share.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from .models import CaptureTicket, WorklistRow, now, uid


class IdentityConflict(ValueError):
    pass


def safe_name(value: str, limit: int = 48) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    value = re.sub(r"\s+", "_", value)[:limit].rstrip(" .") or "unnamed"
    if value.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *[f"COM{i}" for i in range(10)],
        *[f"LPT{i}" for i in range(10)],
    }:
        value = "_" + value
    return value


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS patients(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, mrn TEXT NOT NULL, dob TEXT NOT NULL,
 issuer TEXT NOT NULL, UNIQUE(mrn,issuer));
CREATE TABLE IF NOT EXISTS encounters(
 id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
 day TEXT NOT NULL, appointment TEXT NOT NULL, order_id TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'waiting', UNIQUE(patient_id,day,appointment,order_id));
CREATE TABLE IF NOT EXISTS sessions(
 id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
 encounter_id TEXT REFERENCES encounters(id), created TEXT NOT NULL,
 ended TEXT, folder TEXT NOT NULL UNIQUE, notes TEXT NOT NULL DEFAULT '',
 study_uid TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS media(
 id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
 session_id TEXT NOT NULL REFERENCES sessions(id), eye TEXT NOT NULL CHECK(eye IN ('R','L')),
 kind TEXT NOT NULL CHECK(kind IN ('image','video')), camera TEXT NOT NULL,
 created TEXT NOT NULL, path TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
 sha256 TEXT NOT NULL DEFAULT '', width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
 duration REAL DEFAULT 0, notes TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
 favourite INTEGER NOT NULL DEFAULT 0, deleted_at TEXT,
 edits TEXT NOT NULL DEFAULT '{}', annotations TEXT NOT NULL DEFAULT '[]',
 metadata TEXT NOT NULL DEFAULT '{}', source_id TEXT, revision INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_media_session ON media(session_id,status,deleted_at);
CREATE INDEX IF NOT EXISTS ix_media_patient ON media(patient_id,created);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, occurred TEXT NOT NULL, actor TEXT NOT NULL,
 action TEXT NOT NULL, target TEXT NOT NULL, details TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS presets(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, camera_key TEXT NOT NULL,
 settings TEXT NOT NULL, instructions TEXT NOT NULL DEFAULT '', UNIQUE(name,camera_key));
CREATE TABLE IF NOT EXISTS transfers(
 id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id), destination TEXT NOT NULL,
 path TEXT NOT NULL, sop_uid TEXT NOT NULL, state TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inbox(
 id TEXT PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'review',
 created TEXT NOT NULL, UNIQUE(path,sha256));
PRAGMA user_version=1;
"""


class Catalog:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for folder in (".staging", ".exports", ".inbox"):
            (self.root / folder).mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "catalog.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            raise RuntimeError("This archive needs a newer version of Slitlamp Studio.")
        self.db.executescript(SCHEMA)
        self.recover()

    @contextmanager
    def transaction(self):
        with self.lock:
            with self.db:
                yield self.db

    def close(self):
        with self.lock:
            self.db.close()

    def query(self, sql: str, args=()) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, args)]

    def one(self, sql: str, args=()) -> dict | None:
        rows = self.query(sql, args)
        return rows[0] if rows else None

    def audit(self, action: str, target: str, details=None):
        # Contains archive identifiers, not patient names or image content.
        self.db.execute(
            "INSERT INTO audit(occurred,actor,action,target,details) VALUES(?,?,?,?,?)",
            (now(), getpass.getuser(), action, target, json.dumps(details or {})),
        )

    def get_setting(self, key: str, default=None):
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value):
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))

    def import_worklist(self, rows: list[WorklistRow]) -> tuple[int, int]:
        added = existing = 0
        with self.transaction():
            for row in rows:
                if not row.name.strip() or not row.mrn.strip():
                    raise ValueError("Name and MRN are required.")
                birth = date.fromisoformat(row.dob)
                day = date.fromisoformat(row.day)
                if birth > day:
                    raise ValueError("Date of birth cannot be after the appointment date.")
                patient = self.one("SELECT * FROM patients WHERE mrn=? AND issuer=?", (row.mrn, row.issuer))
                if patient and (
                    patient["dob"] != row.dob or patient["name"].casefold() != row.name.strip().casefold()
                ):
                    raise IdentityConflict(
                        f"Conflicting patient details for MRN {row.mrn}. No rows were imported."
                    )
                pid = patient["id"] if patient else uid()
                if not patient:
                    self.db.execute(
                        "INSERT INTO patients VALUES(?,?,?,?,?)",
                        (pid, row.name.strip(), row.mrn, row.dob, row.issuer),
                    )
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO encounters(id,patient_id,day,appointment,order_id) VALUES(?,?,?,?,?)",
                    (uid(), pid, row.day, row.appointment, row.order_id),
                )
                added += cursor.rowcount
                existing += 1 - cursor.rowcount
            self.audit("worklist.import", "worklist", {"added": added, "existing": existing})
        return added, existing

    def worklist(self, day: str, text: str = ""):
        return self.query(
            """SELECT e.*,p.name,p.mrn,p.dob,p.issuer FROM encounters e
          JOIN patients p ON p.id=e.patient_id WHERE e.day=? AND (p.name LIKE ? OR p.mrn LIKE ?)
          ORDER BY e.appointment,p.name""",
            (day, f"%{text}%", f"%{text}%"),
        )

    def start_session(self, encounter_id: str) -> dict:
        with self.transaction():
            row = self.one(
                """SELECT e.*,p.name,p.mrn FROM encounters e JOIN patients p ON p.id=e.patient_id WHERE e.id=?""",
                (encounter_id,),
            )
            if not row:
                raise ValueError("Select a patient from the worklist first.")
            stamp = now()
            sid = uid()
            folder = (
                Path(stamp[:10])
                / f"{safe_name(row['name'])}_{safe_name(row['mrn'], 24)}_{row['patient_id'][:8]}"
                / f"Session_{datetime.fromisoformat(stamp):%H%M%S}_{sid[:8]}"
            )
            (self.root / folder).mkdir(parents=True, exist_ok=False)
            self.db.execute(
                "INSERT INTO sessions(id,patient_id,encounter_id,created,folder,study_uid) VALUES(?,?,?,?,?,?)",
                (sid, row["patient_id"], encounter_id, stamp, str(folder), "2.25." + str(int(uid(), 16))),
            )
            self.db.execute("UPDATE encounters SET state='in progress' WHERE id=?", (encounter_id,))
            self.audit("session.start", sid)
            return self.session(sid)

    def session(self, sid: str) -> dict:
        row = self.one(
            """SELECT s.*,p.name,p.mrn,p.dob,p.issuer,e.order_id FROM sessions s JOIN patients p
            ON p.id=s.patient_id LEFT JOIN encounters e ON e.id=s.encounter_id WHERE s.id=?""",
            (sid,),
        )
        if not row:
            raise ValueError("Unknown session.")
        return row

    def end_session(self, sid: str):
        with self.transaction():
            if self.one("SELECT id FROM media WHERE session_id=? AND status='pending'", (sid,)):
                raise ValueError("Wait for pending captures to finish.")
            session = self.session(sid)
            self.db.execute("UPDATE sessions SET ended=? WHERE id=?", (now(), sid))
            self.db.execute("UPDATE encounters SET state='completed' WHERE id=?", (session["encounter_id"],))
            self.audit("session.end", sid)

    def reserve(self, session_id: str, eye: str, kind: str, camera: str, metadata=None) -> CaptureTicket:
        if eye not in ("R", "L"):
            raise ValueError("Select Right or Left eye before capture.")
        if kind not in ("image", "video"):
            raise ValueError("Unsupported capture type.")
        if shutil.disk_usage(self.root).free < 100 * 1024 * 1024:
            raise OSError("Less than 100 MB of free storage remains. Free space before capturing.")
        with self.transaction():
            session = self.session(session_id)
            if session["ended"]:
                raise ValueError("This session has ended. Start a new session.")
            item = CaptureTicket(
                uid(), session_id, session["patient_id"], eye, kind, camera, now(), self.root / ".staging"
            )
            self.db.execute(
                """INSERT INTO media(id,patient_id,session_id,eye,kind,camera,created,status,metadata)
              VALUES(?,?,?,?,?,?,?,'pending',?)""",
                (
                    item.id,
                    item.patient_id,
                    item.session_id,
                    eye,
                    kind,
                    camera,
                    item.created,
                    json.dumps(metadata or {}),
                ),
            )
            self.audit("capture.reserve", item.id, {"session": session_id, "eye": eye})
            return item

    def fail(self, ticket: CaptureTicket, reason: str):
        with self.transaction():
            self.db.execute("UPDATE media SET status='failed' WHERE id=? AND status='pending'", (ticket.id,))
            self.audit("capture.failed", ticket.id, {"reason": reason[:400]})

    def finish(self, ticket: CaptureTicket, source: Path, metadata=None) -> dict:
        from .imaging import probe

        with self.lock:
            row = self.media(ticket.id)
            if row["status"] != "pending":
                raise ValueError("This capture is no longer pending; the file remains in staging for review.")
            if not source.is_file() or source.stat().st_size == 0:
                raise ValueError("The camera did not produce a complete file.")
            info = probe(source, ticket.kind)
            checksum = digest(source)
            suffix = source.suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
                raise ValueError("Unsupported filename extension.")
            session = self.session(ticket.session_id)
            dest = (
                Path(session["folder"])
                / ("Videos" if ticket.kind == "video" else "Originals")
                / f"{datetime.fromisoformat(ticket.created):%H%M%S_%f}_{ticket.eye}_{ticket.id}{suffix}"
            )
            final = self.path(dest)
            final.parent.mkdir(parents=True, exist_ok=True)
            combined = dict(row["metadata"])
            combined.update(metadata or {})
            combined.update(info.get("metadata", {}))
            with self.transaction():
                self.db.execute(
                    "UPDATE media SET path=?,sha256=?,width=?,height=?,duration=?,metadata=? WHERE id=?",
                    (
                        str(dest),
                        checksum,
                        info["width"],
                        info["height"],
                        info.get("duration", 0),
                        json.dumps(combined),
                        ticket.id,
                    ),
                )
            temp = final.with_suffix(final.suffix + ".part")
            with source.open("rb") as src, temp.open("xb") as out:
                shutil.copyfileobj(src, out)
                out.flush()
                os.fsync(out.fileno())
            if digest(temp) != checksum:
                raise OSError("Image copy verification failed. Source retained for recovery.")
            os.replace(temp, final)
            with self.transaction():
                self.db.execute("UPDATE media SET status='ready' WHERE id=?", (ticket.id,))
                self.audit("capture.saved", ticket.id, {"sha256": checksum})
            # Only our camera staging files are removed. Imports never remove vendor files.
            if source.resolve().is_relative_to((self.root / ".staging").resolve()):
                source.unlink(missing_ok=True)
            return self.media(ticket.id)

    def path(self, relative: str | Path) -> Path:
        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("File path is outside this archive.")
        return resolved

    def media(self, mid: str) -> dict:
        row = self.one(
            """SELECT m.*,p.name,p.mrn,p.dob,p.issuer FROM media m JOIN patients p ON p.id=m.patient_id WHERE m.id=?""",
            (mid,),
        )
        if not row:
            raise ValueError("Unknown image/video.")
        for key in ("tags", "edits", "annotations", "metadata"):
            row[key] = json.loads(row[key])
        return row

    def search(
        self, *, session_id=None, patient_id=None, text="", eye="", kind="", start="", end="", deleted=False
    ):
        where = ["m.status='ready'", "m.deleted_at IS NOT NULL" if deleted else "m.deleted_at IS NULL"]
        args = []
        for col, value in (
            ("m.session_id", session_id),
            ("m.patient_id", patient_id),
            ("m.eye", eye),
            ("m.kind", kind),
        ):
            if value:
                where.append(col + "=?")
                args.append(value)
        if start:
            where.append("substr(m.created,1,10)>=?")
            args.append(start)
        if end:
            where.append("substr(m.created,1,10)<=?")
            args.append(end)
        for token in text.split():
            where.append("(p.name LIKE ? OR p.mrn LIKE ? OR m.tags LIKE ? OR m.notes LIKE ?)")
            args.extend([f"%{token}%"] * 4)
        return self.query(
            "SELECT m.*,p.name,p.mrn,p.dob FROM media m JOIN patients p ON p.id=m.patient_id WHERE "
            + " AND ".join(where)
            + " ORDER BY m.created DESC",
            args,
        )

    def update_media(self, mid: str, *, tags=None, notes=None, edits=None, annotations=None, favourite=None):
        values = {
            "tags": tags,
            "notes": notes,
            "edits": edits,
            "annotations": annotations,
            "favourite": favourite,
        }
        with self.transaction():
            row = self.media(mid)
            if row["status"] != "ready" or row["deleted_at"]:
                raise ValueError("Restore this item before editing it.")
            for key, value in values.items():
                if value is None:
                    continue
                if key == "tags":
                    value = sorted({str(tag).strip().casefold() for tag in value if str(tag).strip()})
                if key in ("tags", "edits", "annotations"):
                    value = json.dumps(value)
                self.db.execute(f"UPDATE media SET {key}=? WHERE id=?", (value, mid))
            self.db.execute("UPDATE media SET revision=revision+1 WHERE id=?", (mid,))
            self.audit("media.update", mid, {"fields": [key for key, v in values.items() if v is not None]})

    def delete(self, ids: list[str], restore=False):
        with self.transaction():
            for mid in ids:
                self.db.execute(
                    "UPDATE media SET deleted_at=? WHERE id=? AND status='ready'",
                    (None if restore else now(), mid),
                )
                self.audit("media.restore" if restore else "media.delete", mid)

    def purge(self, ids: list[str]):
        with self.lock:
            for mid in ids:
                row = self.media(mid)
                if not row["deleted_at"]:
                    raise ValueError("Only items in Deleted items can be permanently removed.")
            for mid in ids:
                row = self.media(mid)
                self.path(row["path"]).unlink(missing_ok=True)
                with self.transaction():
                    self.db.execute(
                        "UPDATE media SET status='purged',edits='{}',annotations='[]' WHERE id=?", (mid,)
                    )
                    self.audit("media.purge", mid)

    def reassign(self, mid: str, session_id: str, eye: str, reason: str):
        if eye not in ("R", "L") or not reason.strip():
            raise ValueError("Eye and a correction reason are required.")
        with self.lock:
            old = self.media(mid)
            dest_session = self.session(session_id)
            if old["status"] != "ready":
                raise ValueError("Only saved media can be reassigned.")
            source = self.path(old["path"])
            target = self.path(
                Path(dest_session["folder"])
                / ("Videos" if old["kind"] == "video" else "Originals")
                / f"{datetime.fromisoformat(old['created']):%H%M%S_%f}_{eye}_{mid}{source.suffix}"
            )
            if target != source:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ValueError(
                        "The destination file already exists; inspect the archive before reassignment."
                    )
                with source.open("rb") as src, target.open("xb") as out:
                    shutil.copyfileobj(src, out)
                    out.flush()
                    os.fsync(out.fileno())
                if digest(target) != old["sha256"]:
                    target.unlink(missing_ok=True)
                    raise OSError("Reassignment copy verification failed; original retained.")
            with self.transaction():
                self.db.execute(
                    "UPDATE media SET patient_id=?,session_id=?,eye=?,path=?,revision=revision+1 WHERE id=?",
                    (dest_session["patient_id"], session_id, eye, str(target.relative_to(self.root)), mid),
                )
            if target != source:
                source.unlink(missing_ok=True)
                self.audit(
                    "media.reassign",
                    mid,
                    {
                        "old_session": old["session_id"],
                        "new_session": session_id,
                        "old_eye": old["eye"],
                        "new_eye": eye,
                        "reason": reason,
                    },
                )

    def recover(self):
        with self.transaction():
            for row in self.query("SELECT * FROM media WHERE status='pending'"):
                ready = bool(
                    row["path"]
                    and self.path(row["path"]).is_file()
                    and digest(self.path(row["path"])) == row["sha256"]
                )
                self.db.execute(
                    "UPDATE media SET status=? WHERE id=?", ("ready" if ready else "failed", row["id"])
                )
                self.audit("capture.recovered" if ready else "capture.interrupted", row["id"])
            self.db.execute(
                "UPDATE transfers SET state='failed',error='Interrupted; retry explicitly' WHERE state='sending'"
            )

    def save_preset(self, name: str, camera_key: str, settings: dict, instructions="", preset_id=None):
        if not name.strip():
            raise ValueError("Give the preset a name.")
        with self.transaction():
            self.db.execute(
                """INSERT INTO presets VALUES(?,?,?,?,?) ON CONFLICT(name,camera_key)
                DO UPDATE SET settings=excluded.settings,instructions=excluded.instructions""",
                (preset_id or uid(), name.strip(), camera_key, json.dumps(settings), instructions),
            )

    def all_tags(self):
        return sorted(
            {
                tag
                for r in self.query("SELECT tags FROM media WHERE status='ready' AND deleted_at IS NULL")
                for tag in json.loads(r["tags"])
            }
        )

    def backup(self, destination: Path) -> Path:
        destination = destination.expanduser().resolve()
        if destination.is_relative_to(self.root):
            raise ValueError("Choose a backup destination outside the live archive.")
        folder = destination / f"SlitlampBackup_{datetime.now():%Y%m%d_%H%M%S}_{uid()[:6]}"
        with self.lock:
            folder.mkdir(parents=True)
            target_db = sqlite3.connect(folder / "catalog.sqlite3")
            try:
                self.db.backup(target_db)
            finally:
                target_db.close()
            # Snapshot the catalogue and immutable-media list together, then release
            # the lock so a large archive copy cannot freeze the clinic interface.
            files = {
                row["path"]: row["sha256"]
                for row in self.query("SELECT path,sha256 FROM media WHERE status='ready'")
            }
            # Other files may be changing. Verify their copies; an incomplete backup
            # never receives a backup.json completion manifest.
            for subdir in (".inbox", ".staging", ".exports"):
                for source in (self.root / subdir).rglob("*"):
                    if source.is_file() and not source.is_symlink():
                        files[str(source.relative_to(self.root))] = None
        manifest = {"version": 1, "created": now(), "files": {}}
        for relative, expected in files.items():
            source = self.path(relative)
            if not source.is_file():
                raise FileNotFoundError(
                    "Backup incomplete: an archive file was removed during backup. Retry."
                )
            checksum = expected or digest(source)
            dest = folder / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            if digest(dest) != checksum:
                raise OSError("Backup incomplete: a file changed or its copy failed verification. Retry.")
            manifest["files"][relative] = checksum
        manifest["files"]["catalog.sqlite3"] = digest(folder / "catalog.sqlite3")
        (folder / "backup.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.set_setting("last_backup", {"time": now(), "path": str(folder)})
        return folder

    @staticmethod
    def restore(backup: Path, destination: Path):
        backup, destination = backup.resolve(), destination.resolve()
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Restore into an empty folder, never over an active archive.")
        manifest = json.loads((backup / "backup.json").read_text(encoding="utf-8"))
        for name, checksum in manifest["files"].items():
            source = (backup / name).resolve()
            target = (destination / name).resolve()
            if not source.is_relative_to(backup) or not target.is_relative_to(destination):
                raise ValueError("Invalid path in backup manifest.")
            if digest(source) != checksum:
                raise ValueError(f"Backup verification failed for {name}.")
        destination.mkdir(parents=True, exist_ok=True)
        for name in manifest["files"]:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / name, target)

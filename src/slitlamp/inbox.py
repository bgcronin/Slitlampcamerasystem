"""Vendor-folder intake never guesses a patient from the UI's current selection."""

from pathlib import Path
import shutil
import time

from .catalog import digest
from .imaging import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from .models import now, uid


class FolderInbox:
    def __init__(self, catalog):
        self.catalog = catalog
        self.seen = {}

    def scan(self, folder: Path, stable_seconds=3.0):
        folder = folder.resolve()
        if folder.is_relative_to(self.catalog.root) or self.catalog.root.is_relative_to(folder):
            raise ValueError("The watched folder must be separate from the application archive.")
        if not folder.is_dir():
            raise ValueError("The watched folder is not available.")
        found = 0
        for path in folder.iterdir():
            if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS or not path.is_file():
                continue
            stat = path.stat()
            state = (stat.st_size, stat.st_mtime_ns)
            previous = self.seen.get(path)
            if not previous or previous[0] != state:
                self.seen[path] = (state, time.monotonic())
                continue
            if not stat.st_size or time.monotonic() - previous[1] < stable_seconds:
                continue
            try:
                checksum = digest(path)
                if self.catalog.one("SELECT id FROM inbox WHERE path=? AND sha256=?", (str(path), checksum)):
                    continue
                ident = uid()
                dest = self.catalog.root / ".inbox" / (ident + path.suffix.lower())
                shutil.copy2(path, dest)
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != state or digest(dest) != checksum:
                    dest.unlink(missing_ok=True)
                    self.seen.pop(path, None)
                    continue
                with self.catalog.transaction():
                    self.catalog.db.execute(
                        "INSERT INTO inbox(id,path,sha256,created) VALUES(?,?,?,?)",
                        (ident, str(path), checksum, now()),
                    )
                    self.catalog.audit("inbox.received", ident)
                found += 1
            except (PermissionError, FileNotFoundError):
                continue  # Vendor still owns or is replacing the file; retry later.
        return found

    def file(self, row: dict) -> Path:
        return self.catalog.root / ".inbox" / (row["id"] + Path(row["path"]).suffix.lower())

    def assign(self, inbox_id: str, session_id: str, eye: str):
        row = self.catalog.one("SELECT * FROM inbox WHERE id=? AND state='review'", (inbox_id,))
        if not row:
            raise ValueError("This inbox item has already been assigned.")
        path = self.file(row)
        ticket = self.catalog.reserve(
            session_id,
            eye,
            "video" if path.suffix in VIDEO_EXTENSIONS else "image",
            "Vendor file import",
            {"inbox_id": inbox_id},
        )
        try:
            result = self.catalog.finish(ticket, path)
        except Exception as exc:
            self.catalog.fail(ticket, type(exc).__name__)
            raise
        with self.catalog.transaction():
            self.catalog.db.execute("UPDATE inbox SET state='assigned' WHERE id=?", (inbox_id,))
            self.catalog.audit(
                "inbox.assigned", inbox_id, {"media": ticket.id, "session": session_id, "eye": eye}
            )
        return result

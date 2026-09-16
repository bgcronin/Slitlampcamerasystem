# Architecture

## Modules

- `catalog.py`: local SQLite data model, immutable capture tickets, staged media commit, audit, presets, soft deletion, backup/restore.
- `worklist.py`: CSV/XLSX parsing, explicit date handling and mapping.
- `imaging.py`: colour-aware image loading, adjustments, annotations, rendering, exports and video inspection.
- `inbox.py`: stable-file detection and explicit patient assignment for vendor output.
- `cameras/base.py`: signal-based camera contract.
- `cameras/canon.py`: Windows x64 EDSDK ABI, dedicated COM worker, model capability queries and transfer callbacks.
- `cameras/windows.py`: Qt native camera pipeline and recorder.
- `cameras/simulator.py`: visibly simulated pattern and video source.
- `cameras/recorder.py`: bounded frame queue and FFmpeg encoding for preview streams.
- `pacs.py`: Secondary Capture objects, persisted transfer jobs, C-STORE/C-ECHO and Modality Worklist query.
- `ui/`: Qt Widgets application, image editor, worklist/preset/settings dialogs.

## Capture transaction

1. Patient and session must already exist; laterality must be explicit.
2. `reserve` creates an immutable ticket and a pending database record before triggering the camera.
3. The camera writes a staging file and returns the original ticket, not the UI's current selection.
4. `finish` validates the file, records its destination and hash, writes a temporary archive copy, verifies it, atomically renames it, then marks the record ready.
5. After a crash, a pending record is recovered only if its final file and expected hash agree. Otherwise it becomes failed and staging is retained for review.

Files are never inferred to belong to a patient by capture time alone. Vendor-folder and unsolicited Canon captures enter a separate inbox for explicit assignment. Following a Canon timeout, new direct captures require reconnecting so late files cannot be assigned to a new request.

## Data integrity

Original media bytes are immutable except deliberate permanent deletion. Edits and annotation coordinates are stored in SQLite and rendered into separate export copies. Tags, notes, annotations and audit entries travel with the database backup.

The database uses WAL, full synchronous commits and foreign keys. A workstation-level lock prevents simultaneous application instances on one archive. The application is not a multi-PC shared-database service.

The image editor stores annotations in original-image coordinates. Rendering applies photometric adjustments, annotations, crop and rotation in that order, ensuring annotations move with image content.

## Camera extension contract

Implement `Camera` and expose accurate capabilities through `CameraInfo`. Camera signals must return a `CaptureTicket` unchanged. Never report success until the device produced a file. A new proprietary Mizar adapter must use a documented, licensed vendor API; do not emulate unsupported functions or treat generic USB detection as acquisition support.

Background work uses Qt's thread pool; Canon native calls stay on their own thread. Long transfers retain their identity even when the UI is reviewing historical records.

## Deployment

The installer is built on a Windows runner. Python, Qt and the application libraries are bundled by PyInstaller. Canon/CSO binaries are installed separately under vendor terms. Patient archives live outside the application installation folder and are preserved on uninstall.

# Slitlamp Studio

A local Windows desktop application for slit lamp photographs and videos. Patients come from a daily worklist; each capture is tied to a patient, session and eye before acquisition. Files stay in a date/patient/session archive on the PC.

**Status:** working application code with automated workflow tests and Windows packaging. Real camera acceptance testing is still required. The CSO Mizar proprietary interface is not publicly verified; do not interpret the Windows camera adapter as a claim of universal Mizar compatibility.

## Included

- CSV/XLSX worklist mapping and preview, manual patients, duplicate/conflict checks.
- Capture sessions with persistent name, MRN, DOB and eye selection.
- Canon EDSDK still capture, live view and recording of the live-view stream.
- Native Windows camera capture/video for devices exposed by their installed drivers.
- Patient-reviewed import inbox for Phoenix/vendor exports, plus manual media import.
- Automatic folders, original-file preservation, integrity hashes and crash recovery records.
- Session gallery, previous visits, search, tags, notes and favourites.
- Non-destructive image adjustments, crop/rotation and editable arrows, shapes, text and freehand annotations.
- Camera-specific presets with explicit manual slit lamp setup instructions.
- Video playback, seeking and frame extraction.
- Quick recoverable deletion, undo, restoration and deliberate permanent removal.
- Real file drag-and-drop into Explorer, compatible email clients/webmail and other receiving applications.
- Original/edited/annotated exports; direct DICOM Secondary Capture C-STORE, retry queue, C-ECHO and Modality Worklist query.
- Consistent catalogue/media backups, verified restore, audit history and image reassignment.
- A separate demonstration mode containing fictional patients and a generated test pattern.

## Target cameras

| Device | Implemented route | What remains to verify |
| --- | --- | --- |
| Canon EOS 200D II (250D / Rebel SL3 regional equivalents) | Official Windows x64 Canon EDSDK | Exact SDK/firmware, live view, exposure controls, transfer and disconnect behaviour |
| Canon EOS 60D | Official Windows x64 Canon EDSDK | Same hardware acceptance checks |
| Canon EOS 70D | Official Windows x64 Canon EDSDK | Same hardware acceptance checks |
| CSO Mizar | Windows camera backend **if exposed by the installed driver**; otherwise Phoenix export/import | Device/driver identity, public/vendor SDK access, full resolution, video and joystick behaviour |

Canon's proprietary SDK is obtained separately from Canon. DLLs and patient data are excluded from this repository. Canon video in this version is recorded from **live view**, not a promise of native full-resolution in-camera movie capture. Import native movies when that quality is needed.

See [camera setup and compatibility](docs/CAMERAS.md).

## Run on Windows

### Packaged application

The [Windows workflow](.github/workflows/windows.yml) runs tests and produces a portable application and, when Inno Setup is available, an installer. Download the `SlitlampStudio-Windows-x64` artifact from a successful run under the repository's **Actions** tab.

Run `SlitlampStudio.exe`, or use `SlitlampStudio-Setup-0.1.0.exe` if included. The package is unsigned; the clinic should review and approve its installation. The program does not bundle camera drivers or Canon SDK libraries.

### Run from source

Install **64-bit Python 3.12** on the capture PC, then open PowerShell in this repository:

```powershell
./scripts/run_windows.ps1 -Demo
```

For an ordinary archive:

```powershell
./scripts/run_windows.ps1
```

Or choose a specific archive:

```powershell
./scripts/run_windows.ps1 -DataDir 'D:\Clinical Images\Slit Lamp Photos'
```

The first run installs the pinned application dependencies into `.venv`. Subsequent launches work offline. If local PowerShell policy prevents running scripts, use the equivalent commands:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m slitlamp --demo
```

The default archive is the Windows Pictures location plus `Slit Lamp Photos`. Demo mode uses `Slitlamp Studio Demo`. `--choose-archive` offers a folder chooser. A lock prevents two instances from opening the same archive.

## First clinic workflow

1. Configure the camera integration and a separate backup destination in **Settings**.
2. Import the daily worklist; map columns, choose the date format and review the preview. An example with fictional patients is in [examples/worklist.csv](examples/worklist.csv).
3. Double-click the patient and verify name, MRN and DOB.
4. Connect the camera and select Right or Left eye.
5. Capture with **F5**. Start/stop video with **F6**. Shortcuts are configurable.
6. Select photographs to review, annotate, adjust, tag or delete. Return to **Live view** before capturing again.
7. Select an export version and drag thumbnails into the destination, or use **Export**.
8. End the session and select the next patient.

See the [user guide](docs/USER_GUIDE.md), [architecture](docs/ARCHITECTURE.md) and [acceptance checklist](docs/ACCEPTANCE.md).

## Development

The UI uses Python/PySide6, SQLite and Pillow. This replaces the specification's suggested C#/WPF stack while retaining a native desktop window, Windows SDK access and OS file drag-and-drop. The same workflow can be tested on a development Mac/Linux system; Canon direct capture remains Windows-specific.

```sh
python3.12 -m venv .venv
# Windows: use .venv\Scripts\python.exe instead
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install pytest pytest-qt ruff
PYTHONPATH=src .venv/bin/python -m slitlamp --demo
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
```

Build an installable Windows application on **Windows**, not by cross-compiling from macOS:

```powershell
./scripts/build_windows.ps1
```

Inno Setup 6 creates the installer; otherwise the script produces a portable folder. Uninstalling the app preserves the separate patient archive.

## Current limits

- No hardware has been declared verified solely from simulation or unit tests. Complete the acceptance checklist using all four actual cameras.
- Mizar direct integration still needs a driver diagnostic or manufacturer SDK. No undocumented CSO API is invented.
- Canon direct capture expects one connected EOS body at a time. Use JPEG or RAW+JPEG for review/editing. RAW files are preserved but RAW development is not implemented.
- Physical camera/joystick events that cannot be reliably linked to an application capture go to the review inbox. Use the capture shortcut or a keyboard-emulating pedal for direct patient-bound capture.
- The DICOM exporter uses RGB Secondary Capture. Ophthalmic Photography SOP support, DICOMweb, encrypted DICOM transport and direct video DICOM transfer are not implemented. Use the clinic's approved network and validate its PACS conformance.
- Drag-and-drop acceptance is controlled by the receiving program. File export is always available as a fallback. The app never sends email automatically.
- Protection at rest uses clinic-managed Windows accounts, folder permissions and disk/backup encryption; the app does not itself encrypt SQLite or media files.
- This release is for one archive on one capture workstation. Multi-user shared editing is not implemented.

## Dependency licences

See [third-party notices](docs/THIRD_PARTY.md) before redistributing packaged builds. This repository does not include proprietary camera SDK binaries.

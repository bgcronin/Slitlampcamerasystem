# Verification record

## Development environment

- Python 3.12, PySide6 6.11.2, macOS development host.
- All test patients and captures are fictional/generated.
- No physical Canon or Mizar camera was attached during development.
- A Windows GitHub Actions job separately tests and builds the target-platform package.

## Checks run locally

- 28 automated tests passed, including the Qt desktop workflow, annotation persistence, video encoding/decoding, backup restoration and a localhost DICOM C-STORE receiver with retry.
- Ruff static checks passed.
- Python source compilation passed.
- The demonstration application was launched and its captured window inspected; a screenshot is saved in `docs/screenshots/demo.png`.

The macOS environment marks downloaded Qt plugin files hidden. Their hidden flags were cleared in the local development environment before UI tests. This is a local runtime issue and no such workaround is built into the Windows application.

## Still requiring target-environment verification

- All real camera capture, live view, presets and disconnection tests listed in `CAMERAS.md`.
- Mizar's installed driver interface and Phoenix export functionality.
- External drag-and-drop into the clinic's particular email, webmail and PACS applications.
- The clinic's worklist/PACS network settings and DICOM conformance.
- Installer behaviour and clinic Windows access/encryption/backup configuration.

Automated tests and a successful Windows build do not constitute camera or clinical-workflow acceptance. Record the exact equipment/software versions and results in `ACCEPTANCE.md` before marking an integration verified.

# Acceptance and verification

## Automated checks

Run `python -m pytest -q` and `python -m ruff check src tests scripts` with the development dependencies installed. The Windows workflow repeats these checks and packages the application only after they pass.

Tests cover:

- Same-name patients, MRN preservation, duplicate worklists and all-or-nothing conflict handling.
- Immutable capture context, eye selection, pending-session guards and file uniqueness.
- Original integrity, rendered annotations, crop/rotation, tags and reversible deletion.
- Backup/restore with checksums and refusal to overwrite active archives or follow traversal paths.
- Recovery after interrupted capture writes.
- Vendor-file stabilisation, duplicate intake and explicit patient assignment.
- Playable video recording and frame extraction.
- DICOM identity/pixels and persisted SOP identifiers; loopback C-STORE receiver and retries.
- Desktop demo capture → gallery → tags → delete/restore, and annotation save/reload/undo.
- Canon ABI structure sizes, missing SDK feedback and reconnect requirement after interrupted capture.

These checks use fictional patients and generated media. They do not verify physical cameras or a clinic's actual PACS/email client.

## Required on the target Windows PC

Record Windows, driver, SDK and firmware versions for **each of EOS 200D II, EOS 60D, EOS 70D and CSO Mizar**.

1. Connect the actual device and confirm the name and advertised capabilities.
2. Capture a full-resolution photograph and compare with the manufacturer's software for dimensions, colour, orientation and detail.
3. Test both eyes, patient changes, rapid capture, slow transfer, unplug/reconnect and camera-busy conditions.
4. Verify every configured preset's real readback and resulting exposure/white balance. Unsupported controls must be reported.
5. Record video, stop, restart the app and play the file. Verify timing, dimensions and source-quality label. Test unplugging during a recording.
6. For Mizar, verify the driver interface or the installed Phoenix export workflow. Test the joystick separately; do not assume it generates an application-bound capture.
7. Check keyboard/pedal capture in the intended clinic arrangement.
8. Annotate, crop, rotate and export, then compare the rendered result with its preview and verify the original hash.
9. Drag one and multiple files into Explorer, the actual desktop email client/webmail and the actual PACS-style importer. Verify delayed attachment access and destination patient selection.
10. Test DICOM import with the PACS administrator, including identity, laterality, acknowledgement and duplicate retry behaviour.
11. Simulate low storage/failed writes and verify clear failure handling without false Saved status.
12. Restore a backup into a separate folder and verify images, tags, notes, annotations and patient associations.

Do not mark a camera verified until its actual checklist is completed. Keep failures and remaining restrictions in the compatibility register.

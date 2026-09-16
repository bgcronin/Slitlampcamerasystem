# User guide

## Patients and sessions

Import CSV or `.xlsx` using **Import list**. Choose the column for name, MRN and DOB and select the correct date order. Leading zeros in text MRNs are retained; an Excel numeric cell with a `000000` format is preserved as displayed. Numeric identifiers with lost zeros cannot be reconstructed without that formatting. Save legacy `.xls` as `.xlsx` first.

The import is all-or-nothing if demographic conflicts are found. Patient identity uses MRN plus issuer. Two patients with the same name remain separate. Reimporting identical appointments does not duplicate them.

Double-click a patient to start a session. Confirm the banner and choose Right or Left before capturing. End the session when finished. A separate same-day visit creates a separate folder.

## Capture and presets

Connect a camera, use **Capture photograph / F5**, and wait for **Saved**. A camera preview is not proof that an image is saved. The app prevents patient/eye changes while saving or recording.

Save a named preset after setting camera values, or edit a preset using the controls offered by the driver. For Canon, supported exposure values come from the body. Presets belong to the detected camera. Unsupported values and failed writes are reported.

Write instructions for physical magnification, illumination filter and slit width in the preset. The program does not turn physical lamp controls automatically.

## Video

F6 starts/stops recording. The red indicator shows elapsed time. Wait for finalisation and saving before changing patient. Audio is disabled.

Select a video thumbnail to play, pause or seek. **Save video frame** creates a linked still from the displayed time for the active session. That still can be annotated and exported like any other photograph.

Canon recordings use live-view resolution. For higher-quality native movies, record in the camera/vendor application and import the file.

## Editing and annotations

Select one photograph and choose **Edit / annotate**. Available tools include arrows, circles/ellipses, rectangles, freehand and text. Use Select to move annotations; use Smaller/Larger to resize a selection. Change colour, line thickness or text size before drawing. Undo/redo covers annotations and adjustments.

Brightness, contrast, white balance and sharpening are reversible. Crop and rotation are shown in **Output preview**. The annotation canvas keeps marks attached to original image coordinates, so marks follow the same image content through those changes. The Original tab shows the untouched source.

Choose Save to persist edits and annotations. Original files are never overwritten. RAW-only photographs are archived but cannot be developed/annotated in this version; use JPEG or RAW+JPEG for the review workflow.

Edited exports use 8-bit sRGB. Higher-bit-depth originals and their embedded profiles remain preserved in the original files.

## Tags and search

Enter comma-separated tags and a note, then **Save details**. For multiple selected images, **Add tags to selected** adds the tags without replacing each image's existing tags. Search words are combined: an image must match every word in its name/MRN/tags/notes. Eye, media type and date range narrow the results.

Use Current session, Patient history, All patients or Deleted items. Reviewing another patient does not change the active capture patient. Return to Live view before taking another photograph.

## Quick deletion

Select one or several poor captures and press Delete or click **Delete selected**. They leave the gallery immediately. Use **Undo delete** for the last batch or select Deleted items and restore any item.

Recoverable deletion does not free disk space. **Remove permanently** confirms removal of selected archive originals and their saved editing records. Export copies, email attachments, PACS copies and backups remain outside this action.

## Drag into email or folders

Choose Original, Edited without annotations or Edited with annotations. Select one or several thumbnails and drag into Explorer, an email compose window or a compatible attachment area. The app prepares real image files and only offers a copy operation. It never sends the email.

The chosen export version is visible above Export. Use **Preview** to inspect an example or **Export** to save to a folder when drag-and-drop is not accepted by the destination. Confirm patient matching inside the receiving PACS-style application.

Export copies are retained in the archive's `.exports` folder, including after the application exits. They are not automatically removed after a drag because some email clients read attachments later. Open the export folder from File to manage old copies only after attachments/uploads are complete.

## Phoenix/vendor imports

Set a dedicated vendor export folder in Settings. New stable files enter Import inbox without a guessed patient assignment. Preview the file, start the correct patient session, choose the eye in the inbox and confirm the assignment. Exported source files remain with the vendor application.

## Backup and restore

Configure a backup destination outside the live archive. An hourly interval can be selected; 24 hours is the default. Backups occur while the app is open. The app does not run a background Windows service when closed.

**Archive → Back up now** creates a catalogue snapshot and copies original media, edits/annotations (stored in the catalogue), inbox and export files. A checksum manifest marks successful completion. A failed or incomplete folder without `backup.json` is not a valid restore point.

Restore into an empty folder using **Archive → Restore backup**. Open the restored folder with the Choose archive shortcut or `--data-dir`. Do not restore over the currently open archive. Store archives and backups on clinic-approved encrypted storage with appropriate Windows access permissions.

## PACS

Ask the PACS administrator for hostname, port and called/calling AE titles and confirm acceptance of RGB Secondary Capture. Configure Settings, test the connection, select images, then Send to PACS. Review the destination and selection before sending.

The queue shows queued, sending, failed or acknowledged. Retry failed transfers from the queue; the same DICOM object identifiers are retained. Acknowledged means the receiver accepted the object, not that long-term storage commitment has been obtained. Local originals are retained.

Video DICOM, DICOMweb and encrypted DICOM transport are not implemented. Use an approved clinic network/VPN and file export for unsupported media. Worklist querying can specify a different server endpoint.

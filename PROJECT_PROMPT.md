# Project prompt: Windows slit lamp imaging application

## Instructions to the developer or coding assistant

Build a Windows desktop application for an ophthalmologist to capture, review, organise, annotate, enhance, search and export photographs and videos from a slit lamp camera connected to a PC by USB.

Use this document as the unified product specification. All features marked **Version 1** belong in the first usable release, subject to verified hardware capabilities. The later-features section is a separate backlog.

Prioritise a fast clinic workflow, correct patient identification, reliable saving and preservation of original images. Use plain language in the interface. Continue independent development with fictional patients and a simulated camera while equipment details are being confirmed. Clearly identify simulations and unverified integrations.

## 1. Deployment and technical approach

**Version 1**

- Deliver a normal Windows desktop program with an installer, desktop shortcut and uninstall support that preserves patient data by default.
- Connect to cameras locally over USB. Support a compatible Canon camera and a dedicated CSO slit lamp camera through separate integrations.
- Keep photographs and videos as ordinary files on the PC, with a local searchable catalogue for patient details, sessions, tags and file associations.
- Let core capture, review, tagging and editing work offline. Do not require a cloud account or website hosting.
- A suggested starting point is C# with a supported .NET release, WPF for the interface and SQLite for the local catalogue. Validate that choice against the actual camera SDKs and driver architecture before committing to it.
- Keep camera control, worklist import, storage, image editing and export in separate modules.
- Use the Windows Pictures location as the initial storage suggestion, with a configurable clinic-approved folder. Resolve the actual Windows location rather than hard-coding an English folder path.
- Use automated backup to a separate approved destination. Local storage and backup must be configurable independently.
- If multi-PC access is added later, introduce a central application service and shared archive. Do not have several PCs directly edit the same SQLite file over a network share.

## 2. Information to establish at project start

**Confirmed target cameras:** Canon EOS 200D II, Canon EOS 60D, Canon EOS 70D and CSO Mizar. Implement and validate these specific models first. Compatibility with additional cameras must be based on verified SDK/driver capabilities.

Record the following as supplied, unknown or verified. Ask only for information that cannot be established from available documentation or the project environment.

| Item | Detail needed |
| --- | --- |
| Canon camera | Exact model, firmware, installed software and available SDK |
| CSO equipment | Slit lamp model, camera model, driver, existing imaging software and version |
| Computer | Windows version, processor architecture, memory and available storage |
| Capture trigger | On-screen button, camera/slit lamp button, keyboard and any foot pedal |
| Worklist | A fictionalised sample CSV/Excel file or details of the electronic source |
| Receiving imaging system | PACS-style product name/version, accepted files and available interfaces |
| Email | Desktop email client and/or webmail service and browser to test |
| Storage | Preferred image folder, backup destination and applicable access permissions |

Do not invent camera functions, vendor APIs, worklist endpoints or PACS support. Missing integration details should not block development of the independent application features.

## 3. Prove camera compatibility first

**Version 1 prerequisite**

- Check official SDK availability, licence terms, driver requirements and supported functions for each exact camera.
- Use Canon EDSDK where the model supports the required operations.
- For CSO, use a documented manufacturer-supported interface if available. Confirm access with the supplier where necessary.
- Do not assume a USB camera exposes a standard webcam interface.
- Verify still photography, live view and video recording separately. A camera may expose different capabilities for each.
- Demonstrate connection, full-resolution still capture, transfer to disk and recovery after unplugging/reconnecting each camera.
- Distinguish full-resolution photographs from live-view frames. Identify the actual resolution and quality of video obtained through the supported interface.
- Report incompatible drivers, another application holding the camera connection and unsupported controls clearly.

### Fallback acquisition

If direct control is unavailable, investigate importing files saved or exported by the manufacturer's existing software into a monitored folder.

- Verify that the vendor software supports a suitable workflow before promising it.
- Wait for files to finish writing before importing; detect duplicate imports.
- Preserve the source file and record where the import came from.
- Bind imports to a reliably identified patient/session, such as an explicit session-specific import destination or trusted source metadata.
- Put ambiguous or delayed imports into a review queue. Never assign them merely to whichever patient is currently selected.
- State which functions, such as capture controls or video, still require the manufacturer’s software.

Maintain a compatibility table with separate statuses for **verified on hardware**, **implemented but unverified**, **simulated**, **unsupported** and **requires vendor information**.

## 4. Daily patient worklist and identification

**Version 1**

- Import daily worklists from CSV and Excel files.
- Provide column mapping, a preview and understandable validation errors before committing an import.
- Include name, medical record number (MRN), date of birth and, where supplied, appointment time and encounter/order identifier.
- Treat MRNs as text and preserve leading zeros. Handle date formats explicitly rather than guessing ambiguous dates.
- Detect duplicate worklist rows and flag conflicting demographic details. Re-importing a worklist must not duplicate patients or lose previous sessions.
- Use stable internal patient identifiers linked to the MRN and issuing organisation where relevant; never identify a patient solely by name or folder name.
- Show an easy-to-select list with name, MRN, DOB and waiting/completed status.
- Support search by name or MRN and sorting by appointment time or name.
- Allow manual patient entry for unscheduled patients with validation and duplicate checks.
- Keep the active patient's name, MRN and DOB prominently visible during capture and review.
- Require deliberate patient/session selection before capture. Provide an obvious **End Session / Next Patient** action.
- Record right eye or left eye for every photograph and video. Make missing laterality explicit and require resolution before routine export; never infer it from image appearance.

Design a separate connector for an electronic worklist, such as DICOM Modality Worklist, once the clinic's source is known. Preserve supplied order and encounter identifiers for later export.

## 5. Main screen and still capture

**Version 1**

Suggested layout:

- **Left:** today's patients and search.
- **Centre:** camera live view or the selected photograph/video.
- **Bottom:** the active patient's current-session gallery.
- **Right:** eye selection, capture preset, tags, notes and editing controls.

Provide a large **Capture** button, configurable keyboard shortcut and supported camera/slit lamp trigger events. Keep the interface usable on a normal clinic monitor with large, clear controls.

- Show connection, capture, transfer and save status separately.
- Offer an optional sound after successful saving.
- Bind each capture to its patient, session and eye when the capture starts. A delayed transfer must retain that association after a patient change.
- Handle pending transfers explicitly before ending or switching sessions.
- Show **Saved** only after the file has been successfully written. Display failures prominently and support recovery without silently losing or misassigning images.
- Keep the interface responsive during transfer, thumbnail generation and export.

## 6. Capture presets

**Version 1**

Allow users to create, name, save, duplicate, edit and delete capture presets, accessible with one click beside live view.

Suggested starting names are **Diffuse illumination**, **Optical section**, **Retroillumination**, **Fluorescein / cobalt blue** and **External eye / lids**. Do not invent universal exposure values; configure and verify values with the actual equipment.

- Save supported camera settings, such as exposure, shutter speed, aperture where available, ISO/gain and white balance.
- Include supported video resolution and frame-rate settings where applicable.
- Keep presets separate for different camera models and capture modes.
- Show the active preset and whether the user has modified its settings.
- Report unsupported settings or failed application of a preset. Do not indicate success when settings were only partially applied.
- For physical slit lamp settings that cannot be controlled electronically, show brief manual setup instructions, such as magnification, filter and slit width.
- Do not imply that choosing a software preset automatically changes physical illumination or magnification unless that capability is verified.

## 7. Video recording

**Version 1, where verified camera interfaces permit it**

- Provide large **Start Recording** and **Stop Recording** buttons and a configurable keyboard shortcut.
- Show a clear recording indicator, elapsed time and storage status. Disable audio by default.
- Bind the video to the selected patient, session and eye at recording start. Prevent patient changes during recording.
- Save videos automatically alongside the session's photographs.
- Show a thumbnail, video icon and duration in the gallery.
- Provide playback, pause, seeking and full-screen viewing, plus tags, notes, export and deletion.
- Preserve the original recorded file. Prefer MP4 for sharing where practical, with any conversion saved as a separate export.
- Allow a frame to be extracted as a separate photograph, linked to its source video and timestamp. The extracted frame can use normal image annotation and editing tools.
- If simultaneous still capture and video recording is unsupported, make that limitation clear in the controls.
- Handle low disk space, camera disconnection and recording errors. On restart, identify incomplete recordings and attempt recovery where possible; report any unrecoverable content accurately.
- Verify that stopped recordings are finalised and playable. Do not claim video compatibility with PACS without testing the destination.

## 8. Automatic storage and catalogue

**Version 1**

Create date folders, patient subfolders and separate sessions automatically. Example using fictional data:

```text
Slit Lamp Photos/
  2026-09-16/
    Smith_Jane_MRN001234/
      Session_093015_a81f/
        Originals/
        Edited/
        Videos/
        Exports/
```

- Use the clinic's local session date and retain that session folder if a transfer finishes later.
- Include MRN alongside the patient name to distinguish people with identical names. Handle invalid Windows filename characters and path-length constraints.
- Use unique filenames containing capture time, eye and a unique image/video identifier. Never overwrite a previous capture.
- Preserve original camera files unchanged. Store edits, annotations and export copies separately, linked to their originals.
- Store patient/session association, laterality, timestamps, camera, preset, tags, notes and file paths in the searchable local catalogue.
- Keep separate same-day sessions distinct while allowing review of all that patient's visits.
- Provide **Open patient folder** and **Show in Explorer**.
- Detect missing files and recover consistently from interrupted writes or application closure. Reconcile files and catalogue entries without silently inventing associations.
- Warn clearly about insufficient space or inaccessible storage.

## 9. Photo browser, review and image enhancement

**Version 1**

- Show new captures in the current-session gallery as soon as they are saved.
- Provide thumbnails, full-screen viewing, zoom, pan, favourites and multi-selection.
- Make previous visits accessible without mixing them into the current capture session.
- Show patient, date, eye and original/edited status clearly when reviewing images.

Provide non-destructive crop, straighten, rotate, brightness/exposure, contrast, white balance and carefully controlled sharpening, with undo/redo, reset and original-versus-edited comparison.

- Preserve source resolution and colour information where supported.
- Record edit operations and clearly identify edited versions.
- Do not silently mirror photographs or change laterality.
- Do not use generative fill, invented detail or automatic removal of clinical features.
- Treat user-entered tags and notes as user labels, not automated diagnoses.

## 10. Annotations

**Version 1**

Provide arrows, circles, ellipses, rectangles, freehand drawing and text labels.

- Allow adjustable colour, line thickness and text size.
- Support selection, movement, resizing, deletion and undo/redo.
- Store annotations as a separate editable layer, linked to the correct image version, with show/hide controls.
- Preserve annotation positioning after zooming and when applying compatible crop/rotation operations. Make behaviour explicit when edits change the annotated image geometry.
- Keep annotations editable after closing and reopening the application.
- Never burn annotations into the original photograph.
- Offer export of the original, the edited image without annotations, or the edited image with annotations rendered into it.
- Preview the actual export result before a normal export, and keep the selected export mode visible for quick drag-and-drop.

## 11. Quick deletion of poor-quality captures

**Version 1**

- Provide a visible **Delete** button, Delete-key support and multi-selection for bulk removal of photographs and videos.
- Remove deleted items from the active gallery immediately and offer an easy **Undo** action.
- Initially move items into an application-managed, recoverable **Deleted items** area. Keep their originals, related edits, annotations and metadata together.
- Exclude deleted items from normal searches and exports.
- Provide a separate view for restoring items or permanently deleting them.
- Require confirmation for permanent deletion, clearly identifying the affected items. Keep ordinary recoverable deletion quick.
- Explain that recoverable deletion does not yet free disk space. Show retained space and allow deliberate emptying of Deleted items.
- Record deletion/restoration actions. Permanent local deletion must not claim to remove copies already exported or stored in backups.

The original-preservation requirement permits deliberate permanent deletion through this workflow; it prohibits edits or exports from silently overwriting or removing originals.

## 12. Tags, notes and search

**Version 1**

- Allow multiple custom tags per photograph or video and optional session-level tags.
- Suggest existing tags during entry to reduce spelling variants.
- Apply tags to multiple selected items at once.
- Support free-text notes.
- Example tags include cornea, cataract, pterygium, keratoconus, blepharitis, postoperative and teaching.
- Search across all patients and dates using name, MRN, eye, date range, media type, tags and notes, including combinations of filters.
- Persist tags and notes after restart and include them in backups and restoration.

## 13. Drag-and-drop into email, folders and other applications

**Version 1**

Allow dragging one or several selected photographs directly from the application's photo browser/gallery, search results and session view into:

- Email drafts as attachments.
- Windows Explorer folders and accessible network folders.
- Other applications that accept image files, including the clinic's PACS-style application where compatible.
- Webmail attachment areas where the browser and website support file drops.

Requirements:

- Transfer actual full-resolution image files, not thumbnails, screenshots or internal database links.
- Support original, edited and edited-with-annotations export modes. Remember the preference and keep it visible beside the gallery.
- Prepare required export files automatically so users do not have to save them manually first.
- Preserve the patient archive; dragging must copy, not move, the originals.
- Use unique export filenames. Avoid silent overwriting in application-managed exports; when another application controls destination naming, respect its collision handling and document limitations.
- Keep generated export files available long enough for the receiving application to finish reading or attaching them. Use a documented cleanup policy that does not break pending attachments.
- Provide **Export selected images**, **Open export folder** and **Show in Explorer** as fallback workflows.
- Adding attachments must never automatically send an email.
- Do not label a drag operation as confirmed PACS receipt or successful email delivery.
- Verify single-file and multi-file behaviour in the actual Windows email client, webmail/browser, Explorer and imaging system selected by the clinic. Document unsupported destinations.

## 14. File export and optional direct PACS integration

### Version 1: file export

- Export original files or selected image versions as JPEG and lossless PNG/TIFF where appropriate.
- Support batch selection and an **Export to Folder** alternative to dragging.
- Show which versions, formats and filenames will be exported.
- Preserve local originals after any export.
- Test the receiving PACS-style system's actual file-import workflow, including how the operator selects the destination patient. A filename alone is not reliable patient matching.

### Integration phase: direct PACS transfer

Implement once the actual receiving system's interface and requirements are established.

- Obtain its DICOM conformance statement and connection requirements.
- Choose supported image objects, preferably ophthalmic photography where compatible, and satisfy the required metadata. Do not claim that renaming a JPEG creates DICOM.
- Preserve patient ID, DOB, laterality, acquisition time and available order/encounter identifiers.
- Use valid Study, Series and Instance identifiers and appropriate original/derived image information.
- Implement DICOM C-STORE or DICOMweb STOW-RS according to destination support.
- Provide a transfer queue, per-item status, clear failure messages and retries. Preserve object identifiers on retry to prevent duplicate submissions.
- Distinguish queued, sent and destination-acknowledged states. Do not represent an acknowledgement as a guarantee of permanent archival.
- Retain local originals after transfer. Test video independently; do not assume a still-image interface also accepts video.

## 15. Access, backup and maintenance

**Version 1**

- Use appropriate Windows/user access controls and clinic-approved storage permissions and encryption for files, the catalogue and backups.
- Make backup status visible and back up the catalogue, original media, edits, annotations, tags and notes consistently.
- Provide restore instructions and demonstrate restoration on a separate test location.
- Record changes to patient assignment, edits, deletion/restoration and exports in an audit history.
- Provide a deliberate, audited process for correcting a wrongly assigned image without losing its history or associated files.
- Keep identifying patient information out of diagnostic logs wherever possible.
- Do not automatically upload images, patient information or telemetry containing those details to external services.
- Provide clear setup, troubleshooting and update instructions. Updates must preserve existing images and catalogue data.

## 16. Delivery sequence

1. **Compatibility proof:** establish the camera/driver/SDK matrix; prove full-resolution still capture and supported video paths; document vendor dependencies and fallbacks.
2. **Capture foundation:** worklist import, patient/eye selection, simulated and verified camera adapters, automatic storage, current-session gallery and recoverable deletion.
3. **Complete Version 1:** capture presets, supported video, annotations, enhancements, tagging/search, file export, drag-and-drop, backup and installation.
4. **Clinical workflow verification:** run the acceptance tests with fictional data on the target Windows PC and the actual cameras and receiving applications. Resolve critical capture, identity and data-loss failures before routine use.
5. **System integrations:** electronic worklist and direct PACS transfer once their interfaces are confirmed.

Do not present an intermediate prototype as the completed Version 1. If a requested function is blocked by a vendor interface, document the exact limitation and verified alternatives while completing independent features.

## 17. Acceptance criteria

Demonstrate and record these results:

| Area | Required evidence |
| --- | --- |
| Camera support | Real capture tests for each exact camera; separate still/live-view/video results; simulated tests labelled |
| Worklist | Leading-zero MRNs and DOB formats preserved; duplicate import handled; conflicting details flagged |
| Patient identity | Two people with identical names stay separate; delayed transfers remain with their original patient/session/eye |
| Storage | Correct date/patient/session folders; unique filenames; interrupted saves detected; restart does not lose valid associations |
| Capture reliability | Disconnect/reconnect, blocked camera access, low storage and failed save produce clear recoverable states |
| Presets | Supported settings applied and read back where available; failures reported; physical setup instructions distinguished |
| Video | Correct patient/eye, visible recording state, playable saved files, failure handling and linked frame extraction |
| Editing | Original files unchanged; edits and original/edited status persist |
| Annotations | Editable after restart; positioning correct after supported transforms; export matches preview |
| Deletion | Single/bulk delete, undo and restoration work with associated edits and metadata; permanent removal requires confirmation |
| Search | Tags/notes survive restart; combined filters find the expected items; deleted items excluded |
| Drag-and-drop | Full-resolution single/multiple files work in tested destinations; export mode correct; source archive unchanged; delayed attachment reading works |
| File export | Receiving application can import the selected formats and associate them with the intended patient |
| Direct PACS, if implemented | Destination acknowledges test objects with correct identity/laterality; retries do not create duplicate objects |
| Backup | Restore recovers media, catalogue associations, tags, notes, edits and annotations |

## 18. Deliverables

- Source code and reproducible build instructions.
- Windows installer and instructions for a clean installation and updates.
- Fictional sample worklist and clearly identified simulated camera.
- Camera compatibility table and instructions for installing vendor prerequisites.
- Configuration guide for storage, presets, backup, worklist and export.
- Short user guide covering capture, video, annotations, tagging, deletion and dragging photos into email/folders.
- Acceptance-test report identifying actual equipment/software tested and remaining limitations.
- A short list of dependencies, licences and vendor information still required.

## 19. Later feature backlog

Keep these outside the initial required scope unless explicitly promoted:

- Foot pedal capture, subject to hardware support.
- Side-by-side comparison with earlier visits and linked zoom.
- Barcode-based patient selection.
- Contact sheets and image reports.
- Teaching export with identifying filenames, metadata and visible labels removed, plus a review step.
- Blur/overexposure indicators for operator review.
- Physical measurements only with calibration for the actual optical setup and magnification.
- Shared archives across clinic rooms or sites through a central service.

## 20. Reference starting points

Recheck compatibility, terms and current documentation during implementation. These links are starting points, not proof that a particular device or PACS supports a feature.

- [Canon SDK information](https://asia.canon/en/campaign/developerresources/sdk)
- [CSO digital slit lamp product information](https://csoitalia.it/en/prodotti/slit-lamp/)
- [DICOM ophthalmic photography image definition](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_A.41.html)
- [DICOM Modality Worklist definition](https://dicom.nema.org/medical/dicom/current/output/chtml/part04/sect_K.6.html)
- [Microsoft WPF documentation](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/overview/)
- [SQLite deployment guidance](https://www.sqlite.org/whentouse.html)

## Starting instruction

Read this specification, inspect the project environment, document assumptions and identify the smallest practical camera compatibility experiment. Establish the project structure and implement the independent workflow with fictional data and a simulated camera while obtaining the hardware details needed for real integrations. Report what is implemented, what is tested on actual equipment and what remains dependent on vendor access.

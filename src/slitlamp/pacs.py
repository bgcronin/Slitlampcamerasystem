"""Standards-based optional C-STORE, C-ECHO and Modality Worklist integration.

RGB Secondary Capture is deliberately used until a destination's ophthalmic SOP
and required acquisition attributes are agreed. No invented ophthalmic metadata.
"""

from datetime import datetime

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from .imaging import render
from .models import WorklistRow, now, uid


def build_dicom(catalog, mid: str, mode="original", sop_uid=None) -> FileDataset:
    item = catalog.media(mid)
    if item["kind"] != "image" or item["status"] != "ready" or item["deleted_at"]:
        raise ValueError("DICOM export currently supports saved, non-deleted still images only.")
    session = catalog.session(item["session_id"])
    image = render(
        catalog.path(item["path"]),
        item["edits"] if mode != "original" else {},
        item["annotations"] if mode == "annotated" else [],
    )
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid or generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = "2.25.152411345739885730388190386163497620"
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.PatientName = item["name"]
    ds.PatientID = item["mrn"]
    ds.IssuerOfPatientID = item["issuer"]
    ds.PatientBirthDate = item["dob"].replace("-", "")
    ds.PatientSex = ""
    ds.StudyInstanceUID = session["study_uid"]
    # Stable series for source/session/eye/version. SOP identifiers are saved with the transfer job.
    import uuid

    ds.SeriesInstanceUID = "2.25." + str(
        uuid.uuid5(uuid.NAMESPACE_URL, session["id"] + item["eye"] + mode).int
    )
    stamp = datetime.fromisoformat(item["created"])
    study_stamp = datetime.fromisoformat(session["created"])
    ds.StudyDate, ds.StudyTime = study_stamp.strftime("%Y%m%d"), study_stamp.strftime("%H%M%S")
    ds.ContentDate, ds.ContentTime = stamp.strftime("%Y%m%d"), stamp.strftime("%H%M%S.%f")
    ds.AcquisitionDateTime = stamp.strftime("%Y%m%d%H%M%S.%f%z")
    ds.TimezoneOffsetFromUTC = stamp.strftime("%z")
    ds.StudyID = session["id"][:16]
    ds.AccessionNumber = session["order_id"] or ""
    ds.ReferringPhysicianName = ""
    ds.Modality = "OT"
    ds.ConversionType = "WSD"
    ds.Manufacturer = "Slitlamp Studio"
    ds.SoftwareVersions = "0.1.0"
    ds.SeriesNumber = 1 if item["eye"] == "R" else 2
    ds.InstanceNumber = 1
    ds.ImageLaterality = item["eye"]
    ds.Laterality = item["eye"]
    ds.SeriesDescription = f"Slit lamp {item['eye']} {mode}"
    ds.ImageType = ["DERIVED", "SECONDARY"]
    ds.DerivationDescription = "RGB Secondary Capture from " + item["camera"] + "; " + mode
    ds.BurnedInAnnotation = "YES" if mode == "annotated" and item["annotations"] else "NO"
    ds.PatientOrientation = []
    ds.Rows, ds.Columns = image.height, image.width
    ds.SamplesPerPixel = 3
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = image.tobytes()
    if len(ds.PixelData) % 2:
        ds.PixelData += b"\0"
    # Source compression history is not invented for arbitrary imported images.
    if catalog.path(item["path"]).suffix.lower() in (".jpg", ".jpeg"):
        ds.LossyImageCompression = "01"
    return ds


def connection(config: dict):
    from pynetdicom import AE

    ae = AE(ae_title=config.get("calling_ae", "SLITLAMP"))
    ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = 15
    return ae


def echo(config: dict):
    from pynetdicom.sop_class import Verification

    ae = connection(config)
    ae.add_requested_context(Verification)
    assoc = ae.associate(config["host"], int(config["port"]), ae_title=config["called_ae"])
    if not assoc.is_established:
        raise ConnectionError("PACS association failed. Check host, port, AE titles and firewall.")
    try:
        status = assoc.send_c_echo()
        if not status or status.Status != 0:
            raise ConnectionError("PACS did not acknowledge the connection test.")
    finally:
        assoc.release()


def queue_transfer(catalog, mid: str, config: dict, mode: str):
    import json

    ds = build_dicom(catalog, mid, mode)
    path = catalog.root / ".exports" / (uid() + ".dcm")
    ds.save_as(path, enforce_file_format=True)
    tid = uid()
    with catalog.transaction():
        catalog.db.execute(
            "INSERT INTO transfers(id,media_id,destination,path,sop_uid,state,updated) VALUES(?,?,?,?,?,'queued',?)",
            (
                tid,
                mid,
                json.dumps(config),
                str(path.relative_to(catalog.root)),
                str(ds.SOPInstanceUID),
                now(),
            ),
        )
        catalog.audit("pacs.queued", tid, {"media": mid})
    return tid


def send_transfer(catalog, tid: str):
    import json
    import pydicom

    row = catalog.one("SELECT * FROM transfers WHERE id=?", (tid,))
    if not row:
        raise ValueError("Unknown transfer.")
    config = json.loads(row["destination"])
    ds = pydicom.dcmread(catalog.path(row["path"]))
    with catalog.transaction():
        catalog.db.execute(
            "UPDATE transfers SET state='sending',attempts=attempts+1,error='',updated=? WHERE id=?",
            (now(), tid),
        )
    assoc = None
    try:
        ae = connection(config)
        ae.add_requested_context(ds.SOPClassUID, ExplicitVRLittleEndian)
        assoc = ae.associate(config["host"], int(config["port"]), ae_title=config["called_ae"])
        if not assoc.is_established:
            raise ConnectionError("PACS rejected or did not answer the association.")
        status = assoc.send_c_store(ds)
        if not status or status.Status != 0:
            raise ConnectionError(
                f"PACS did not confirm storage: {hex(status.Status) if status else 'timeout'}"
            )
        with catalog.transaction():
            catalog.db.execute("UPDATE transfers SET state='acknowledged',updated=? WHERE id=?", (now(), tid))
            catalog.audit("pacs.acknowledged", tid)
    except Exception as exc:
        with catalog.transaction():
            catalog.db.execute(
                "UPDATE transfers SET state='failed',error=?,updated=? WHERE id=?", (str(exc), now(), tid)
            )
        raise
    finally:
        if assoc and assoc.is_established:
            assoc.release()


def query_worklist(config: dict, day: str, modality="") -> list[WorklistRow]:
    from pynetdicom.sop_class import ModalityWorklistInformationFind

    ae = connection(config)
    ae.add_requested_context(ModalityWorklistInformationFind)
    query = Dataset()
    query.PatientName = query.PatientID = query.PatientBirthDate = query.IssuerOfPatientID = ""
    query.AccessionNumber = ""
    step = Dataset()
    step.ScheduledProcedureStepStartDate = day.replace("-", "")
    step.ScheduledProcedureStepStartTime = ""
    step.Modality = modality
    step.ScheduledStationAETitle = ""
    query.ScheduledProcedureStepSequence = [step]
    assoc = ae.associate(config["host"], int(config["port"]), ae_title=config["called_ae"])
    if not assoc.is_established:
        raise ConnectionError("Could not connect to the worklist server.")
    result = []
    success = False
    try:
        for status, identifier in assoc.send_c_find(query, ModalityWorklistInformationFind):
            if not status:
                raise ConnectionError("Worklist request timed out.")
            if status.Status in (0xFF00, 0xFF01) and identifier:
                entry = identifier.ScheduledProcedureStepSequence[0]
                dob = datetime.strptime(str(identifier.PatientBirthDate), "%Y%m%d").date().isoformat()
                stamp = str(getattr(entry, "ScheduledProcedureStepStartTime", ""))
                result.append(
                    WorklistRow(
                        str(identifier.PatientName).replace("^", " "),
                        str(identifier.PatientID),
                        dob,
                        day,
                        f"{stamp[:2]}:{stamp[2:4]}" if len(stamp) >= 4 else "",
                        str(getattr(identifier, "AccessionNumber", "")),
                        str(getattr(identifier, "IssuerOfPatientID", "") or "CLINIC"),
                    )
                )
            elif status.Status == 0:
                success = True
            else:
                raise ConnectionError(f"Worklist returned failure {hex(status.Status)}.")
        if not success:
            raise ConnectionError("Worklist did not return a successful completion status.")
    finally:
        assoc.release()
    return result

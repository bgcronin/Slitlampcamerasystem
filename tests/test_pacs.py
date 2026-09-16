import pydicom
from pydicom.uid import SecondaryCaptureImageStorage

from slitlamp.pacs import build_dicom, queue_transfer


def test_dicom_identity_laterality_and_pixel_encoding(catalog, media, tmp_path):
    ds = build_dicom(catalog, media["id"])
    assert ds.PatientID == "00123"
    assert ds.PatientBirthDate == "19800203"
    assert ds.ImageLaterality == "R"
    assert ds.SOPClassUID == SecondaryCaptureImageStorage
    assert ds.Rows == 120 and ds.Columns == 160
    assert len(ds.PixelData) == 120 * 160 * 3
    path = tmp_path / "image.dcm"
    ds.save_as(path, enforce_file_format=True)
    recovered = pydicom.dcmread(path)
    assert recovered.SOPInstanceUID == ds.SOPInstanceUID
    assert recovered.PixelData == ds.PixelData


def test_transfer_job_preserves_uid_for_retries(catalog, media):
    job = queue_transfer(
        catalog,
        media["id"],
        {"host": "127.0.0.1", "port": 11112, "called_ae": "TEST", "calling_ae": "SLITLAMP"},
        "original",
    )
    first = catalog.one("SELECT * FROM transfers WHERE id=?", (job,))
    second = catalog.one("SELECT * FROM transfers WHERE id=?", (job,))
    assert first["sop_uid"] == second["sop_uid"]
    assert pydicom.dcmread(catalog.path(first["path"])).SOPInstanceUID == first["sop_uid"]


def test_local_dicom_receiver_acknowledges_image_and_retry(catalog, media):
    from pynetdicom import AE, evt
    from pydicom.uid import ExplicitVRLittleEndian
    from slitlamp.pacs import send_transfer

    received = []

    def store(event):
        received.append(
            (
                str(event.dataset.SOPInstanceUID),
                str(event.dataset.PatientID),
                str(event.dataset.ImageLaterality),
            )
        )
        return 0x0000

    server_ae = AE(ae_title="TESTPACS")
    server_ae.add_supported_context(SecondaryCaptureImageStorage, ExplicitVRLittleEndian)
    server = server_ae.start_server(("127.0.0.1", 0), block=False, evt_handlers=[(evt.EVT_C_STORE, store)])
    try:
        config = {
            "host": "127.0.0.1",
            "port": server.server_address[1],
            "called_ae": "TESTPACS",
            "calling_ae": "SLITLAMP",
        }
        job = queue_transfer(catalog, media["id"], config, "original")
        send_transfer(catalog, job)
        send_transfer(catalog, job)
        assert len(received) == 2
        assert received[0] == received[1]
        assert received[0][1:] == ("00123", "R")
        assert catalog.one("SELECT state,attempts FROM transfers WHERE id=?", (job,)) == {
            "state": "acknowledged",
            "attempts": 2,
        }
    finally:
        server.shutdown()

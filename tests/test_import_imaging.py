import time

import pytest
from openpyxl import Workbook
from PIL import Image

from slitlamp.worklist import read_table, map_rows, parse_date
from slitlamp.inbox import FolderInbox
from slitlamp.imaging import render, probe, video_frame
from slitlamp.cameras.recorder import StreamRecorder


def test_csv_mapping_preserves_leading_zeros(tmp_path):
    path = tmp_path / "worklist.csv"
    path.write_text("Patient,Record,Birth\nTest Person,00012,03/04/1980\n", encoding="utf-8")
    headings, rows = read_table(path)
    mapped = map_rows(rows, {"name": "Patient", "mrn": "Record", "dob": "Birth"}, "DMY", "2026-09-16")
    assert mapped[0].mrn == "00012"
    assert mapped[0].dob == "1980-04-03"
    assert parse_date("03/04/1980", "MDY") == "1980-03-04"
    with pytest.raises(ValueError):
        parse_date("03/04/1980", "ISO")


def test_excel_padded_mrn(tmp_path):
    book = Workbook()
    sheet = book.active
    sheet.append(["Name", "MRN", "DOB"])
    sheet.append(["Test", 12, "1980-01-01"])
    sheet["B2"].number_format = "000000"
    path = tmp_path / "list.xlsx"
    book.save(path)
    _, rows = read_table(path)
    assert rows[0]["MRN"] == "000012"


def test_watched_folder_quarantines_and_deduplicates(catalog, session, tmp_path, source):
    folder = tmp_path / "vendor"
    folder.mkdir()
    target = folder / "IMG_0001.png"
    target.write_bytes(source.read_bytes())
    inbox = FolderInbox(catalog)
    assert inbox.scan(folder, stable_seconds=0) == 0
    assert inbox.scan(folder, stable_seconds=0) == 1
    assert inbox.scan(folder, stable_seconds=0) == 0
    assert catalog.search() == []
    row = catalog.one("SELECT * FROM inbox")
    saved = inbox.assign(row["id"], session["id"], "L")
    assert saved["patient_id"] == session["patient_id"]
    assert saved["eye"] == "L"
    assert target.exists()
    with pytest.raises(ValueError):
        inbox.assign(row["id"], session["id"], "R")


def test_watch_archive_itself_is_rejected(catalog):
    with pytest.raises(ValueError):
        FolderInbox(catalog).scan(catalog.root)


def test_annotations_follow_crop_and_rotation(source):
    annotations = [
        {"kind": "rectangle", "points": [[0.1, 0.1], [0.4, 0.4]], "color": "#ff0000", "width": 0.02}
    ]
    annotated = render(source, {"crop": [0, 0, 0.5, 0.5], "rotation": 90}, annotations)
    assert annotated.size == (60, 80)
    pixels = annotated.tobytes()
    assert (
        sum(1 for r, g, b in zip(pixels[::3], pixels[1::3], pixels[2::3]) if r > 230 and g < 30 and b < 30)
        > 10
    )


def test_video_recording_is_playable_and_extractable(tmp_path):
    path = tmp_path / "video.mp4"
    image = Image.new("RGB", (160, 120), (40, 90, 160))
    recorder = StreamRecorder(path, image, fps=10)
    time.sleep(0.6)
    recorder.offer(Image.new("RGB", (160, 120), (100, 20, 30)))
    time.sleep(0.2)
    recorder.finish()
    info = probe(path, "video")
    assert info["width"] == 160 and info["height"] == 120
    assert info["duration"] >= 0.5
    assert video_frame(path, 0.2).size == (160, 120)

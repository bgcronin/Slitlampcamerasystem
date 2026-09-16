import json
from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from slitlamp.catalog import Catalog, IdentityConflict, digest, safe_name
from slitlamp.models import WorklistRow
from slitlamp.imaging import prepare_export, load_image


def test_duplicate_worklist_and_identical_names(catalog):
    day = date.today().isoformat()
    rows = [
        WorklistRow("Same Name", "0001", "1970-01-01", day),
        WorklistRow("Same Name", "0002", "1980-01-01", day),
    ]
    assert catalog.import_worklist(rows) == (2, 0)
    assert catalog.import_worklist(rows) == (0, 2)
    people = catalog.worklist(day)
    assert len(people) == 2
    assert people[0]["patient_id"] != people[1]["patient_id"]
    assert {row["mrn"] for row in people} == {"0001", "0002"}


def test_conflict_rolls_back_entire_import(catalog, session):
    day = date.today().isoformat()
    rows = [
        WorklistRow("New Person", "09999", "1990-01-01", day),
        WorklistRow("Wrong Name", "00123", "1980-02-03", day),
    ]
    with pytest.raises(IdentityConflict):
        catalog.import_worklist(rows)
    assert catalog.one("SELECT id FROM patients WHERE mrn='09999'") is None


def test_capture_context_survives_other_patient_selection(catalog, session, source):
    ticket = catalog.reserve(session["id"], "L", "image", "Delayed camera")
    with pytest.raises(FrozenInstanceError):
        ticket.eye = "R"
    catalog.import_worklist([WorklistRow("Other Person", "999", "1985-01-01", date.today().isoformat())])
    other = catalog.start_session(
        catalog.one("SELECT id FROM encounters WHERE patient_id!=?", (session["patient_id"],))["id"]
    )
    assert other["patient_id"] != ticket.patient_id
    saved = catalog.finish(ticket, source)
    assert saved["patient_id"] == session["patient_id"]
    assert saved["eye"] == "L"
    assert saved["session_id"] == session["id"]


def test_identity_and_end_session_guards(catalog, session):
    with pytest.raises(ValueError, match="eye"):
        catalog.reserve(session["id"], "", "image", "test")
    ticket = catalog.reserve(session["id"], "R", "image", "test")
    with pytest.raises(ValueError, match="pending"):
        catalog.end_session(session["id"])
    catalog.fail(ticket, "test failure")
    catalog.end_session(session["id"])
    with pytest.raises(ValueError, match="ended"):
        catalog.reserve(session["id"], "L", "image", "test")


def test_original_preserved_edits_exports_and_restore(catalog, media):
    original = catalog.path(media["path"])
    checksum = digest(original)
    annotations = [{"kind": "arrow", "points": [[0.1, 0.1], [0.8, 0.8]], "color": "#ff0000", "width": 0.03}]
    catalog.update_media(
        media["id"],
        edits={"brightness": 1.4, "rotation": 90},
        annotations=annotations,
        tags=["Cornea", "cornea", "Test"],
        notes="Follow-up",
    )
    exported = prepare_export(catalog, media["id"], "annotated", "PNG")
    assert load_image(exported).size == (120, 160)
    assert digest(original) == checksum
    assert catalog.search(text="cornea follow-up")
    catalog.delete([media["id"]])
    assert catalog.search() == []
    assert len(catalog.search(deleted=True)) == 1
    with pytest.raises(ValueError):
        prepare_export(catalog, media["id"])
    catalog.delete([media["id"]], restore=True)
    restored = catalog.media(media["id"])
    assert restored["annotations"] == annotations
    assert restored["tags"] == ["cornea", "test"]
    assert exported.is_file()  # Attachments survive subsequent archive edits/deletion.


def test_backup_restore_validates_all_media(catalog, media, tmp_path):
    catalog.update_media(
        media["id"],
        tags=["followup"],
        notes="sample",
        annotations=[{"kind": "text", "points": [[0.1, 0.1]], "text": "A"}],
    )
    backup = catalog.backup(tmp_path / "backups")
    target = tmp_path / "restored"
    Catalog.restore(backup, target)
    restored = Catalog(target)
    try:
        result = restored.media(media["id"])
        assert result["tags"] == ["followup"]
        assert result["notes"] == "sample"
        assert digest(restored.path(result["path"])) == media["sha256"]
    finally:
        restored.close()
    (backup / media["path"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="verification"):
        Catalog.restore(backup, tmp_path / "bad-restore")
    assert not (tmp_path / "bad-restore").exists()


def test_backup_refuses_live_archive_destination(catalog):
    with pytest.raises(ValueError, match="outside"):
        catalog.backup(catalog.root / "bad")


def test_pending_recovered_after_atomic_file_rename(catalog, session, source):
    ticket = catalog.reserve(session["id"], "R", "image", "test")
    path = catalog.root / "recovered.png"
    path.write_bytes(source.read_bytes())
    with catalog.transaction():
        catalog.db.execute(
            "UPDATE media SET path=?,sha256=? WHERE id=?", ("recovered.png", digest(path), ticket.id)
        )
    root = catalog.root
    catalog.close()
    recovered = Catalog(root)
    try:
        assert recovered.media(ticket.id)["status"] == "ready"
    finally:
        recovered.close()


def test_unfinished_capture_reported_failed(catalog, session):
    ticket = catalog.reserve(session["id"], "R", "video", "test")
    catalog.recover()
    assert catalog.media(ticket.id)["status"] == "failed"


def test_path_and_backup_traversal_refused(catalog, tmp_path):
    with pytest.raises(ValueError):
        catalog.path("../../outside")
    backup = tmp_path / "malicious"
    backup.mkdir()
    (backup / "backup.json").write_text(json.dumps({"files": {"../../outside": "abc"}}))
    with pytest.raises(ValueError, match="Invalid path"):
        Catalog.restore(backup, tmp_path / "restore")


def test_purge_only_deleted_items_and_export_copies_survive(catalog, media):
    exported = prepare_export(catalog, media["id"])
    with pytest.raises(ValueError):
        catalog.purge([media["id"]])
    catalog.delete([media["id"]])
    catalog.purge([media["id"]])
    assert not catalog.path(media["path"]).exists()
    assert exported.exists()
    assert catalog.media(media["id"])["status"] == "purged"


def test_names_safe_on_windows():
    assert safe_name("CON") == "_CON"
    assert safe_name(" A/B:C*? ") == "A_B_C__"
    assert not safe_name("hello. ").endswith(".")


def test_same_day_sessions_and_files_never_overwrite(catalog, session, source):
    second = catalog.start_session(session["encounter_id"])
    assert second["folder"] != session["folder"]
    first_ticket = catalog.reserve(session["id"], "R", "image", "test")
    second_ticket = catalog.reserve(session["id"], "R", "image", "test")
    first = catalog.finish(first_ticket, source)
    second_media = catalog.finish(second_ticket, source)
    assert first["path"] != second_media["path"]
    assert source.exists()

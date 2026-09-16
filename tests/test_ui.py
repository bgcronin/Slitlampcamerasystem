from slitlamp.ui.main import MainWindow
from slitlamp.ui.editor import EditorDialog


def test_demo_workflow_capture_review_tag_delete_restore(qtbot, catalog, monkeypatch):
    window = MainWindow(catalog, demo=True)
    qtbot.addWidget(window)
    window.show()
    window.timer.stop()
    assert window.patient_list.count() == 3
    assert window.active_session and window.eye.currentData() == "R"
    window.capture()
    qtbot.waitUntil(lambda: not window.pending, timeout=15000)
    qtbot.waitUntil(lambda: window.gallery.count() == 1, timeout=10000)
    window.gallery.setCurrentRow(0)
    qtbot.waitUntil(lambda: window.current_media is not None)
    mid = window.current_media["id"]
    assert window.current_media["metadata"]["simulated"]
    window.tags.setText("cornea, teaching")
    window.notes.setPlainText("Test note")
    window.save_details()
    assert catalog.media(mid)["tags"] == ["cornea", "teaching"]
    window.gallery.setFocus()
    window.delete_selected()
    assert len(catalog.search(deleted=True)) == 1
    window.undo_delete()
    assert len(catalog.search()) == 1
    qtbot.waitUntil(lambda: not window.tasks, timeout=15000)
    window.close()


def test_annotation_editor_save_reload_and_undo(qtbot, catalog, media):
    editor = EditorDialog(catalog, media["id"])
    qtbot.addWidget(editor)
    editor.show()
    editor.canvas.add_annotation(
        {"kind": "arrow", "points": [[0.1, 0.2], [0.8, 0.7]], "color": "#ffff00", "width": 0.01}
    )
    editor.set_edit("rotation", 90)
    editor.undo()
    assert editor.edits.get("rotation", 0) == 0
    editor.redo()
    editor.save()
    assert catalog.media(media["id"])["edits"]["rotation"] == 90
    again = EditorDialog(catalog, media["id"])
    qtbot.addWidget(again)
    assert len(again.canvas.annotations()) == 1
    again.reject()

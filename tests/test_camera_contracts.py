import ctypes

import pytest

from slitlamp.cameras.canon import CanonCamera, EDSDK, CanonError, DirectoryInfo, Capacity, DeviceInfo
from slitlamp.cameras.simulator import SimulatedCamera


def test_canon_native_structure_widths():
    assert ctypes.sizeof(DirectoryInfo) == 288
    assert DirectoryInfo.size.offset == 0
    assert DirectoryInfo.name.offset == 20
    assert ctypes.sizeof(Capacity) == 12
    assert ctypes.sizeof(DeviceInfo) == 520


def test_missing_sdk_fails_clearly(tmp_path):
    with pytest.raises(CanonError, match="Windows|EDSDK"):
        EDSDK(tmp_path)


def test_canon_interrupted_capture_blocks_reuse(qtbot, catalog, session):
    camera = CanonCamera(catalog.root)
    camera.reconnect_required = True
    ticket = catalog.reserve(session["id"], "R", "image", "Canon")
    with qtbot.waitSignal(camera.failed, timeout=1000) as blocker:
        camera.capture(ticket)
    assert blocker.args[0] == ticket
    assert "Reconnect" in blocker.args[1]
    assert camera.commands.empty()


def test_simulator_video_retains_original_ticket(qtbot, catalog, session):
    camera = SimulatedCamera()
    camera.connect_camera()
    ticket = catalog.reserve(session["id"], "L", "video", camera.info.label)
    camera.start_video(ticket)
    qtbot.wait(350)
    with qtbot.waitSignal(camera.captured, timeout=10000) as blocker:
        camera.stop_video()
    assert blocker.args[0].patient_id == session["patient_id"]
    assert blocker.args[0].eye == "L"
    assert blocker.args[1].is_file()
    assert blocker.args[2]["simulated"] is True
    camera.close()

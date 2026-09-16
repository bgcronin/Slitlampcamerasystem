"""Canon EDSDK 13.x Windows x64 adapter (SDK supplied separately by Canon).

All EDSDK operations and callbacks live on one COM-initialised worker thread.
Native widths are fixed explicitly, including 64-bit stream lengths. This code
does not ship Canon DLLs or claim hardware verification.
"""

from __future__ import annotations

import ctypes as C
import io
import os
import queue
import threading
import time
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Signal

from .base import Camera
from .recorder import StreamRecorder
from ..models import CameraInfo

U32, I32, U64, REF = C.c_uint32, C.c_int32, C.c_uint64, C.c_void_p
PROP = {"iso": 0x402, "aperture": 0x405, "shutter": 0x406, "white_balance": 0x106}
ISO_VALUES = {
    0x00: "Auto",
    0x48: "100",
    0x50: "200",
    0x58: "400",
    0x60: "800",
    0x68: "1600",
    0x70: "3200",
    0x78: "6400",
    0x80: "12800",
    0x88: "25600",
}
TV_VALUES = {
    0x38: "1 s",
    0x40: "1/2",
    0x48: "1/4",
    0x50: "1/8",
    0x58: "1/15",
    0x60: "1/30",
    0x68: "1/60",
    0x70: "1/125",
    0x78: "1/250",
    0x80: "1/500",
    0x88: "1/1000",
    0x90: "1/2000",
    0x98: "1/4000",
}
AV_VALUES = {0x20: "f/2.8", 0x28: "f/4", 0x30: "f/5.6", 0x38: "f/8", 0x40: "f/11", 0x48: "f/16", 0x50: "f/22"}
WB_VALUES = {
    0: "Auto",
    1: "Daylight",
    2: "Cloudy",
    3: "Tungsten",
    4: "Fluorescent",
    5: "Flash",
    6: "Manual",
    8: "Shade",
    9: "Colour temperature",
}
TARGET_MODELS = ("EOS 200D II", "EOS 250D", "EOS Rebel SL3", "EOS 60D", "EOS 70D")


class DeviceInfo(C.Structure):
    _fields_ = [
        ("port", C.c_char * 256),
        ("description", C.c_char * 256),
        ("subtype", U32),
        ("reserved", U32),
    ]


class DirectoryInfo(C.Structure):
    _fields_ = [
        ("size", U64),
        ("folder", U32),
        ("group", U32),
        ("option", U32),
        ("name", C.c_char * 256),
        ("format", U32),
        ("date", U32),
    ]


class Capacity(C.Structure):
    _fields_ = [("clusters", I32), ("sector", I32), ("reset", I32)]


class PropertyDescription(C.Structure):
    _fields_ = [("form", I32), ("access", I32), ("count", I32), ("values", I32 * 128)]


class CanonError(RuntimeError):
    pass


class EDSDK:
    def __init__(self, folder: Path):
        if os.name != "nt" or C.sizeof(REF) != 8:
            raise CanonError("Canon direct capture requires 64-bit Windows and Canon's 64-bit EDSDK.")
        folder = folder.resolve()
        library = folder / "EDSDK.dll"
        if not library.is_file():
            raise CanonError(
                "Choose the folder containing Canon's licensed 64-bit EDSDK.dll and its dependencies."
            )
        self.directory = os.add_dll_directory(str(folder))
        self.dll = C.WinDLL(str(library))
        self.callback_type = C.WINFUNCTYPE(U32, U32, REF, REF)
        signatures = {
            "EdsInitializeSDK": [],
            "EdsTerminateSDK": [],
            "EdsGetEvent": [],
            "EdsGetCameraList": [C.POINTER(REF)],
            "EdsGetChildCount": [REF, C.POINTER(U32)],
            "EdsGetChildAtIndex": [REF, I32, C.POINTER(REF)],
            "EdsGetDeviceInfo": [REF, C.POINTER(DeviceInfo)],
            "EdsOpenSession": [REF],
            "EdsCloseSession": [REF],
            "EdsRelease": [REF],
            "EdsRetain": [REF],
            "EdsSetObjectEventHandler": [REF, U32, self.callback_type, REF],
            "EdsSetPropertyData": [REF, U32, I32, U32, REF],
            "EdsGetPropertyData": [REF, U32, I32, U32, REF],
            "EdsGetPropertyDesc": [REF, U32, C.POINTER(PropertyDescription)],
            "EdsSendCommand": [REF, U32, I32],
            "EdsSetCapacity": [REF, Capacity],
            "EdsGetDirectoryItemInfo": [REF, C.POINTER(DirectoryInfo)],
            "EdsCreateMemoryStream": [U64, C.POINTER(REF)],
            "EdsGetPointer": [REF, C.POINTER(REF)],
            "EdsGetLength": [REF, C.POINTER(U64)],
            "EdsDownload": [REF, U64, REF],
            "EdsDownloadComplete": [REF],
            "EdsDownloadCancel": [REF],
            "EdsCreateEvfImageRef": [REF, C.POINTER(REF)],
            "EdsDownloadEvfImage": [REF, REF],
        }
        for name, args in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes, function.restype = args, U32

    def call(self, name, *args):
        status = getattr(self.dll, name)(*args)
        if status:
            explanations = {
                0x81: "camera busy",
                0xA102: "autofocus could not lock; use manual focus",
                0xA104: "camera needs a memory card",
                0x7: "operation not supported",
                0x2: "internal camera error",
            }
            raise CanonError(f"{name}: {explanations.get(status, 'camera/SDK error')} (0x{status:08X}).")

    def get(self, camera, prop):
        value = U32()
        self.call("EdsGetPropertyData", camera, prop, 0, 4, C.byref(value))
        return value.value

    def set(self, camera, prop, value):
        data = U32(int(value))
        self.call("EdsSetPropertyData", camera, prop, 0, 4, C.byref(data))

    def bytes(self, stream):
        pointer, length = REF(), U64()
        self.call("EdsGetPointer", stream, C.byref(pointer))
        self.call("EdsGetLength", stream, C.byref(length))
        if length.value > 1024 * 1024 * 1024:
            raise CanonError("The returned file exceeds the 1 GB transfer limit; use vendor file import.")
        return C.string_at(pointer, length.value)


class CanonCamera(Camera):
    settings_changed = Signal(dict)
    preset_result = Signal(dict)
    orphan_file = Signal(object)

    def __init__(self, folder: Path, device_index=0, parent=None):
        super().__init__(
            CameraInfo(
                "canon-edsdk",
                "Canon EOS · EDSDK",
                "canon",
                video=True,
                live=True,
                detail="Full-resolution stills; video is recorded from the live-view stream.",
            ),
            parent,
        )
        self.folder = folder
        self.device_index = device_index
        self.commands = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self._settings = {}
        self._options = {}
        self.recorder = None
        self.video_ticket = None
        self.reconnect_required = False

    def connect_camera(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="Canon EDSDK", daemon=True)
        self.thread.start()

    def capture(self, ticket):
        if self.reconnect_required:
            self.failed.emit(
                ticket, "Reconnect Canon after an interrupted capture. Late files remain unassigned."
            )
            return
        self.commands.put(("capture", ticket))

    def settings(self):
        return self._settings.copy()

    def options(self):
        return self._options.copy()

    def apply_settings(self, values):
        self.commands.put(("settings", dict(values)))
        return {key: "Queued; await camera readback" for key in values}

    def start_video(self, ticket):
        if self.latest is None or not self.connected:
            raise ValueError(
                "Wait for Canon live view before recording. Native in-camera movies can also be imported."
            )
        self.video_ticket = ticket
        self.recorder = StreamRecorder(self.staging_path(ticket, ".mp4"), self.latest, fps=15)
        self.recording = True
        self.recording_changed.emit(True)

    def stop_video(self):
        if not self.recorder:
            return
        recorder, self.recorder = self.recorder, None
        try:
            path = recorder.finish()
            self.captured.emit(
                self.video_ticket,
                path,
                {"capture_source": "Canon live-view video", "preview_resolution": True, "fps": 15},
            )
        except Exception as exc:
            self.failed.emit(self.video_ticket, str(exc))
        finally:
            self.recording = False
            self.recording_changed.emit(False)

    def close(self):
        self.stop_video()
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=8)
            if self.thread.is_alive():
                raise CanonError(
                    "Canon is still finishing an operation. Wait before reconnecting or exiting."
                )
        self.connected = False

    def _read_settings(self, sdk, camera):
        values, options = {}, {}
        labels = {"iso": ISO_VALUES, "shutter": TV_VALUES, "aperture": AV_VALUES, "white_balance": WB_VALUES}
        for key, prop in PROP.items():
            try:
                values[key] = sdk.get(camera, prop)
                desc = PropertyDescription()
                sdk.call("EdsGetPropertyDesc", camera, prop, C.byref(desc))
                options[key] = [
                    {"value": int(v), "label": labels[key].get(int(v), f"Camera value 0x{int(v):X}")}
                    for v in desc.values[: max(0, min(128, desc.count))]
                ]
            except CanonError:
                continue
        self._settings, self._options = values, options
        self.settings_changed.emit(values)

    def _run(self):
        sdk, camera, camera_list = None, REF(), REF()
        initialised = session_open = False
        current = None
        downloads = []
        object_events = queue.Queue()
        last_download = 0
        capture_started = 0
        original_save = original_evf = None
        com = False
        try:
            if os.name != "nt":
                raise CanonError("Canon EDSDK direct capture is available on Windows only.")
            hr = C.windll.ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
            com = hr in (0, 1)
            if not com:
                raise CanonError("Could not initialise the Canon worker's COM apartment.")
            sdk = EDSDK(self.folder)
            sdk.call("EdsInitializeSDK")
            initialised = True
            sdk.call("EdsGetCameraList", C.byref(camera_list))
            count = U32()
            sdk.call("EdsGetChildCount", camera_list, C.byref(count))
            if self.device_index >= count.value:
                raise CanonError(
                    "No Canon camera at this index. Connect USB, turn the camera on, and close EOS Utility."
                )
            sdk.call("EdsGetChildAtIndex", camera_list, self.device_index, C.byref(camera))
            info = DeviceInfo()
            sdk.call("EdsGetDeviceInfo", camera, C.byref(info))
            self.info.label = info.description.decode(errors="replace")
            self.info.id = "canon:" + self.info.label
            sdk.call("EdsOpenSession", camera)
            session_open = True

            @sdk.callback_type
            def callback(event, item, context):
                if item:
                    # Callback transfers its reference to our event queue. Release once after handling.
                    if event == 0x208:  # kEdsObjectEvent_DirItemRequestTransfer
                        object_events.put(REF(item))
                    else:
                        sdk.dll.EdsRelease(item)
                return 0

            self._callback = callback  # Keep native callback alive for entire session.
            sdk.call("EdsSetObjectEventHandler", camera, 0x200, callback, None)
            original_save = sdk.get(camera, 0xB)
            sdk.set(camera, 0xB, 2)  # kEdsSaveTo_Host
            sdk.call("EdsSetCapacity", camera, Capacity(0x7FFFFFFF, 4096, 1))
            self._read_settings(sdk, camera)
            try:
                original_evf = sdk.get(camera, 0x500)
                sdk.set(camera, 0x500, original_evf | 2)  # PC EVF output
            except CanonError as exc:
                self.status.emit(f"Still capture ready; live view unavailable: {exc}")
            self.connected = True
            self.status.emit(f"{self.info.label} · connected · video uses preview resolution")
            last_frame = 0
            while not self.stop_event.is_set():
                sdk.call("EdsGetEvent")
                try:
                    command, value = self.commands.get_nowait()
                    if command == "capture":
                        if current:
                            self.failed.emit(value, "Wait for the previous Canon transfer to finish.")
                        else:
                            current = value
                            capture_started = time.monotonic()
                            downloads = []
                            try:
                                sdk.call("EdsSendCommand", camera, 0, 0)  # TakePicture
                            except CanonError as exc:
                                self.reconnect_required = True
                                self.failed.emit(current, str(exc))
                                current = None
                    elif command == "settings":
                        result = {}
                        for key, setting in value.items():
                            try:
                                if key not in PROP:
                                    raise CanonError("Unsupported property")
                                sdk.set(camera, PROP[key], setting)
                                actual = sdk.get(camera, PROP[key])
                                result[key] = (
                                    "Applied"
                                    if actual == int(setting)
                                    else f"Not applied; camera returned {actual}"
                                )
                            except CanonError as exc:
                                result[key] = str(exc)
                        self._read_settings(sdk, camera)
                        self.preset_result.emit(result)
                except queue.Empty:
                    pass
                while not object_events.empty():
                    item = object_events.get_nowait()
                    stream = REF()
                    complete = False
                    try:
                        entry = DirectoryInfo()
                        sdk.call("EdsGetDirectoryItemInfo", item, C.byref(entry))
                        if entry.folder:
                            continue
                        if entry.size > 1024 * 1024 * 1024:
                            raise CanonError(
                                "Camera file exceeds direct-transfer memory limit; use vendor import."
                            )
                        sdk.call("EdsCreateMemoryStream", entry.size, C.byref(stream))
                        sdk.call("EdsDownload", item, entry.size, stream)
                        payload = sdk.bytes(stream)
                        extension = Path(entry.name.decode(errors="replace")).suffix.lower()
                        if extension not in (".jpg", ".jpeg", ".cr2", ".cr3", ".mov", ".mp4"):
                            raise CanonError("Unsupported camera file format; select JPEG or RAW+JPEG.")
                        # Unsolicited hardware shutter events are quarantined, not assigned to the selected patient.
                        stage = current.staging if current else self.folder_for_orphans
                        path = stage / f"{time.time_ns()}{extension}"
                        with path.open("xb") as out:
                            out.write(payload)
                            out.flush()
                            os.fsync(out.fileno())
                        sdk.call("EdsDownloadComplete", item)
                        complete = True
                        if current:
                            downloads.append(path)
                            last_download = time.monotonic()
                        else:
                            self.orphan_file.emit(path)
                    except Exception as exc:
                        self.reconnect_required = True
                        self.failed.emit(current, str(exc))
                        current = None
                    finally:
                        if not complete:
                            sdk.dll.EdsDownloadCancel(item)
                        if stream:
                            sdk.dll.EdsRelease(stream)
                        sdk.dll.EdsRelease(item)
                if current and downloads and time.monotonic() - last_download > 1.5:
                    downloads.sort(key=lambda p: p.suffix.lower() not in (".jpg", ".jpeg"))
                    self.captured.emit(
                        current,
                        downloads[0],
                        {
                            "capture_source": "Canon full-resolution file",
                            "companions": [str(p) for p in downloads[1:]],
                        },
                    )
                    current = None
                    downloads = []
                if current and not downloads and time.monotonic() - capture_started > 30:
                    self.reconnect_required = True
                    self.failed.emit(
                        current,
                        "Canon capture timed out. Check manual focus, card and camera mode. Late files go to review.",
                    )
                    current = None
                if time.monotonic() - last_frame > 0.1:
                    last_frame = time.monotonic()
                    stream, evf = REF(), REF()
                    try:
                        sdk.call("EdsCreateMemoryStream", 0, C.byref(stream))
                        sdk.call("EdsCreateEvfImageRef", stream, C.byref(evf))
                        result = sdk.dll.EdsDownloadEvfImage(camera, evf)
                        if result == 0:
                            image = Image.open(io.BytesIO(sdk.bytes(stream))).convert("RGB")
                            self.latest = image
                            self.frame.emit(image)
                            if self.recorder:
                                self.recorder.offer(image)
                    finally:
                        if evf:
                            sdk.dll.EdsRelease(evf)
                        if stream:
                            sdk.dll.EdsRelease(stream)
                self.stop_event.wait(0.01)
        except Exception as exc:
            self.failed.emit(current, str(exc))
            current = None
        finally:
            self.connected = False
            if current:
                self.failed.emit(
                    current, "Canon session ended before transfer completed; inspect staging files."
                )
            if sdk:
                while not object_events.empty():
                    orphan = object_events.get_nowait()
                    sdk.dll.EdsDownloadCancel(orphan)
                    sdk.dll.EdsRelease(orphan)
                if session_open:
                    for prop, value in ((0x500, original_evf), (0xB, original_save)):
                        if value is not None:
                            try:
                                sdk.set(camera, prop, value)
                            except CanonError:
                                pass
                    sdk.dll.EdsCloseSession(camera)
                if camera:
                    sdk.dll.EdsRelease(camera)
                if camera_list:
                    sdk.dll.EdsRelease(camera_list)
                if initialised:
                    sdk.dll.EdsTerminateSDK()
                sdk.directory.close()
            if com:
                C.windll.ole32.CoUninitialize()
            self.status.emit("Canon disconnected")

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


@dataclass(frozen=True)
class CaptureTicket:
    """Immutable identity, established BEFORE a request reaches a camera."""

    id: str
    session_id: str
    patient_id: str
    eye: str
    kind: str
    camera: str
    created: str
    staging: Path


@dataclass
class CameraInfo:
    id: str
    label: str
    backend: str
    still: bool = True
    video: bool = False
    live: bool = False
    verification: str = "Implemented; requires hardware verification"
    detail: str = ""
    settings: dict = field(default_factory=dict)


@dataclass
class WorklistRow:
    name: str
    mrn: str
    dob: str
    day: str
    appointment: str = ""
    order_id: str = ""
    issuer: str = "CLINIC"

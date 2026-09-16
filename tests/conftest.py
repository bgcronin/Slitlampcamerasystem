import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image

from slitlamp.catalog import Catalog
from slitlamp.models import WorklistRow


@pytest.fixture
def catalog(tmp_path):
    store = Catalog(tmp_path / "archive")
    yield store
    try:
        store.close()
    except Exception:
        pass


@pytest.fixture
def session(catalog):
    day = date.today().isoformat()
    catalog.import_worklist([WorklistRow("Test Person", "00123", "1980-02-03", day)])
    return catalog.start_session(catalog.worklist(day)[0]["id"])


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.png"
    image = Image.new("RGB", (160, 120), (80, 110, 140))
    image.putpixel((20, 20), (255, 0, 0))
    image.save(path)
    return path


@pytest.fixture
def media(catalog, session, source):
    ticket = catalog.reserve(session["id"], "R", "image", "Test adapter")
    return catalog.finish(ticket, source)

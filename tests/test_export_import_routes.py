"""Tests fuer die Export/Import-HTTP-Routen (Etappe 4)."""

import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_packages.utils.export_import import build_export_import_routes


class _FakeStore:
    def __init__(self):
        self._data: dict[str, dict] = {}

    def list(self) -> dict:
        return dict(self._data)

    def get(self, item_id: str) -> dict | None:
        return self._data.get(item_id)

    def create(self, item_id: str, data: dict) -> None:
        self._data[item_id] = dict(data)

    def update(self, item_id: str, data: dict) -> None:
        self._data.setdefault(item_id, {}).update(data)


@pytest.fixture
def client(tmp_path):
    from astrapi_core.system import db as core_db

    from astrapi_packages.utils import file_store

    core_db._local.conn = None
    core_db.configure(tmp_path / "test.db")
    file_store._table_ready = False

    store = _FakeStore()
    store.create("arch-builder", {"tag": "latest", "module": "archlinux"})
    file_store.save("builder", "arch-builder", "arch-builder.dockerfile", "FROM archlinux\n")

    app = FastAPI()
    app.include_router(build_export_import_routes("builder", store, ["tag", "module"]))
    yield TestClient(app), store
    core_db._local.conn = None


def test_export_all(client):
    c, _store = client
    r = c.get("/ui/builder/export")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["item_id"] == "arch-builder"
    assert "attachment" in r.headers["content-disposition"]


def test_export_one(client):
    c, _store = client
    r = c.get("/api/builder/arch-builder/export")
    assert r.status_code == 200
    assert r.json()[0]["item_id"] == "arch-builder"


def test_import_upload(client):
    c, store = client
    payload = [
        {
            "item_id": "debian-builder",
            "metadata": {"tag": "latest", "module": "debian"},
            "files": [{"filename": "debian-builder.dockerfile", "content": "FROM debian\n"}],
        }
    ]
    upload = io.BytesIO(json.dumps(payload).encode())
    r = c.post("/api/builder/import", files={"file": ("export.json", upload, "application/json")})
    assert r.status_code == 200
    assert r.json() == {"created": 1, "updated": 0, "files_imported": 1}
    assert store.get("debian-builder")["tag"] == "latest"


def test_import_ungueltiges_json(client):
    c, _store = client
    upload = io.BytesIO(b"kein json")
    r = c.post("/api/builder/import", files={"file": ("export.json", upload, "application/json")})
    assert r.status_code == 400


def test_roundtrip_export_und_import(client):
    c, _store = client
    exported = c.get("/ui/builder/export").content
    r = c.post(
        "/api/builder/import",
        files={"file": ("export.json", io.BytesIO(exported), "application/json")},
    )
    assert r.status_code == 200
    # existierender Eintrag -> updated statt created
    assert r.json()["updated"] == 1


def test_export_all_kollidiert_nicht_mit_generischem_item_id_router():
    """Regression: /api/{owner_type}/export darf NICHT mit dem generischen
    JSON-CRUD-Router (GET /api/{owner_type}/{item_id}) kollidieren -- deshalb
    liegt der Bulk-Export unter /ui/ statt /api/. War beim ersten Verdrahten
    in der echten App tatsaechlich kaputt (item_id='export' matchte zuerst),
    im isolierten Router-Test (siehe fixture oben) aber unsichtbar, weil dort
    kein zweiter Router mit {item_id}-Route im selben Prefix existiert."""
    from astrapi_core.system import db as core_db
    from fastapi import HTTPException

    from astrapi_packages.utils import file_store

    core_db._local.conn = None
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        core_db.configure(Path(tmp) / "test.db")
        file_store._table_ready = False

        store = _FakeStore()
        store.create("arch-builder", {"tag": "latest", "module": "archlinux"})

        app = FastAPI()

        # Simuliert crud_router.py's generische GET /{item_id}-Route, zuerst
        # registriert -- genau die Reihenfolge, die in der echten App zum
        # Fehlschlag fuehrte.
        from fastapi import APIRouter

        item_router = APIRouter()

        @item_router.get("/{item_id}")
        def get_item(item_id: str):
            item = store.get(item_id)
            if item is None:
                raise HTTPException(404, f"nicht gefunden: {item_id}")
            return item

        app.include_router(item_router, prefix="/api/builder")
        app.include_router(build_export_import_routes("builder", store, ["tag", "module"]))

        c = TestClient(app)
        r = c.get("/ui/builder/export")
        assert r.status_code == 200
        assert r.json()[0]["item_id"] == "arch-builder"

    core_db._local.conn = None

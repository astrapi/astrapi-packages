"""Tests fuer astrapi_packages.utils.file_routes (Etappe 2)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_packages.utils.file_routes import build_file_routes


@pytest.fixture
def client(tmp_path):
    from astrapi_core.system import db as core_db
    from astrapi_packages.utils import file_store

    core_db._local.conn = None
    core_db.configure(tmp_path / "test.db")
    file_store._table_ready = False

    app = FastAPI()
    app.include_router(build_file_routes("builder"))
    yield TestClient(app)
    core_db._local.conn = None


def test_list_files_leer(client):
    r = client.get("/api/builder/arch-builder/files")
    assert r.status_code == 200
    assert r.json() == []


def test_read_unbekannte_datei_404(client):
    r = client.get("/api/builder/arch-builder/files/Dockerfile")
    assert r.status_code == 404


def test_save_und_list(client):
    r = client.post(
        "/api/builder/arch-builder/files/Dockerfile", json={"content": "FROM archlinux\n"}
    )
    assert r.status_code == 200
    files = client.get("/api/builder/arch-builder/files").json()
    assert len(files) == 1
    assert files[0]["filename"] == "Dockerfile"
    assert files[0]["content"] == "FROM archlinux\n"


def test_diff_zeigt_unterschied(client):
    client.post("/api/builder/arch-builder/files/Dockerfile", json={"content": "FROM archlinux\n"})
    r = client.post(
        "/api/builder/arch-builder/files/Dockerfile/diff",
        json={"content": "FROM archlinux:latest\n"},
    )
    assert "-FROM archlinux" in r.json()["diff"]
    assert "+FROM archlinux:latest" in r.json()["diff"]


def test_delete_und_history(client):
    client.post("/api/builder/arch-builder/files/Dockerfile", json={"content": "a"})
    r = client.delete("/api/builder/arch-builder/files/Dockerfile")
    assert r.status_code == 200
    assert client.get("/api/builder/arch-builder/files/Dockerfile").status_code == 404

    history = client.get("/api/builder/arch-builder/files/Dockerfile/history").json()
    assert len(history) == 2
    assert history[0]["is_deleted"] == 1


def test_restore(client):
    client.post("/api/builder/arch-builder/files/Dockerfile", json={"content": "v1"})
    client.post("/api/builder/arch-builder/files/Dockerfile", json={"content": "v2"})
    history = client.get("/api/builder/arch-builder/files/Dockerfile/history").json()
    v1_id = history[1]["id"]

    r = client.post(f"/api/builder/arch-builder/files/Dockerfile/restore/{v1_id}")
    assert r.status_code == 200
    assert client.get("/api/builder/arch-builder/files/Dockerfile").json()["content"] == "v1"


def test_restore_unbekannte_version_404(client):
    r = client.post("/api/builder/arch-builder/files/Dockerfile/restore/999")
    assert r.status_code == 404

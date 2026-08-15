"""Tests fuer das os_types-Modul -- freie OS-Typ-Definition ohne Code, siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul"."""

import os
import tempfile

import pytest

_workdir = tempfile.mkdtemp(prefix="astrapi-packages-test-ostypes-")
os.environ["ASTRAPI_PACKAGES_WORK_DIR"] = _workdir

from fastapi.testclient import TestClient  # noqa: E402

import astrapi_packages._app as app_mod  # noqa: E402

client = TestClient(app_mod.app)
_DB_PATH = app_mod.ACTUAL_DB_PATH


@pytest.fixture(autouse=True)
def _reconnect_own_db():
    from astrapi_core.system import db as core_db

    core_db._local.conn = None
    core_db.configure(_DB_PATH)
    yield


def test_create_beliebigen_os_typ_frei_benannt():
    r = client.post(
        "/ui/os_types/",
        data={"key": "ubuntu", "label": "Ubuntu", "repo_subdir": "ubuntu"},
    )
    assert r.status_code == 200

    r = client.get("/api/os_types/ubuntu")
    assert r.status_code == 200
    assert r.json()["label"] == "Ubuntu"


def test_liste_zeigt_neu_angelegten_typ():
    client.post("/ui/os_types/", data={"key": "fedora", "label": "Fedora", "repo_subdir": "fedora"})
    r = client.get("/api/os_types/")
    assert "fedora" in r.json()["os_types"]


def test_update_aendert_repo_subdir():
    client.post("/ui/os_types/", data={"key": "gentoo", "label": "Gentoo", "repo_subdir": "old"})
    r = client.get("/ui/os_types/gentoo/edit")
    assert r.status_code == 200
    r = client.post("/ui/os_types/gentoo/update", data={"label": "Gentoo", "repo_subdir": "new"})
    assert r.status_code == 200
    assert client.get("/api/os_types/gentoo").json()["repo_subdir"] == "new"


def test_delete_entfernt_os_typ():
    client.post("/ui/os_types/", data={"key": "temp", "label": "Temp", "repo_subdir": "temp"})
    r = client.delete("/api/os_types/temp")
    assert r.status_code == 204
    assert client.get("/api/os_types/temp").status_code == 404


def test_kein_code_noetig_fuer_neuen_typ_erscheint_im_pakete_filter():
    """Kernanspruch des virtuellen OS-Moduls: ein frei benannter, neuer
    OS-Typ erscheint sofort im Pakete-Filter -- ohne Neustart, ohne Code."""
    client.post(
        "/ui/os_types/", data={"key": "voidlinux", "label": "Void Linux", "repo_subdir": "void"}
    )
    r = client.get("/ui/packages/content")
    assert r.status_code == 200
    assert "voidlinux" in r.text

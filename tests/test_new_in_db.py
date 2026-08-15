"""Tests fuer den "Neu erstellen"-Flow (Etappe 5, PKGBUILD direkt in der DB).

astrapi_packages._app baut die App als Modul-Singleton beim Import auf und
liest dabei einmalig ASTRAPI_PACKAGES_WORK_DIR -- die Env-Variable muss vor
dem ersten Import gesetzt sein, die DB-Verbindung bleibt fuer die gesamte
Testsession bestehen (kein Reset zwischen Tests moeglich, anders als bei
file_store.py). Jeder Test verwendet deshalb einen eigenen, eindeutigen
Paketnamen statt DB-Isolation ueber tmp_path.
"""

import os
import tempfile

import pytest

_workdir = tempfile.mkdtemp(prefix="astrapi-packages-test-")
os.environ["ASTRAPI_PACKAGES_WORK_DIR"] = _workdir

from fastapi.testclient import TestClient  # noqa: E402

import astrapi_packages._app as app_mod  # noqa: E402

client = TestClient(app_mod.app)


@pytest.fixture(autouse=True)
def _reconnect_own_db():
    """Andere Testdateien reconfigurieren astrapi_core.system.db auf ihre
    eigene tmp_path (gleicher Prozess, gleiches Thread-Local) -- ohne das hier
    wuerde diese Datei je nach Ausfuehrungsreihenfolge gegen eine fremde,
    bereits wieder aufgeraeumte DB laufen ("no such table")."""
    from astrapi_core.system import db as core_db

    core_db._local.conn = None
    core_db.configure(app_mod.db_path())
    yield


@pytest.mark.parametrize("mod", ["debian", "archlinux"])
def test_new_in_db_dialog_rendert(mod):
    r = client.get(f"/ui/{mod}/new-in-db")
    assert r.status_code == 200
    assert "Erstellen" in r.text


@pytest.mark.parametrize("mod", ["debian", "archlinux"])
def test_new_in_db_legt_pkgbuild_an_und_oeffnet_editor(mod):
    from astrapi_packages.utils import file_store

    name = f"neu-editor-{mod}"
    r = client.post(f"/ui/{mod}/new-in-db", data={"name": name})
    assert r.status_code == 200
    assert f"files-tab-{mod}-{name}" in r.text

    content = file_store.read(mod, name, "PKGBUILD")
    assert content is not None
    assert f"pkgname={name}" in content


@pytest.mark.parametrize("mod", ["debian", "archlinux"])
def test_new_in_db_setzt_source_type_db(mod):
    name = f"neu-sourcetype-{mod}"
    client.post(f"/ui/{mod}/new-in-db", data={"name": name})

    if mod == "debian":
        from astrapi_packages.modules.debian import store
    else:
        from astrapi_packages.modules.archlinux import store

    assert store.get(name)["source_type"] == "db"


@pytest.mark.parametrize("mod", ["debian", "archlinux"])
def test_new_in_db_ohne_namen_zeigt_fehler(mod):
    r = client.post(f"/ui/{mod}/new-in-db", data={"name": ""})
    assert "erforderlich" in r.text


@pytest.mark.parametrize("mod", ["debian", "archlinux"])
def test_new_in_db_doppelter_name_zeigt_fehler(mod):
    name = f"neu-duplikat-{mod}"
    client.post(f"/ui/{mod}/new-in-db", data={"name": name})
    r = client.post(f"/ui/{mod}/new-in-db", data={"name": name})
    assert "bereits vorhanden" in r.text

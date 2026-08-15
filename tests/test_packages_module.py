"""Tests fuer das generische Pakete-Modul (ersetzt debian/archlinux, siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul") -- CRUD,
"Neu erstellen"-Flow, os_types-Filter, colon-IDs ({os_type}:{name}).

astrapi_packages._app baut die App als Modul-Singleton beim Import auf und
liest dabei einmalig ASTRAPI_PACKAGES_WORK_DIR -- die Env-Variable muss vor
dem ersten Import gesetzt sein, die DB-Verbindung bleibt fuer die gesamte
Testsession bestehen. Jeder Test verwendet deshalb einen eigenen,
eindeutigen Paketnamen statt DB-Isolation ueber tmp_path.
"""

import os
import tempfile

import pytest

_workdir = tempfile.mkdtemp(prefix="astrapi-packages-test-pkgmod-")
os.environ["ASTRAPI_PACKAGES_WORK_DIR"] = _workdir

from fastapi.testclient import TestClient  # noqa: E402

import astrapi_packages._app as app_mod  # noqa: E402

client = TestClient(app_mod.app)

# app_mod.db_path() liest work_dir() bei JEDEM Aufruf neu aus
# ASTRAPI_PACKAGES_WORK_DIR -- eine andere Testdatei koennte die Variable
# inzwischen ueberschrieben haben, obwohl der App-Singleton weiter gegen die
# urspruengliche DB laeuft. app_mod.ACTUAL_DB_PATH ist der beim tatsaechlichen
# (einzigen) create_app()-Lauf eingefrorene Pfad.
_DB_PATH = app_mod.ACTUAL_DB_PATH


@pytest.fixture(autouse=True)
def _reconnect_own_db():
    from astrapi_core.system import db as core_db

    from astrapi_packages.utils import file_store

    core_db._local.conn = None
    core_db.configure(_DB_PATH)
    # file_store haelt _table_ready als GLOBALES Modul-Flag (nicht pro Store-
    # Instanz wie bei BuilderImageStore etc.) -- eine andere Testdatei kann es
    # gegen ihre eigene tmp-DB auf True gesetzt haben, hier zurueck auf False,
    # sonst wird CREATE TABLE gegen DIESE Verbindung uebersprungen.
    file_store._table_ready = False
    yield


@pytest.fixture(scope="module", autouse=True)
def _os_types():
    """Legt die beiden OS-Typen einmal fuer die ganze Datei an -- Pakete
    brauchen einen existierenden os_type als Fremdschluessel.

    Reconnect hier explizit statt sich auf _reconnect_own_db (function-scoped)
    zu verlassen: modul-weite Fixtures laufen VOR funktions-weiten, ohne den
    Reconnect hier wuerde dieses Fixture ggf. gegen eine von einer anderen
    Testdatei hinterlassene, veraltete Verbindung laufen ("no such table")."""
    from astrapi_core.system import db as core_db

    core_db._local.conn = None
    core_db.configure(_DB_PATH)

    from astrapi_packages.modules.os_types import store as os_types_store

    if os_types_store.get("debian") is None:
        os_types_store.create("debian", {"label": "Debian", "repo_subdir": "debian"})
    if os_types_store.get("archlinux") is None:
        os_types_store.create(
            "archlinux",
            {
                "label": "Arch Linux",
                "repo_subdir": "arch/x86_64",
                "depends_url_template": "https://aur.archlinux.org/{name}.git",
            },
        )
    yield


# ── "Neu erstellen" (PKGBUILD direkt in der DB) ──────────────────────────────


@pytest.mark.parametrize("os_type", ["debian", "archlinux"])
def test_new_in_db_dialog_zeigt_os_typ_auswahl(os_type):
    r = client.get("/ui/packages/new-in-db")
    assert r.status_code == 200
    assert "OS-Typ" in r.text
    assert os_type in r.text


@pytest.mark.parametrize("os_type", ["debian", "archlinux"])
def test_new_in_db_legt_pkgbuild_an_und_oeffnet_editor(os_type):
    from astrapi_packages.utils import file_store

    name = f"neu-editor-{os_type}"
    r = client.post("/ui/packages/new-in-db", data={"name": name, "os_type": os_type})
    assert r.status_code == 200
    item_id = f"{os_type}:{name}"
    assert f"files-tab-packages-{item_id}" in r.text

    content = file_store.read("packages", item_id, "PKGBUILD")
    assert content is not None
    assert f"pkgname={name}" in content


def test_new_in_db_setzt_source_type_db():
    from astrapi_packages.modules.packages import store

    name = "neu-sourcetype"
    client.post("/ui/packages/new-in-db", data={"name": name, "os_type": "debian"})
    assert store.get(f"debian:{name}")["source_type"] == "db"


def test_new_in_db_ohne_namen_zeigt_fehler():
    r = client.post("/ui/packages/new-in-db", data={"name": "", "os_type": "debian"})
    assert "erforderlich" in r.text


def test_new_in_db_doppelter_name_zeigt_fehler():
    name = "neu-duplikat"
    client.post("/ui/packages/new-in-db", data={"name": name, "os_type": "debian"})
    r = client.post("/ui/packages/new-in-db", data={"name": name, "os_type": "debian"})
    assert "bereits vorhanden" in r.text


# ── Regulaeres CRUD, insbesondere mit ":" in der ID ──────────────────────────


def test_create_edit_delete_mit_colon_id():
    r = client.post(
        "/ui/packages/",
        data={
            "name": "htop",
            "os_type": "archlinux",
            "source_url": "https://aur.archlinux.org/htop.git",
            "pkg_type": "package",
            "enabled": "1",
        },
    )
    assert r.status_code == 200

    from astrapi_packages.modules.packages import store

    item = store.get("archlinux:htop")
    assert item is not None
    assert item["name"] == "htop"
    assert item["os_type"] == "archlinux"

    r = client.get("/ui/packages/archlinux:htop/edit")
    assert r.status_code == 200

    r = client.post(
        "/ui/packages/archlinux:htop/update",
        data={
            "source_url": "https://aur.archlinux.org/htop.git",
            "pkg_type": "package",
            "enabled": "1",
        },
    )
    assert r.status_code == 200

    r = client.delete("/api/packages/archlinux:htop")
    assert r.status_code == 204
    assert store.get("archlinux:htop") is None


def test_create_ohne_os_typ_zeigt_fehler():
    r = client.post("/ui/packages/", data={"name": "irgendwas", "os_type": ""})
    assert "erforderlich" in r.text


# ── OS-Typ-Filter im Header ───────────────────────────────────────────────────


def test_content_zeigt_os_typ_filter_optionen():
    r = client.get("/ui/packages/content")
    assert r.status_code == 200
    assert "debian" in r.text
    assert "archlinux" in r.text


# ── check-updates (generisch, PKGBUILD-Parsing statt AUR-Batch) ─────────────


def test_check_updates_laeuft_ohne_fehler():
    name = "check-updates-pkg"
    client.post("/ui/packages/new-in-db", data={"name": name, "os_type": "debian"})
    r = client.post("/ui/packages/check-updates")
    assert r.status_code == 200

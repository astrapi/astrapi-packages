"""Tests fuer das virtuelle OS-Modul: debian/archlinux werden nicht mehr
automatisch aus modules/ gescannt (liegen unter modules/_os_profiles/, per
Unterstrich-Praefix vom Scan ausgenommen), sondern in astrapi_packages._app
gezielt anhand der Einstellung packages_config.enable_debian/enable_archlinux
geladen.

astrapi_packages._app baut die App als Modul-Singleton beim Import auf (siehe
test_new_in_db.py) -- fuer diese Datei reicht es, die reine Auswahl-Funktion
_load_enabled_os_profiles() direkt zu testen (kein Neustart-Zwang wie beim
tatsaechlichen An-/Abschalten im echten Betrieb) plus einen In-Prozess-Check
der bereits laufenden Default-App.
"""

import os
import tempfile

import pytest

_workdir = tempfile.mkdtemp(prefix="astrapi-packages-test-osprofiles-")
os.environ["ASTRAPI_PACKAGES_WORK_DIR"] = _workdir

from fastapi.testclient import TestClient  # noqa: E402

import astrapi_packages._app as app_mod  # noqa: E402

client = TestClient(app_mod.app)

# Siehe test_new_in_db.py: app_mod.db_path() liest work_dir() bei jedem
# Aufruf neu, ACTUAL_DB_PATH ist der beim tatsaechlichen create_app()-Lauf
# eingefrorene Pfad -- unabhaengig davon, welche Testdatei zuletzt ihre eigene
# ASTRAPI_PACKAGES_WORK_DIR gesetzt hat.
_DB_PATH = app_mod.ACTUAL_DB_PATH


@pytest.fixture(autouse=True)
def _reconnect_own_db():
    from astrapi_core.system import db as core_db

    core_db._local.conn = None
    core_db.configure(_DB_PATH)
    yield


def test_as_bool_versteht_formular_strings():
    assert app_mod._as_bool("false", True) is False
    assert app_mod._as_bool("true", False) is True
    assert app_mod._as_bool(None, True) is True
    assert app_mod._as_bool(False, True) is False


def test_beide_os_profile_per_default_aktiv():
    found = app_mod._load_enabled_os_profiles()
    keys = {m.key for m in found}
    assert keys == {"debian", "archlinux"}


def test_deaktiviertes_profil_wird_nicht_geladen():
    from astrapi_core.ui.settings_registry import set_module

    set_module("packages_config", "enable_archlinux", False)
    try:
        found = app_mod._load_enabled_os_profiles()
        keys = {m.key for m in found}
        assert keys == {"debian"}
    finally:
        set_module("packages_config", "enable_archlinux", True)


def test_nav_zeigt_debian_und_archlinux_und_os_auswahl():
    r = client.get("/")
    assert r.status_code == 200
    assert "Debian" in r.text
    assert "Archlinux" in r.text
    assert "OS-Auswahl" in r.text


def test_settings_karte_zeigt_beide_schalter():
    r = client.get("/ui/settings/content")
    assert r.status_code == 200
    assert "enable_debian" in r.text
    assert "enable_archlinux" in r.text


def test_settings_speichern_ueber_formular_persistiert_string():
    r = client.post(
        "/ui/settings/save/module/packages_config",
        data={"enable_debian": "true", "enable_archlinux": "false"},
    )
    assert r.status_code == 200

    from astrapi_core.ui.settings_registry import get_module

    raw = get_module("packages_config", "enable_archlinux", True)
    assert app_mod._as_bool(raw, True) is False

    # aufraeumen fuer nachfolgende Tests in dieser Datei
    from astrapi_core.ui.settings_registry import set_module

    set_module("packages_config", "enable_archlinux", True)

"""astrapi_packages._app – ASGI-App-Factory.

Wird von astrapi_packages._cli (Console-Script) und direkt von uvicorn importiert:
    uvicorn astrapi_packages._app:app
"""

import logging
import time

from astrapi_core.system.paths import configure as _configure_paths

_configure_paths("astrapi-packages")

from astrapi_core.modules.settings.engine import configure as configure_settings
from astrapi_core.modules.system.engine import configure_updater
from astrapi_core.system.health import register_health
from astrapi_core.system.systemd import sd_notify, start_watchdog
from astrapi_core.system.version import get_display_name
from astrapi_core.ui import create as create_ui
from astrapi_core.ui.module_registry import load_modules
from astrapi_core.ui.settings_registry import init as settings_init
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from astrapi_packages._paths import db_path, package_dir, work_dir
from astrapi_packages.api.fastapi_app import create as create_api

_START_TIME = time.time()
_log = logging.getLogger(__name__)

_TABELLEN = ("archlinux_packages", "debian_packages")


def _spalte_vorhanden(con, tabelle: str, spalte: str) -> bool:
    """False auch dann, wenn es die Tabelle noch gar nicht gibt.

    Die Modul-Stores legen ihre Tabelle erst beim ersten Zugriff an.
    """
    return spalte in [r[1] for r in con.execute(f'PRAGMA table_info("{tabelle}")')]


def _reset_stale_status() -> None:
    """Setzt haengengebliebene Lauf-Status beim Start auf `error`.

    Beim Start kann per Definition nichts laufen: was noch auf "building" oder
    "pending" steht, stammt aus einem unterbrochenen Lauf (Neustart, Absturz,
    Update). Ohne das Zuruecksetzen zeigt die Liste dauerhaft einen Spinner
    und das Status-Polling laeuft endlos weiter.

    Bis T-148-PACKAGES war das Ergebnis `aborted` statt `error`, damit ein
    unterbrochener Lauf nicht aus der automatischen Aktualisierung faellt
    (T-132). Auf Nachfrage bewusst zurueckgebaut: der Fall ist selten genug,
    dass ein manueller Eingriff akzeptabel ist -- ein eigenes Vokabular nur
    dafuer lohnt den Pflegeaufwand nicht.

    `core.system.db.reset_stale_status()` greift hier nicht: die Funktion geht
    ueber die per `register_table()` registrierten Tabellen. archlinux und
    debian bringen ihre Tabellen selbst mit und sind dort nicht registriert,
    builder liegt als JSON im kvstore.
    """
    from astrapi_core.system.db import _conn

    from astrapi_packages.api import status as _status

    gesamt = 0
    con = _conn()
    for tabelle in _TABELLEN:
        try:
            if not _spalte_vorhanden(con, tabelle, "last_status"):
                continue
            cur = con.execute(
                f'UPDATE "{tabelle}" SET last_status = ? WHERE last_status IN (?, ?)',
                (_status.ERROR, *_status.LAEUFT),
            )
            gesamt += cur.rowcount or 0
        except Exception as e:
            _log.warning("reset_stale_status: Tabelle %s: %s", tabelle, e)
    if gesamt:
        con.commit()

    try:
        from astrapi_packages.modules.builder import store as builder_store

        for item_id, item in builder_store.list().items():
            if item.get("last_status") in _status.LAEUFT:
                builder_store.upsert(item_id, {"last_status": _status.ERROR})
                gesamt += 1
    except Exception as e:
        _log.warning("reset_stale_status: builder: %s", e)

    if gesamt:
        _log.info("reset_stale_status: %d unterbrochene Laeufe auf 'error' gesetzt", gesamt)


def _normalisiere_leeren_status() -> None:
    """Zieht den historischen Leerwert auf `neu` nach (T-134).

    G-010 gibt "neu" als Initialwert vor; astrapi-packages hat stattdessen ''
    geschrieben. Beide bedeuten "noch nie gebaut", aber zwei Schreibweisen fuer
    denselben Zustand laden zu Vergleichsfehlern ein. Idempotent -- nach dem
    ersten Start faellt die Bedingung auf null Zeilen.
    """
    from astrapi_core.system.db import _conn

    from astrapi_packages.api import status as _status

    con = _conn()
    gesamt = 0
    for tabelle in _TABELLEN:
        try:
            if not _spalte_vorhanden(con, tabelle, "last_status"):
                continue
            cur = con.execute(
                f'UPDATE "{tabelle}" SET last_status = ? WHERE last_status = ?',
                (_status.NEU, ""),
            )
            gesamt += cur.rowcount or 0
        except Exception as e:
            _log.warning("normalisiere_leeren_status: Tabelle %s: %s", tabelle, e)
    if gesamt:
        con.commit()
        _log.info("normalisiere_leeren_status: %d Eintraege von '' auf 'neu' gesetzt", gesamt)


# Bekannte OS-Profile unter modules/_os_profiles/. Der Unterstrich-Praefix
# haelt sie aus dem normalen Verzeichnis-Scan von load_modules() heraus (siehe
# _os_profiles/__init__.py) -- ein neues OS "erfinden" reicht als Einstellung
# nicht aus, es braucht immer ein Profil in dieser Liste.
_OS_PROFILE_SETTINGS = {
    "debian": "enable_debian",
    "archlinux": "enable_archlinux",
}


def _as_bool(value: object, default: bool = False) -> bool:
    """Einstellungen aus dem Formular kommen als String 'true'/'false' an
    (settings_save_module() wandelt sie nicht in echte Booleans um, siehe
    astrapi-mirror._sync_engine.validator._as_bool fuer dasselbe Muster) --
    ein rohes `if wert:` waere fuer den String 'false' faelschlich wahr.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_enabled_os_profiles() -> list:
    """Importiert genau die OS-Profile, die per Einstellung (Modul
    packages_config) aktiviert sind, und gibt ihre Module-Instanzen zurueck.

    Deaktivierte Profile werden nicht importiert -- sie tauchen weder in
    Navigation noch Scheduler noch API auf, bis die Einstellung geaendert und
    die App neu gestartet wird (Aenderungen an aktiven OS brauchen einen
    Neustart, da Routen nur einmal beim Start registriert werden).
    """
    import importlib

    from astrapi_core.ui.settings_registry import get_module as _get_setting

    found = []
    for os_type, setting_key in _OS_PROFILE_SETTINGS.items():
        if not _as_bool(_get_setting("packages_config", setting_key, True), True):
            continue
        try:
            mod = importlib.import_module(f"astrapi_packages.modules._os_profiles.{os_type}")
            found.append(mod.module)
        except Exception as e:
            _log.warning("OS-Profil '%s' konnte nicht geladen werden: %s", os_type, e)
    return found


def _db_check() -> tuple[bool, dict]:
    from astrapi_core.system.db import _conn

    try:
        _conn().execute("SELECT 1").fetchone()
        return True, {"db": True}
    except Exception:
        return False, {"db": False}


ACTUAL_DB_PATH = None  # von create_app() beim einzigen echten Lauf gesetzt


def create_app() -> FastAPI:
    global ACTUAL_DB_PATH
    _pkg = package_dir()
    configure_settings(health_fn=_db_check, app_name=get_display_name(_pkg))
    configure_updater(_pkg)

    from astrapi_core.system.db import configure as _configure_db
    from astrapi_core.system.db import create_all_registered_tables

    # db_path() liest work_dir() bei jedem Aufruf neu aus der Env-Variable --
    # hier einmalig einfrieren, sonst wuerde ein spaeterer db_path()-Aufruf
    # (z.B. aus einem Test, der seinerseits die Variable fuer sich selbst neu
    # setzt) auf einen anderen Pfad zeigen als den, gegen den create_app()
    # tatsaechlich die Tabellen angelegt hat.
    ACTUAL_DB_PATH = db_path()
    _configure_db(ACTUAL_DB_PATH)
    create_all_registered_tables()

    settings_init(work_dir())

    modules, _ = load_modules(_pkg)
    modules += _load_enabled_os_profiles()
    _reset_stale_status()
    _normalisiere_leeren_status()
    api = create_api(modules=modules)

    from pathlib import Path

    import astrapi_core.ui

    core_static = Path(astrapi_core.ui.__file__).parent / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")

    create_ui(api, app_root=_pkg, modules=modules)

    register_health(api, check_fn=_db_check, start_time=_START_TIME)
    start_watchdog(check_fn=lambda: _db_check()[0])
    sd_notify("READY=1")
    return api


app = create_app()

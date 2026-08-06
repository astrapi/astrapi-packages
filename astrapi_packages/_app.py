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

# Laufzeit-Status, die nur waehrend eines Baus gesetzt sind
_STALE_STATUS = ("building", "pending")


def _reset_stale_status() -> None:
    """Setzt haengengebliebene Lauf-Status beim Start zurueck.

    Beim Start kann per Definition nichts laufen: was noch auf "building" oder
    "pending" steht, stammt aus einem abgebrochenen Lauf (Neustart, Absturz,
    Update). Ohne das Zuruecksetzen zeigt die Liste dauerhaft einen Spinner
    und das Status-Polling laeuft endlos weiter.

    `core.system.db.reset_stale_status()` greift hier nicht: die Funktion geht
    ueber die per `register_table()` registrierten Tabellen. archlinux und
    debian bringen ihre Tabellen selbst mit und sind dort nicht registriert,
    builder liegt als JSON im kvstore.
    """
    from astrapi_core.system.db import _conn

    gesamt = 0
    con = _conn()
    for tabelle in ("archlinux_packages", "debian_packages"):
        try:
            spalten = [r[1] for r in con.execute(f'PRAGMA table_info("{tabelle}")')]
            if "last_status" not in spalten:
                continue  # Tabelle wird erst beim ersten Store-Zugriff angelegt
            cur = con.execute(
                f'UPDATE "{tabelle}" SET last_status = ? WHERE last_status IN (?, ?)',
                ("error", *_STALE_STATUS),
            )
            gesamt += cur.rowcount or 0
        except Exception as e:
            _log.warning("reset_stale_status: Tabelle %s: %s", tabelle, e)
    if gesamt:
        con.commit()

    try:
        from astrapi_packages.modules.builder import store as builder_store

        for item_id, item in builder_store.list().items():
            if item.get("last_status") in _STALE_STATUS:
                builder_store.upsert(item_id, {"last_status": "error"})
                gesamt += 1
    except Exception as e:
        _log.warning("reset_stale_status: builder: %s", e)

    if gesamt:
        _log.info("reset_stale_status: %d abgebrochene Laeufe zurueckgesetzt", gesamt)


def _db_check() -> tuple[bool, dict]:
    from astrapi_core.system.db import _conn

    try:
        _conn().execute("SELECT 1").fetchone()
        return True, {"db": True}
    except Exception:
        return False, {"db": False}


def create_app() -> FastAPI:
    _pkg = package_dir()
    configure_settings(health_fn=_db_check, app_name=get_display_name(_pkg))
    configure_updater(_pkg)

    from astrapi_core.system.db import configure as _configure_db
    from astrapi_core.system.db import create_all_registered_tables

    _configure_db(db_path())
    create_all_registered_tables()

    settings_init(work_dir())

    modules, _ = load_modules(_pkg)
    _reset_stale_status()
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

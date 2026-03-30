"""packagectl._app – ASGI-App-Factory.

Wird von packagectl._cli (Console-Script) und direkt von uvicorn importiert:
    uvicorn packagectl._app:app
"""
import time

from astrapi.core.system.paths import configure as _configure_paths
_configure_paths("packagectl")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from a2wsgi import WSGIMiddleware

from astrapi.core.ui import create as create_ui
from astrapi.core.ui.module_registry import load_modules
from astrapi.core.ui.settings_registry import init as settings_init
from astrapi.core.system.health import register_health
from astrapi.core.system.systemd import sd_notify, start_watchdog
from astrapi.core.system.version import get_display_name
from astrapi.core.modules.settings.engine import configure as configure_settings

from packagectl._paths import package_dir, work_dir, db_path
from packagectl.api.fastapi_app import create as create_api

_START_TIME = time.time()


def _db_check() -> tuple[bool, dict]:
    from astrapi.core.system.db import _conn
    try:
        _conn().execute("SELECT 1").fetchone()
        return True, {"db": True}
    except Exception:
        return False, {"db": False}


def create_app() -> FastAPI:
    _pkg = package_dir()
    configure_settings(health_fn=_db_check, app_name=get_display_name(_pkg))

    from astrapi.core.system.db import configure as _configure_db, create_all_registered_tables
    _configure_db(db_path())
    create_all_registered_tables()

    settings_init(work_dir())
    modules, _ = load_modules(_pkg)
    api = create_api(modules=modules)
    ui  = create_ui(app_root=_pkg, modules=modules)

    import astrapi.core.ui
    from pathlib import Path
    core_static = Path(astrapi.core.ui.__file__).parent / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")
    api.mount("/", WSGIMiddleware(ui))

    register_health(api, check_fn=_db_check, start_time=_START_TIME)
    start_watchdog(check_fn=lambda: _db_check()[0])
    sd_notify("READY=1")
    return api


app = create_app()

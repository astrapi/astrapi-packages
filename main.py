"""
backupctl – Einstiegspunkt (FastAPI + Flask)

FastAPI  → /api/...       JSON-Endpunkte, OpenAPI, Swagger
Flask    → /              UI, HTMX-Partials, Modals

Start:
    python main.py              # Port 5001 (Standard)
    python main.py --port 8080
    python main.py --no-reload  # ohne File-Watcher
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_ROOT     = PROJECT_ROOT / "app"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from a2wsgi import WSGIMiddleware
import uvicorn

from core.ui import create as create_ui
from core.ui.module_registry import load_modules
from core.ui.settings_registry import init as settings_init
from core.system.health import register_health
from core.system.systemd import sd_notify, start_watchdog
from core.system.version import get_display_name
from core.modules.settings.engine import configure as configure_settings
from app.api.fastapi_app import create as create_api

_START_TIME = time.time()


def _db_check() -> tuple[bool, dict]:
    from core.system.db import _conn
    try:
        _conn().execute("SELECT 1").fetchone()
        return True, {"db": True}
    except Exception:
        return False, {"db": False}


def create_app() -> FastAPI:
    configure_settings(health_fn=_db_check, app_name=get_display_name(APP_ROOT))

    # DB zuerst konfigurieren, damit settings_registry + SqliteStorage SQLite nutzen können
    from core.system.db import configure as _configure_db, create_all_registered_tables
    _configure_db(APP_ROOT / "data" / "app.db")
    create_all_registered_tables()

    settings_init(APP_ROOT)
    modules = load_modules(APP_ROOT)
    api = create_api(modules=modules)
    ui  = create_ui(app_root=APP_ROOT, modules=modules)

    core_static = PROJECT_ROOT / "core" / "ui" / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")
    api.mount("/", WSGIMiddleware(ui))

    register_health(api, check_fn=_db_check, start_time=_START_TIME)
    start_watchdog(check_fn=lambda: _db_check()[0])
    sd_notify("READY=1")
    return api


app = create_app()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-reload", dest="reload", action="store_false", default=True)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)

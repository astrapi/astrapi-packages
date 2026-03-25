"""
app/api/fastapi_app.py  –  FastAPI-Factory V3

Registriert automatisch alle Modul-Router aus app/modules/.
"""
from pathlib import Path
import time
from fastapi import FastAPI
from core.system.health import register_health
from core.system.version import get_app_version

APP_ROOT = Path(__file__).resolve().parents[1]


def _load_api_meta() -> tuple[str, str]:
    """Liest App-Name aus config.yaml und Version aus version.yaml."""
    name = "Astrapi API"
    try:
        import yaml as _yaml
        cfg_path = APP_ROOT / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                raw = _yaml.safe_load(f) or {}
            name = raw.get("app", {}).get("name", name) + " API"
    except Exception:
        pass
    version = get_app_version(APP_ROOT, default="0.0.0")
    return name, version


def create(modules: list | None = None) -> FastAPI:
    """Erstellt die FastAPI-Anwendung.

    modules: Vorgeladene Modulliste (z.B. aus main.py). Wird nicht neu geladen
             wenn angegeben – verhindert doppelten Modulaufruf.
    """
    _title, _version = _load_api_meta()
    app = FastAPI(
        title=_title,
        version=_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── Modul-Router registrieren (nur laden wenn nicht übergeben) ────────────
    from core.ui.module_registry import load_modules, register_fastapi_modules
    if modules is None:
        modules = load_modules(APP_ROOT)
    register_fastapi_modules(app, modules)

    # ── Health-Check ──────────────────────────────────────────────────────────
    register_health(app, path="/api/health", tags=["system"], start_time=time.time())

    return app

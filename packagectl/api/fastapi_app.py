"""packagectl.api.fastapi_app – FastAPI-Factory."""
from fastapi import FastAPI
from astrapi.core.system.version import get_app_version

from packagectl._paths import package_dir

APP_ROOT = package_dir()


def create(modules: list | None = None) -> FastAPI:
    """Erstellt die FastAPI-Anwendung.

    modules: Vorgeladene Modulliste (z.B. aus _app.py). Wird nicht neu geladen
             wenn angegeben – verhindert doppelten Modulaufruf.
    """
    _version = get_app_version(APP_ROOT, default="1.0.0")
    app = FastAPI(
        title="PackageCtl API",
        version=_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    from astrapi.core.ui.module_registry import load_modules, register_fastapi_modules
    if modules is None:
        modules, _ = load_modules(APP_ROOT)
    register_fastapi_modules(app, modules)

    return app

"""app/modules/docker/ui/crud.py – FastAPI-UI-Router für das Docker-Modul."""

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router

from astrapi_packages.modules.docker import _KEY as KEY
from astrapi_packages.modules.docker import store

_DIR = Path(__file__).parent.parent

router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),  # existiert nicht → leere Felder
    has_run_buttons=True,
    has_toggle=False,
    has_status=True,
)

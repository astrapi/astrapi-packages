"""astrapi_packages.modules.os_types.ui.crud – FastAPI-UI-Router für os_types.

Rein datengetrieben ueber schema.yaml -- kein Datei-Editor-Tab noetig (anders
als builder/packages), daher der vollstaendig generische crud_blueprint-Pfad
ohne eigene Create/Edit-Routen.
"""

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router

from astrapi_packages.modules.os_types import KEY, store

_DIR = Path(__file__).parent.parent

router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="OS-Typ",
    description_field="key",
    has_create=True,
    has_edit=True,
    has_delete=True,
    has_run_buttons=False,
    has_toggle=False,
    has_status=False,
)

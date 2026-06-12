"""app/modules/builder/ui/crud.py – FastAPI-UI-Router für das Builder-Modul."""

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.render import render
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_packages.modules.builder import _KEY as KEY
from astrapi_packages.modules.builder import _docker_items, store

_DIR = Path(__file__).parent.parent


class _ImageStoreProxy:
    """Proxy: list() liefert IMAGES mit Defaults (enabled=True), alle anderen
    Methoden delegieren an den echten Store."""

    def list(self):
        return _docker_items()

    def __getattr__(self, name):
        return getattr(store, name)


_proxy_store = _ImageStoreProxy()


def _running_fn() -> dict:
    return {
        f"{KEY}:{item_id}": "building"
        for item_id, item in _docker_items().items()
        if item.get("last_status") == "building"
    }


def _ctx() -> dict:
    return dict(
        cfg=_docker_items(),
        module=KEY,
        container_id=f"mod-{KEY}",
        loading_id=f"{KEY}-loading",
        running=_running_fn(),
    )


_crud = make_crud_router(
    _proxy_store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    has_create=False,
    has_edit=False,
    has_delete=False,
    has_run_buttons=True,
    has_toggle=False,
    has_status=True,
    running_fn=_running_fn,
)

router = APIRouter()


@router.get(f"/ui/{KEY}/status", response_class=HTMLResponse)
def status(request: Request):
    return render(request, "partials/status_oob.html", _ctx())


router.include_router(_crud)

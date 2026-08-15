"""app/modules/builder/ui/crud.py – FastAPI-UI-Router für das Builder-Modul."""

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.render import render
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_packages.modules.builder import _KEY as KEY
from astrapi_packages.modules.builder import store
from astrapi_packages.utils.export_import import build_export_import_routes
from astrapi_packages.utils.file_routes import build_file_routes

_EXPORT_FIELDS = ["tag", "module"]

_DIR = Path(__file__).parent.parent


def _running_fn() -> dict:
    return {
        f"{KEY}:{item_id}": "building"
        for item_id, item in store.list().items()
        if item.get("last_status") == "building"
    }


def _ctx() -> dict:
    return dict(
        cfg=store.list(),
        module=KEY,
        container_id=f"mod-{KEY}",
        loading_id=f"{KEY}-loading",
        running=_running_fn(),
    )


router = APIRouter()


@router.get(f"/ui/{KEY}/status", response_class=HTMLResponse)
def status(request: Request):
    return render(request, "partials/oob/status_oob.html", _ctx())


# ── Create/Edit-Modals ────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(item_id=None, item=None, error=None),
    )


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def create_apply(request: Request):
    form = await request.form()
    item_id = form.get("id", "").strip()

    if not item_id:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(item_id=None, item=dict(form), error="Image-ID ist erforderlich."),
        )

    if store.get(item_id) is not None:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(item_id=None, item=dict(form), error=f"'{item_id}' ist bereits vorhanden."),
        )

    data = {
        "tag": form.get("tag", "latest").strip() or "latest",
        "module": form.get("module", "").strip(),
        "last_status": "neu",
    }
    store.create(item_id, data)
    return render(request, "content.html", _ctx())


@router.get(f"/ui/{KEY}/{{item_id}}/edit", response_class=HTMLResponse)
def edit_modal(item_id: str, request: Request):
    item = store.get(item_id)
    if item is None:
        return HTMLResponse("Nicht gefunden", status_code=404)
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(item_id=item_id, item=item, error=None),
    )


@router.post(f"/ui/{KEY}/{{item_id}}/update", response_class=HTMLResponse)
async def edit_apply(item_id: str, request: Request):
    form = await request.form()
    if store.get(item_id) is not None:
        data = {
            "tag": form.get("tag", "latest").strip() or "latest",
            "module": form.get("module", "").strip(),
        }
        store.update(item_id, data)
    return render(request, "content.html", _ctx())


_crud = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Builder-Image",
    description_field="id",
    has_create=True,
    has_edit=True,
    has_delete=True,
    has_run_buttons=True,
    has_toggle=False,
    has_status=True,
    running_fn=_running_fn,
)

router.include_router(_crud)
router.include_router(build_file_routes(KEY))
router.include_router(build_export_import_routes(KEY, store, _EXPORT_FIELDS))

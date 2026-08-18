"""app/modules/builder/ui/crud.py – FastAPI-UI-Router für das Builder-Modul."""

import json as _json
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.render import render
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from astrapi_packages.modules.builder import _KEY as KEY
from astrapi_packages.modules.builder import store
from astrapi_packages.modules.builder.utils import image_cache

_DIR = Path(__file__).parent.parent

# Hintergrund-Cache starten
image_cache.start()


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


# ── Create/Edit-Modals (Image-Suche statt manueller Eingabe) ─────────────────


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(item_id=None, item=None, error=None, no_source=not image_cache.has_source()),
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
        return Response(
            content="",
            status_code=200,
            headers={
                "HX-Reswap": "none",
                "HX-Trigger": _json.dumps({"builderModalError": f"'{item_id}' ist bereits vorhanden."}),
            },
        )

    data = {
        "source_url": form.get("source_url", "").strip(),
        "source_subdir": form.get("source_subdir", "").strip(),
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
            "source_url": form.get("source_url", "").strip(),
            "source_subdir": form.get("source_subdir", "").strip(),
            "tag": form.get("tag", "latest").strip() or "latest",
            "module": form.get("module", "").strip(),
        }
        store.update(item_id, data)
    return render(request, "content.html", _ctx())


# ── Image-Suche (HTMX) ────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/search", response_class=HTMLResponse)
def search_images(request: Request):
    term = request.query_params.get("q", "").strip()
    if len(term) < 2:
        return HTMLResponse("")
    if not image_cache.get_all():
        import threading

        threading.Thread(target=image_cache.refresh, daemon=True).start()
    results = image_cache.search(term)
    return render(
        request,
        f"{KEY}/dialogs/edit/search_results.html",
        dict(
            results=results,
            term=term,
            cache_empty=not image_cache.get_all(),
            no_source=not image_cache.has_source(),
        ),
    )


@router.post(f"/ui/{KEY}/image-cache/refresh", response_class=HTMLResponse)
async def refresh_image_cache(request: Request):
    """Laedt images.yaml sofort neu statt bis zu 5 Min. auf den Hintergrund-
    Refresh zu warten -- z.B. direkt nach dem Veroeffentlichen eines neuen
    Images im Repo."""
    image_cache.refresh()
    form = await request.form()
    term = (form.get("q") or "").strip()
    if len(term) < 2:
        return HTMLResponse("")
    results = image_cache.search(term)
    return render(
        request,
        f"{KEY}/dialogs/edit/search_results.html",
        dict(
            results=results,
            term=term,
            cache_empty=not image_cache.get_all(),
            no_source=not image_cache.has_source(),
        ),
    )


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

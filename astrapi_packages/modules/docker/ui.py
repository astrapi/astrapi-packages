"""app/modules/docker/ui.py – FastAPI-Router für das Docker-Modul."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_core.ui.render import render, render_string
from astrapi_core.ui.page_factory import register_content_renderer
from .images import IMAGES
from .storage import store

KEY    = "docker"
router = APIRouter()


def _items() -> dict:
    """Liefert alle definierten Images mit aktuellem Runtime-Status."""
    return {
        img_id: {"tag": cfg["tag"], **(store.get(img_id) or {})}
        for img_id, cfg in IMAGES.items()
    }


def _ctx(**extra) -> dict:
    items = _items()
    running = {
        f"{KEY}:{k}": v["last_status"]
        for k, v in items.items()
        if v.get("last_status") == "building"
    }
    return dict(
        cfg=items,
        module=KEY,
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/card_body.html",
        running=running,
        has_create=False,
        has_edit=False,
        has_delete=False,
        has_toggle=False,
        **extra,
    )


register_content_renderer(KEY, lambda request: render_string(request, "content.html", _ctx()))


# ── Listen-Route ──────────────────────────────────────────────────────────────

@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def content(request: Request):
    return render(request, "content.html", _ctx())


# ── Modulspezifische Routen ───────────────────────────────────────────────────

@router.get(f"/ui/{KEY}/status", response_class=HTMLResponse)
def status(request: Request):
    return render(request, "partials/list_wrapper_inner.html", _ctx())


@router.post(f"/ui/{KEY}/{{item_id}}/build", response_class=HTMLResponse)
def build_item(item_id: str, request: Request):
    if item_id not in IMAGES:
        return HTMLResponse("Nicht gefunden", status_code=404)
    store.upsert(item_id, {"last_status": "building"})
    from .jobs import build_image_async
    build_image_async(item_id)
    return render(request, "partials/list_wrapper_inner.html", _ctx())


@router.get(f"/ui/{KEY}/{{item_id}}/log", response_class=HTMLResponse)
def log_item(item_id: str, request: Request):
    item = store.get(item_id) or {}
    return render(request, f"{KEY}/modals/log.html", dict(
        item_id=item_id,
        item_data=item,
    ))


@router.get(f"/ui/{KEY}/{{item_id}}/log-content", response_class=HTMLResponse)
def log_content(item_id: str, request: Request):
    item = store.get(item_id) or {}
    return render(request, f"{KEY}/partials/log_content.html", dict(
        item_id=item_id,
        item_data=item,
    ))

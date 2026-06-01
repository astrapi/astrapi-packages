"""astrapi_packages.modules.debian.ui.crud – FastAPI-UI-Router für das Debian-Modul."""

import threading
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.render import render
from astrapi_core.ui.schema_loader import load_schema
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from astrapi_packages.modules.debian import KEY, store

_DIR = Path(__file__).parent.parent  # modules/debian/
_SCHEMA = load_schema(str(_DIR / "config" / "schema.yaml"))

# Hintergrund-Cache starten
import importlib.util as _ilu
import sys as _sys

_cache_key = "_debian_pkg_cache"
if _cache_key not in _sys.modules:
    _spec = _ilu.spec_from_file_location(_cache_key, _DIR / "utils" / "pkg_cache.py")
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules[_cache_key] = _mod
    _spec.loader.exec_module(_mod)
    _mod.start()


def _running_fn() -> dict:
    return {
        f"{KEY}:{k}": v["last_status"]
        for k, v in store.list().items()
        if v.get("last_status") in ("building", "pending")
    }


_crud = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Paket",
    description_field="name",
    has_run_buttons=True,
    running_fn=_running_fn,
)

router = APIRouter()


def _ctx():
    cfg = store.list()
    return dict(
        cfg=cfg,
        module=KEY,
        container_id=f"mod-{KEY}",
        loading_id=f"{KEY}-loading",
        running=_running_fn(),
    )


# ── Status-Route (HTMX-Polling) ───────────────────────────────────────────────


@router.get(f"/ui/{KEY}/status", response_class=HTMLResponse)
def status(request: Request):
    return render(request, "partials/status_oob.html", _ctx())


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
    item_id = form.get("name", "").strip()

    if not item_id:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(item_id=None, item=dict(form), error="Paketname ist erforderlich."),
        )

    if store.get(item_id) is not None:
        import json as _json

        return Response(
            content="",
            status_code=200,
            headers={
                "HX-Reswap": "none",
                "HX-Trigger": _json.dumps(
                    {"debianModalError": f'"{item_id}" ist bereits vorhanden.'}
                ),
            },
        )

    data = {
        "source_url": form.get("source_url", "").strip(),
        "distribution": form.get("distribution", "bookworm").strip() or "bookworm",
        "component": form.get("component", "main").strip() or "main",
        "pkg_type": form.get("pkg_type", "package").strip() or "package",
        "enabled": "enabled" in form,
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
            "distribution": form.get("distribution", "bookworm").strip() or "bookworm",
            "component": form.get("component", "main").strip() or "main",
            "pkg_type": form.get("pkg_type", "package").strip() or "package",
            "enabled": "enabled" in form,
        }
        store.update(item_id, data)
    return render(request, "content.html", _ctx())


# ── Alle bauen ────────────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/search", response_class=HTMLResponse)
def search_packages(request: Request):
    term = request.query_params.get("q", "").strip()
    if len(term) < 2:
        return HTMLResponse("")
    pkg_cache = _sys.modules.get(_cache_key)
    if pkg_cache and not pkg_cache.get_all():
        import threading

        threading.Thread(target=pkg_cache.refresh, daemon=True).start()
    results = pkg_cache.search(term) if pkg_cache else []
    return render(
        request,
        f"{KEY}/dialogs/edit/search_results.html",
        dict(results=results, term=term, cache_empty=pkg_cache and not pkg_cache.get_all()),
    )


# ── Alle bauen ────────────────────────────────────────────────────────────────


@router.post(f"/ui/{KEY}/build-all", response_class=HTMLResponse)
def build_all(request: Request):
    from astrapi_packages.modules.debian.jobs import update_all_packages

    threading.Thread(target=update_all_packages, daemon=True).start()
    return render(request, "content.html", _ctx())


# ── CRUD-Router einbinden ─────────────────────────────────────────────────────

router.include_router(_crud)

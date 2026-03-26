"""
core/ui/htmx_crud_router.py – Generischer HTMX-CRUD-Router für Form-basierte UIs

Erzeugt einen APIRouter mit HTMX-tauglichen CRUD-Endpunkten:
  POST   /create              → Anlegen (Form-Daten)
  PATCH  /{item_id}/edit      → Aktualisieren (Form-Daten)
  DELETE /{item_id}/delete    → Löschen
  POST   /{item_id}/toggle    → enabled-Flag umschalten

Verwendung:
    from astrapi.core.ui.htmx_crud_router import make_htmx_crud_router
    from pathlib import Path

    KEY = "mymodule"
    _SCHEMA_PATH = Path(__file__).parent / "schema.yaml"

    router = make_htmx_crud_router(KEY, _SCHEMA_PATH)

    # Modulspezifische Routen einfach hinzufügen:
    @router.get("/{item_id}/preview")
    def preview_item(...): ...
"""

import yaml
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Header, Response
from fastapi.responses import HTMLResponse


def make_htmx_crud_router(
    key: str,
    schema_path: Path,
    *,
    post_process: Callable[[dict], dict] | None = None,
    preview_fn: Callable[[str], list[dict]] | None = None,
) -> APIRouter:
    """Erstellt einen HTMX-CRUD-Router für ein Modul.

    Args:
        key:          Modulname (z.B. "borg", "rsync")
        schema_path:  Pfad zur schema.yaml des Moduls
        post_process: Optionale Funktion die das payload-Dict nach dem Einlesen
                      transformiert (z.B. description aus host ableiten).
    """
    router = APIRouter()

    def _load_schema() -> dict:
        try:
            return yaml.safe_load(schema_path.read_text()) or {}
        except FileNotFoundError:
            raise HTTPException(500, f"Schema-Datei nicht gefunden: {schema_path}")
        except yaml.YAMLError as e:
            raise HTTPException(500, f"Schema-Datei fehlerhaft: {e}")

    def _list_response(request: Request):
        from api.templates import templates
        from api.storage import load_config
        from api.routers.run import get_running
        content = templates.TemplateResponse(
            "partials/list_wrapper_inner.html",
            {
                "request":          request,
                "cfg":              load_config(key),
                "module":           key,
                "content_template": f"{key}/partials/list.html",
                "container_id":     f"tab-{key}",
                "loading_id":       f"{key}-loading",
                "running":          get_running(),
            },
        ).body.decode()
        return HTMLResponse(content, headers={
            "HX-Retarget": f"#tab-{key}",
            "HX-Reswap":   "innerHTML",
        })

    def _clean(data: dict) -> dict:
        return {
            k: v for k, v in data.items()
            if v is not None
            and not (isinstance(v, str) and v.strip() == "")
            and not (isinstance(v, list) and len(v) == 0)
        }

    def _extract_lists(schema: dict, payload: dict) -> dict:
        fields = schema.get("fields", [])
        list_fields = [f["name"] for f in fields if f.get("type") == "list" and f.get("name")]
        lists: dict = {n: [] for n in list_fields}
        for k, v in payload.items():
            for ln in list_fields:
                if k.startswith(f"{ln}_"):
                    try:
                        idx = int(k[len(ln) + 1:])
                        lists[ln].append((idx, v))
                    except ValueError:
                        pass
        for n in list_fields:
            lists[n] = [v for _, v in sorted(lists[n])]
        prefixes = tuple(f"{n}_" for n in list_fields)
        clean_payload = {k: v for k, v in payload.items() if not any(k.startswith(p) for p in prefixes)}
        for f in fields:
            if not f.get("name") or f.get("type") in ("list", "section"):
                continue
            if f["name"] not in clean_payload:
                clean_payload[f["name"]] = ""
        for n in list_fields:
            clean_payload[n] = lists[n]
        return clean_payload

    def _parse_form(form, schema: dict) -> dict:
        payload = dict(form)
        payload["enabled"] = payload.get("enabled") in ("on", "1", True)
        payload = _extract_lists(schema, payload)
        if post_process:
            payload = post_process(payload)
        return payload

    @router.post("/create")
    async def create_one(request: Request):
        from api.storage import save_item, next_item_id
        form    = await request.form()
        payload = _parse_form(form, _load_schema())
        save_item(key, next_item_id(key), _clean(payload))
        if request.headers.get("HX-Request") == "true":
            return _list_response(request)
        return payload

    @router.patch("/{item_id}/edit")
    async def patch_one(item_id: str, request: Request):
        from api.storage import get_item, save_item
        iid      = int(item_id)
        existing = get_item(key, iid)
        if existing is None:
            raise HTTPException(404, "Item not found")
        form    = await request.form()
        payload = _parse_form(form, _load_schema())
        existing.update(payload)
        save_item(key, iid, _clean(existing))
        if request.headers.get("HX-Request") == "true":
            return _list_response(request)
        return existing

    @router.delete("/{item_id}/delete")
    def delete_one(request: Request, item_id: str, hx_request: str | None = Header(None)):
        from api.storage import delete_item
        if not delete_item(key, item_id):
            raise HTTPException(404, "Item not found")
        if hx_request:
            return _list_response(request)
        return Response(status_code=204)

    if preview_fn is not None:
        @router.get("/{item_id}/preview")
        def preview_item(item_id: str, request: Request):
            from api.templates import templates
            from api.storage import get_item
            entry = get_item(key, item_id)
            if entry is None:
                raise HTTPException(404, "Item not found")
            return templates.TemplateResponse("partials/preview_modal.html", {
                "request":     request,
                "description": entry.get("description", item_id),
                "commands":    preview_fn(item_id),
            })

    @router.post("/{item_id}/toggle")
    def toggle_item(request: Request, item_id: str, hx_request: str | None = Header(None)):
        from api.storage import load_config, save_item
        cfg = load_config(key)
        iid = item_id
        if iid not in cfg:
            try:
                iid = int(item_id)
            except ValueError:
                pass
        if iid not in cfg:
            raise HTTPException(404, "Item not found")
        cfg[iid]["enabled"] = not cfg[iid].get("enabled", False)
        save_item(key, iid, cfg[iid])
        if hx_request:
            return _list_response(request)
        return {"status": "ok", "item": iid, "enabled": cfg[iid]["enabled"]}

    return router

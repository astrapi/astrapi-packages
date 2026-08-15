"""astrapi_packages.utils.export_import – Export/Import von DB-verwalteten
Paketen/Builder-Images zwischen App-Instanzen (Dev → Prod), siehe
projects/packages/planung-datei-editor.md, Etappe 4/1.4/2.5.

Ersetzt eine klassische Migration: da die Versionierung in der App-eigenen
DB liegt (kein Git-Push/Pull mehr als impliziter Transportweg), braucht es
einen expliziten Weg, fertige Inhalte auf eine andere Instanz zu übertragen.

Export bewusst ohne Historie -- nur der aktuelle, fertige Stand. Import
landet je Datei als neue aktuelle Version (Append-only-Prinzip aus
file_store.py bleibt gewahrt, nichts wird überschrieben/gelöscht).
"""

import json
from typing import Any

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from astrapi_packages.utils import file_store


def export_items(
    owner_type: str,
    store: Any,
    metadata_fields: list[str],
    item_ids: list[str] | None = None,
) -> list[dict]:
    """Baut eine JSON-serialisierbare Liste von Export-Datensätzen.

    metadata_fields: welche Store-Felder mit exportiert werden (z.B. tag/
    module bei Buildern, source_url/pkg_type/... bei Paketen) -- bewusst
    kein Blindexport aller Felder, damit Laufzeit-Status (last_status/
    last_run/last_log) nicht versehentlich mit übertragen wird.
    """
    all_items = store.list()
    ids = item_ids if item_ids is not None else list(all_items.keys())

    result = []
    for item_id in ids:
        item = all_items.get(item_id) or store.get(item_id)
        if item is None:
            continue
        metadata = {k: item.get(k) for k in metadata_fields if k in item}
        files = [
            {"filename": f["filename"], "content": f["content"]}
            for f in file_store.list_files(owner_type, item_id)
        ]
        result.append({"item_id": item_id, "metadata": metadata, "files": files})
    return result


def import_items(owner_type: str, store: Any, data: list[dict]) -> dict:
    """Importiert eine Export-Liste: legt fehlende Einträge an, gleicht
    vorhandene ab (Natural Key: item_id), übernimmt jede Datei als neue
    aktuelle Version. Gibt eine Zusammenfassung zurück."""
    created = 0
    updated = 0
    files_imported = 0

    for entry in data:
        item_id = entry.get("item_id")
        if not item_id:
            continue
        metadata = entry.get("metadata") or {}
        if store.get(item_id) is None:
            store.create(item_id, metadata)
            created += 1
        else:
            store.update(item_id, metadata)
            updated += 1

        for f in entry.get("files") or []:
            filename = f.get("filename")
            content = f.get("content", "")
            if not filename:
                continue
            file_store.save(
                owner_type, item_id, filename, content, message="Import (Export/Import)"
            )
            files_imported += 1

    return {"created": created, "updated": updated, "files_imported": files_imported}


def build_export_import_routes(
    owner_type: str, store: Any, metadata_fields: list[str]
) -> APIRouter:
    """Generische Export/Import-Routen -- von builder/debian/archlinux gemeinsam
    genutzt (dünner Wrapper um export_items()/import_items())."""
    router = APIRouter()

    # Bulk-Export bewusst unter /ui/ statt /api/{owner_type}/export: der generische
    # JSON-CRUD-Router (crud_router.py) registriert dort bereits GET /{item_id} --
    # ein zweiter, gleich tiefer Pfad wuerde je nach Registrierungsreihenfolge
    # "export" als item_id fehlinterpretieren (first-match-wins).
    @router.get(f"/ui/{owner_type}/export")
    def export_all():
        data = export_items(owner_type, store, metadata_fields)
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": f'attachment; filename="{owner_type}-export.json"'},
        )

    @router.get(f"/api/{owner_type}/{{item_id}}/export")
    def export_one(item_id: str):
        data = export_items(owner_type, store, metadata_fields, item_ids=[item_id])
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": f'attachment; filename="{owner_type}-{item_id}.json"'},
        )

    @router.post(f"/api/{owner_type}/import")
    async def import_upload(file: UploadFile):
        raw = await file.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return JSONResponse({"error": f"Ungültiges JSON: {e}"}, status_code=400)
        if not isinstance(data, list):
            return JSONResponse({"error": "Erwartet ein JSON-Array."}, status_code=400)
        summary = import_items(owner_type, store, data)
        return summary

    # ── UI-Varianten (Dialog + HTML-Antwort statt JSON) ─────────────────────

    @router.get(f"/ui/{owner_type}/import-dialog", response_class=HTMLResponse)
    def import_dialog(request: Request):
        from astrapi_core.ui.render import render

        return render(request, "dialog_import.html", dict(module=owner_type))

    @router.post(f"/ui/{owner_type}/import", response_class=HTMLResponse)
    async def import_ui(request: Request):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not getattr(upload, "filename", ""):
            return HTMLResponse(
                '<p style="color:var(--r);font-size:13px;">Bitte eine Datei auswählen.</p>'
            )
        raw = await upload.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return HTMLResponse(
                f'<p style="color:var(--r);font-size:13px;">Ungültiges JSON: {e}</p>'
            )
        if not isinstance(data, list):
            return HTMLResponse(
                '<p style="color:var(--r);font-size:13px;">Erwartet ein JSON-Array.</p>'
            )
        summary = import_items(owner_type, store, data)
        return HTMLResponse(
            f'<p style="font-size:13px;">{summary["created"]} angelegt, '
            f"{summary['updated']} aktualisiert, "
            f"{summary['files_imported']} Datei(en) importiert.</p>"
            f'<button type="button" class="btn btn-sm btn-primary" '
            f'hx-get="/ui/{owner_type}/content" hx-target="#main-content" hx-swap="innerHTML" '
            f'onclick="closeModal(this)">Fertig</button>'
        )

    return router

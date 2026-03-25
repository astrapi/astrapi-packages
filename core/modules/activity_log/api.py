# core/modules/activity_log/api.py
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.ui.fastapi_templates import get_templates
from .engine import (
    list_activity, get_activity_log, clear_activity_log, get_log_lines,
    enrich, registered_modules, fmt_duration, fmt_bytes,
)

router = APIRouter(tags=["activity_log"])


@router.get("/clear-confirm", response_class=HTMLResponse)
def activity_log_clear_confirm(request: Request):
    return get_templates().TemplateResponse("partials/confirm_modal.html", {
        "request":      request,
        "description":  "Alle Activity-Log-Einträge",
        "verb":         "löschen",
        "confirm_url":  "/api/activity_log/clear",
        "method":       "delete",
        "container_id": "tab-activity_log",
        "loading_id":   "activity_log-loading",
    })


@router.delete("/clear", response_class=HTMLResponse)
def activity_log_clear(request: Request):
    clear_activity_log()
    return get_templates().TemplateResponse("activity_log/partials/list.html", {
        "request": request,
        "entries": [],
        "modules": registered_modules(),
    })


@router.get("/tab", response_class=HTMLResponse)
def activity_log_tab(request: Request):
    entries = enrich(list_activity(limit=200))
    return get_templates().TemplateResponse("activity_log/partials/list.html", {
        "request": request,
        "entries": entries,
        "modules": registered_modules(),
    })


@router.get("/rows", response_class=HTMLResponse)
def activity_log_rows(
    request: Request,
    log_type:   str = "",
    module:     str = "",
    status:     str = "",
    date_range: str = "30d",
    search:     str = "",
):
    date_from = None
    if date_range == "24h":
        date_from = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_range == "7d":
        date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    elif date_range == "30d":
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    entries = enrich(list_activity(
        limit=200,
        log_type=log_type or None,
        module=module   or None,
        status=status   or None,
        date_from=date_from,
        search=search   or None,
    ))
    return get_templates().TemplateResponse("activity_log/partials/rows.html", {
        "request": request,
        "entries": entries,
    })


@router.get("/{log_id}/detail", response_class=HTMLResponse)
def activity_log_detail(request: Request, log_id: int):
    entry = get_activity_log(log_id)
    if not entry:
        return HTMLResponse("<div>Log-Eintrag nicht gefunden</div>")
    entry["duration_fmt"] = fmt_duration(entry.get("duration_s"))
    entry["bytes_fmt"]    = fmt_bytes(entry.get("bytes_processed"))
    if entry.get("metadata"):
        try:
            entry["metadata_dict"] = json.loads(entry["metadata"])
        except Exception:
            entry["metadata_dict"] = {}
    return get_templates().TemplateResponse("activity_log/partials/detail_modal.html", {
        "request": request,
        "entry": entry,
    })


@router.get("/{log_id}/log", response_class=HTMLResponse)
def activity_log_viewer(request: Request, log_id: int):
    entry = get_activity_log(log_id)
    if not entry:
        return HTMLResponse("<div>Log nicht gefunden</div>")
    lines = get_log_lines(log_id)
    full_log = "\n".join(f"[{r['level']}] {r['line']}" for r in lines) if lines else entry.get("full_log", "")
    return get_templates().TemplateResponse("activity_log/partials/log_viewer_modal.html", {
        "request": request,
        "entry": entry,
        "full_log": full_log,
    })

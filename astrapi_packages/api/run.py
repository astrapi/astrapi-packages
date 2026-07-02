"""astrapi_packages.api.run – Zentraler Run/Log/SSE-Router für alle Run-Module.

Analogie zu astrapi_backup.api.routers.run, aber für astrapi-packages.

Einbinden in fastapi_app.py:
    from astrapi_packages.api.run import make_run_router
    for mod in ["builder", "archlinux"]:
        app.include_router(make_run_router(mod), prefix=f"/api/{mod}")
"""

import asyncio
import json
import threading

from astrapi_core.system.activity_log import (
    get_latest_activity_log_id,
    get_log_lines,
    history_finish,
    history_start,
    list_runs_for_item,
)
from astrapi_core.system.logger import (
    clear_active_log_id,
    clear_tee_context,
    set_active_log_id,
    set_tee_context,
)
from astrapi_core.ui.render import render
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

# ── Globales Running-Dict ─────────────────────────────────────────────────────

_running: dict = {}
_running_lock = threading.Lock()


def _is_running(module: str, item_id: str) -> bool:
    return f"{module}:{item_id}" in _running


def _mark_running(module: str, item_id: str) -> None:
    with _running_lock:
        _running[f"{module}:{item_id}"] = "run"


def _mark_done(module: str, item_id: str) -> None:
    with _running_lock:
        _running.pop(f"{module}:{item_id}", None)


def get_running() -> dict:
    """Gibt alle laufenden Jobs zurück (modul:item_id → mode)."""
    return dict(_running)


# ── Config-Loader-Registry ────────────────────────────────────────────────────

_config_loaders: dict = {}


def register_config_loader(module: str, fn) -> None:
    """Registriert eine Funktion die die Konfiguration eines Moduls lädt.

    fn() → dict  (item_id → item_dict)
    Module die keinen eigenen Loader registrieren nutzen store.list() als
    Fallback.
    """
    _config_loaders[module] = fn


def load_config(module: str) -> dict:
    """Lädt die Konfiguration eines Moduls (item_id → item_dict)."""
    if module in _config_loaders:
        return _config_loaders[module]()
    try:
        import importlib

        mod = importlib.import_module(f"astrapi_packages.modules.{module}.storage")
        return mod.store.list()
    except Exception:
        return {}


# ── Dispatch ──────────────────────────────────────────────────────────────────


def _dispatch_single(module: str, item_id: str) -> None:
    import importlib

    try:
        mod = importlib.import_module(f"astrapi_packages.modules.{module}.jobs")
    except ModuleNotFoundError:
        from astrapi_core.system.logger import log

        log("ERROR", f"Unbekanntes Modul: {module}")
        return
    mod.run_single(item_id)


def _item_description(module: str, item_id: str) -> str:
    try:
        cfg = load_config(module)
        raw = cfg.get(item_id) or {}
        return raw.get("name") or raw.get("label") or raw.get("description") or item_id
    except Exception:
        return item_id


# ── Router-Factory ────────────────────────────────────────────────────────────


def make_run_router(module: str) -> APIRouter:
    """Erzeugt einen APIRouter mit Run/Log/SSE-Routen für ein Modul.

    Einbinden mit prefix="/api/{module}":
      POST   /{item_id}/run
      GET    /{item_id}/logs/stream
      GET    /{item_id}/logs
      GET    /{item_id}/logs/{log_id}
    """
    router = APIRouter(tags=[module])

    # ── Run-Route ─────────────────────────────────────────────────────

    @router.post("/{item_id}/run", response_class=HTMLResponse)
    def run_item(item_id: str, request: Request):
        if _is_running(module, item_id):
            raise HTTPException(status_code=409, detail="Läuft bereits")

        _mark_running(module, item_id)

        def _execute():
            import time

            desc = _item_description(module, item_id)
            hist_id = history_start(module, item_id, desc, "run")
            t0 = time.time()
            set_tee_context(module, item_id)
            set_active_log_id(hist_id)
            status = "ok"
            try:
                _dispatch_single(module, item_id)
            except Exception:
                status = "error"
            finally:
                duration = int(time.time() - t0)
                if status == "ok":
                    levels = {r["level"] for r in get_log_lines(hist_id)}
                    if "ERROR" in levels:
                        status = "error"
                    elif "WARNING" in levels:
                        status = "warning"
                history_finish(hist_id, status, duration)
                clear_active_log_id()
                clear_tee_context()
                _mark_done(module, item_id)

        threading.Thread(target=_execute, daemon=True).start()

        item_data = load_config(module).get(item_id) or {}
        row_html = render(
            request,
            "partials/lists/row_single.html",
            {
                "item_name": item_id,
                "item_data": item_data,
                "module": module,
                "container_id": f"mod-{module}",
                "loading_id": f"{module}-loading",
                "running": get_running(),
            },
        ).body.decode()

        trigger = json.dumps({"openLogModal": {"module": module, "itemId": item_id}})
        return HTMLResponse(row_html, headers={"HX-Trigger": trigger})

    # ── SSE: Live-Log-Stream ──────────────────────────────────────────

    @router.get("/{item_id}/logs/stream")
    async def stream_log(item_id: str):
        async def event_generator():
            act_log_id = None
            waited = 0.0
            while act_log_id is None and waited < 15:
                act_log_id = get_latest_activity_log_id(module, item_id)
                if act_log_id is None:
                    await asyncio.sleep(0.3)
                    waited += 0.3

            if act_log_id is None:
                yield "event: done\ndata: \n\n"
                return

            last_id = 0
            idle_after_done = 0.0

            while True:
                rows = get_log_lines(act_log_id, after_id=last_id)
                for row in rows:
                    last_id = row["id"]
                    level = row["level"].lower()
                    safe = (
                        row["line"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    )
                    yield f'data: <div class="log-line log-{level}">{safe}</div>\n\n'

                if not _is_running(module, item_id):
                    idle_after_done += 0.5
                    if idle_after_done >= 3:
                        yield "event: done\ndata: \n\n"
                        return
                else:
                    idle_after_done = 0.0

                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Log-Endpunkte ─────────────────────────────────────────────────

    @router.get("/{item_id}/logs", response_class=HTMLResponse)
    def get_logs(item_id: str, request: Request, live: int = 0):
        runs = list_runs_for_item(module, item_id)
        act_log_id = runs[0]["id"] if runs else None
        lines = [r["line"] for r in get_log_lines(act_log_id)] if act_log_id else []
        dates = [{"id": str(r["id"]), "label": r["started_at"] or str(r["id"])} for r in runs]
        selected = str(act_log_id) if act_log_id else None
        return render(
            request,
            "dialog_log.html",
            {
                "module": module,
                "item_id": item_id,
                "description": _item_description(module, item_id),
                "dates": dates,
                "selected": selected,
                "lines": lines,
                "live": bool(live),
            },
        )

    @router.get("/{item_id}/logs/{log_id}", response_class=HTMLResponse)
    def get_log_by_id(item_id: str, log_id: str, request: Request):
        lines = [r["line"] for r in get_log_lines(int(log_id))] if log_id.isdigit() else []
        return render(request, "partials/dialogs/log_content.html", {"lines": lines, "date": log_id})

    return router

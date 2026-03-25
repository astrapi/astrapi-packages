# core/health.py
"""Generischer /health-Endpunkt für FastAPI-Apps."""
import time

from fastapi import FastAPI
from fastapi.responses import Response


def register_health(
    app: FastAPI,
    check_fn=None,
    start_time: float = None,
    path: str = "/health",
    tags: list[str] | None = None,
) -> None:
    """Registriert einen Health-Check-Endpunkt auf der FastAPI-App.

    Args:
        app:        FastAPI-Instanz
        check_fn:   Optional. Callable () -> (ok: bool, details: dict).
                    Wird für erweiterte Health-Checks genutzt (z.B. DB-Verbindung).
        start_time: Startzeitpunkt (time.time()), für uptime_s im Response.
                    Standardmäßig der Zeitpunkt des Aufrufs von register_health.
        path:       URL-Pfad des Endpunkts (Standard: "/health").
        tags:       OpenAPI-Tags (Standard: kein Schema-Eintrag).
    """
    _start = start_time if start_time is not None else time.time()
    _include = tags is not None

    @app.get(path, include_in_schema=_include, tags=tags or [])
    def health():
        ok = True
        details: dict = {}
        if check_fn is not None:
            try:
                ok, details = check_fn()
            except Exception:
                ok = False
        uptime = int(time.time() - _start)
        extra = "".join(f',"{k}":{str(v).lower()}' for k, v in details.items())
        body = f'{{"status":"{"ok" if ok else "degraded"}","uptime_s":{uptime}{extra}}}'
        return Response(content=body, media_type="application/json",
                        status_code=200 if ok else 503)

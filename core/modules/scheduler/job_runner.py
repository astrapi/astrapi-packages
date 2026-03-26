# core/modules/scheduler/job_runner.py
"""Wiederverwendbare Logging- und Benachrichtigungs-Helfer für geplante Jobs.

Module nutzen diese Funktionen in ihren ``run()``-Implementierungen:

    from astrapi.core.modules.scheduler.job_runner import run_all, run_logged

    def run():
        run_all("borg", _get_config(), run_single)

    # Einzelnen Eintrag mit Activity-Log-Kontext ausführen:
    run_logged("proxmox_lxc", str(item_id), name, lambda: _backup_lxc(...))
"""

import logging
import time

log = logging.getLogger(__name__)


def run_logged(module: str, item_id: str, description: str, fn) -> str:
    """Führt ``fn`` mit vollständigem Activity-Log- und Tee-Kontext aus.

    Args:
        module:      Modulname, z.B. ``"borg"``.
        item_id:     ID des Eintrags in der Modul-Config.
        description: Anzeigename für den Log-Eintrag.
        fn:          Callable ohne Argumente.

    Returns:
        Status-String: ``"ok"``, ``"warning"`` oder ``"error"``.
    """
    from astrapi.core.system.activity_log import (
        history_start, history_finish, get_log_lines,
    )
    from astrapi.core.system.logger import (
        set_tee_context, clear_tee_context,
        set_active_log_id, clear_active_log_id,
    )

    hist_id = history_start(module, item_id, description, "run")
    t0 = time.time()
    set_tee_context(module, item_id)
    set_active_log_id(hist_id)
    status = "ok"
    try:
        fn()
    except Exception as e:
        status = "error"
        log.error("run_logged: %s/%s fehlgeschlagen: %s", module, item_id, e)
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

    return status


def run_all(
    module: str,
    config: dict,
    run_single_fn,
    desc_fn=None,
) -> None:
    """Führt ``run_single_fn`` für alle aktivierten Einträge in ``config`` aus.

    Args:
        module:       Modulname, z.B. ``"borg"``.
        config:       Dict ``{item_id: entry_dict}`` wie von ``load_config()`` geliefert.
        run_single_fn: Callable ``(item_id, entry)`` – die ``run_single``-Funktion des Moduls.
        desc_fn:      Optionales Callable ``(item_id, entry) -> str`` für den Anzeigenamen.
                      Standard: ``entry.get("description", item_id)``.
    """
    for item_id, entry in config.items():
        if not entry.get("enabled", True):
            continue
        desc = (
            desc_fn(item_id, entry)
            if desc_fn is not None
            else entry.get("description", str(item_id))
        )
        run_logged(
            module,
            str(item_id),
            desc,
            lambda iid=item_id, e=entry: run_single_fn(iid, e),
        )


def _notify(module: str, description: str, status: str, duration: int) -> None:
    """Sendet eine Benachrichtigung über das Ergebnis eines Job-Laufs.

    Args:
        module:      Modulname (wird als Notify-Quelle verwendet).
        description: Anzeigename des Eintrags.
        status:      ``"ok"``, ``"warning"`` oder ``"error"``.
        duration:    Laufzeit in Sekunden.
    """
    try:
        from astrapi.core.modules.notify import engine as _ne
        event = {
            "ok":      _ne.SUCCESS,
            "warning": _ne.WARNING,
            "error":   _ne.ERROR,
        }.get(status, _ne.INFO)
        status_label = {"ok": "Erfolgreich", "warning": "Warnung", "error": "Fehler"}.get(
            status, status
        )
        _ne.send(
            title   = f"{description}: {status_label}",
            message = f"Dauer: {duration}s",
            event   = event,
            source  = module,
            tags    = ["job"],
        )
    except Exception as e:
        log.debug("_notify: Benachrichtigung fehlgeschlagen: %s", e)

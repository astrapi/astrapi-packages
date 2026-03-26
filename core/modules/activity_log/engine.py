# core/modules/activity_log/engine.py

from astrapi.core.system.activity_log import (
    log_activity, update_activity_log,
    list_activity, get_activity_log, clear_activity_log,
    get_log_lines, get_latest_activity_log_id, list_runs_for_item,
    history_start, history_finish, list_history,
    append_log_line,
)

KEY = "activity_log"


def fmt_duration(s: int | None) -> str:
    if s is None:
        return "—"
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m {sec}s"
    h, min_ = divmod(m, 60)
    return f"{h}h {min_}m"


from astrapi.core.system.format import fmt_bytes


def enrich(entries: list) -> list:
    for e in entries:
        e["duration_fmt"] = fmt_duration(e.get("duration_s"))
        e["bytes_fmt"]    = fmt_bytes(e.get("bytes_processed"))
    return entries


def registered_modules() -> list[str]:
    try:
        from astrapi.core.ui.module_registry import _mod_registry
        return [key for key in _mod_registry if not key.startswith("_")]
    except Exception:
        return []

# core/system/logger.py
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

LOG_ROOT = None   # Wird von der App via configure_log_root() gesetzt
_lock = threading.Lock()

# ── Haupt-Log-Kontext (pro Thread) ───────────────────────────────
_context     = threading.local()

# ── Tee-Kontext: Spiegelt log()-Zeilen in eine zweite Datei ──────
_tee_context = threading.local()

# ── Aktive activity_log ID für DB-Logging ────────────────────────
_db_context  = threading.local()


def configure_log_root(path: Path | str) -> None:
    """Setzt das Wurzelverzeichnis für Datei-Logs. Von der App beim Start aufzurufen."""
    global LOG_ROOT
    LOG_ROOT = Path(path)


# ── Pfad-Hilfsfunktion ────────────────────────────────────────────

def log_path(module: str, item_id: str, date: datetime = None) -> Path:
    d = date or datetime.now()
    return LOG_ROOT / module / str(item_id) / f"{d.strftime('%Y-%m-%d')}.log"


def _write(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _cleanup_old_logs(module: str, item_id: str) -> None:
    if LOG_ROOT is None:
        return
    cutoff = datetime.now() - timedelta(days=14)
    folder = LOG_ROOT / module / str(item_id)
    if not folder.exists():
        return
    for f in folder.glob("*.log"):
        try:
            if datetime.strptime(f.stem, "%Y-%m-%d") < cutoff:
                f.unlink()
        except ValueError:
            pass


# ── Kontext-Verwaltung ────────────────────────────────────────────

def set_log_context(module: str, item_id: str) -> None:
    _context.module  = module
    _context.item_id = str(item_id)
    _cleanup_old_logs(module, item_id)


def clear_log_context() -> None:
    _context.module  = None
    _context.item_id = None


def get_log_context():
    return getattr(_context, "module", None), getattr(_context, "item_id", None)


@contextmanager
def log_context(module: str, item_id: str):
    """Contextmanager: setzt Log-Kontext und räumt ihn danach auf."""
    set_log_context(module, item_id)
    try:
        yield
    finally:
        clear_log_context()


def set_tee_context(module: str, item_id: str) -> None:
    """Zusätzlicher Kontext – jede log()-Zeile wird auch dorthin gespiegelt."""
    _tee_context.module  = module
    _tee_context.item_id = str(item_id)
    _cleanup_old_logs(module, item_id)


def clear_tee_context() -> None:
    _tee_context.module  = None
    _tee_context.item_id = None


def set_active_log_id(log_id: int) -> None:
    """Aktiviert DB-Logging: alle log()-Zeilen gehen in activity_log_lines(log_id)."""
    _db_context.log_id = log_id


def clear_active_log_id() -> None:
    _db_context.log_id = None


def get_active_log_id() -> int | None:
    return getattr(_db_context, "log_id", None)


# ── Logging ───────────────────────────────────────────────────────

def log(*args) -> None:
    if len(args) == 1:
        level, message = "INFO", args[0]
    elif len(args) == 2:
        level, message = args[0].upper(), args[1]
    else:
        raise ValueError("log() erwartet 1 oder 2 Argumente")

    now  = datetime.now()
    line = f"{now.strftime('%H:%M:%S')} {level}: {message}"
    print(line)

    # ── DB-Logging (primär) ───────────────────────────────────────
    db_log_id = get_active_log_id()
    if db_log_id is not None:
        try:
            from core.system.activity_log import append_log_line
            append_log_line(db_log_id, line, level)
        except Exception:
            pass
        return  # DB-only: keine Datei-Schreibung

    # ── Datei-Logging (Fallback für Scheduler/direkte Aufrufe) ───
    if LOG_ROOT is None:
        return
    module, item_id = get_log_context()
    if module and item_id:
        _write(log_path(module, item_id, now), line)

    tee_mod = getattr(_tee_context, "module", None)
    tee_id  = getattr(_tee_context, "item_id", None)
    if tee_mod and tee_id and (tee_mod, tee_id) != (module, item_id):
        _write(log_path(tee_mod, tee_id, now), line)


# ── Lesen ─────────────────────────────────────────────────────────

def get_log_dates(module: str, item_id: str) -> list:
    if LOG_ROOT is None:
        return []
    folder = LOG_ROOT / module / str(item_id)
    if not folder.exists():
        return []
    return sorted([f.stem for f in folder.glob("*.log")], reverse=True)


def read_log(module: str, item_id: str, date: str) -> list:
    if LOG_ROOT is None:
        return []
    path = LOG_ROOT / module / str(item_id) / f"{date}.log"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [l.rstrip() for l in f.readlines()]


def get_ntfy_logs(level: str) -> str:
    module, item_id = get_log_context()
    if not module or not item_id:
        return ""
    lines = read_log(module, item_id, datetime.now().strftime("%Y-%m-%d"))
    return "\n".join(l for l in lines if f"{level}:" in l)

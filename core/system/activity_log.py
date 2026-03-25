# core/system/activity_log.py
#
# Generisches Activity-Log und Log-Lines-Backend.
# Speichert Job-Läufe und ihre Log-Zeilen in SQLite.
#
import json
from datetime import datetime

from core.system.db import _conn, get_setting, set_setting


# ── Activity Log ──────────────────────────────────────────────────

_ACTIVITY_LOG_DDL = """
    CREATE TABLE IF NOT EXISTS activity_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,

        created_at      TEXT NOT NULL,
        started_at      TEXT,
        finished_at     TEXT,

        log_type        TEXT NOT NULL,
        module          TEXT NOT NULL,
        item_id         TEXT,
        description     TEXT NOT NULL,

        status          TEXT NOT NULL,
        severity        TEXT,

        mode            TEXT,
        duration_s      INTEGER,

        error_message   TEXT,
        error_code      TEXT,
        error_traceback TEXT,

        bytes_processed INTEGER,
        items_count     INTEGER,
        changed_count   INTEGER,

        full_log        TEXT,
        metadata        TEXT,

        parent_log_id   INTEGER,

        scheduler_job_id TEXT,
        next_run        TEXT,

        archived_at     TEXT
    )
"""

_ACTIVITY_LOG_INDICES = """
    CREATE INDEX IF NOT EXISTS idx_activity_log_type     ON activity_log(log_type);
    CREATE INDEX IF NOT EXISTS idx_activity_log_module   ON activity_log(module);
    CREATE INDEX IF NOT EXISTS idx_activity_log_status   ON activity_log(status);
    CREATE INDEX IF NOT EXISTS idx_activity_log_created  ON activity_log(created_at);
    CREATE INDEX IF NOT EXISTS idx_activity_log_item_id  ON activity_log(item_id);
"""

_LOG_LINES_DDL = """
    CREATE TABLE IF NOT EXISTS activity_log_lines (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id  INTEGER NOT NULL,
        line    TEXT    NOT NULL,
        level   TEXT    NOT NULL DEFAULT 'INFO',
        ts      TEXT    NOT NULL
    )
"""


def _init_activity_log() -> None:
    _conn().execute(_ACTIVITY_LOG_DDL)
    for stmt in _ACTIVITY_LOG_INDICES.strip().split(';'):
        if stmt.strip():
            _conn().execute(stmt)
    _conn().commit()
    if get_setting('activity_log_migrated', '') != '1':
        _migrate_history_to_activity_log()
        set_setting('activity_log_migrated', '1')


def _init_log_lines() -> None:
    _conn().execute(_LOG_LINES_DDL)
    _conn().execute(
        "CREATE INDEX IF NOT EXISTS idx_log_lines_log_id ON activity_log_lines(log_id, id)"
    )
    _conn().commit()


def _migrate_history_to_activity_log() -> None:
    """Einmalige Migration: kopiert job_history → activity_log."""
    try:
        _HISTORY_DDL = """
            CREATE TABLE IF NOT EXISTS job_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT    NOT NULL,
                finished_at TEXT,
                module      TEXT    NOT NULL DEFAULT '',
                item_id     TEXT    NOT NULL DEFAULT '',
                description TEXT    NOT NULL DEFAULT '',
                status      TEXT    NOT NULL DEFAULT 'running',
                duration_s  INTEGER,
                mode        TEXT    NOT NULL DEFAULT 'run'
            )
        """
        _conn().execute(_HISTORY_DDL)
        rows = _conn().execute("SELECT * FROM job_history ORDER BY id").fetchall()
        if not rows:
            return
        for row in rows:
            r = dict(row)
            _conn().execute("""
                INSERT OR IGNORE INTO activity_log (
                    created_at, started_at, finished_at,
                    log_type, module, item_id, description,
                    status, duration_s, mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.get('started_at'),
                r.get('started_at'),
                r.get('finished_at'),
                'job',
                r.get('module', ''),
                r.get('item_id', ''),
                r.get('description', ''),
                r.get('status', 'ok'),
                r.get('duration_s'),
                r.get('mode', 'run'),
            ))
        _conn().commit()
        print(f"[activity_log] Migration: {len(rows)} job_history-Einträge → activity_log")
    except Exception as e:
        print(f"[activity_log] Migration job_history → activity_log fehlgeschlagen: {e}")


def log_activity(
    log_type: str,
    module: str,
    description: str,
    status: str = 'info',
    severity: str = None,
    item_id: str = None,
    started_at: str = None,
    finished_at: str = None,
    duration_s: int = None,
    error_message: str = None,
    error_code: str = None,
    error_traceback: str = None,
    full_log: str = None,
    bytes_processed: int = None,
    items_count: int = None,
    changed_count: int = None,
    metadata: dict = None,
    parent_log_id: int = None,
    mode: str = None,
    scheduler_job_id: str = None,
    next_run: str = None,
) -> int:
    """Schreibt einen neuen Activity-Log-Eintrag. Gibt die Log-ID zurück."""
    _init_activity_log()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = _conn().execute("""
        INSERT INTO activity_log (
            created_at, started_at, finished_at,
            log_type, module, item_id, description,
            status, severity, mode, duration_s,
            error_message, error_code, error_traceback,
            full_log, bytes_processed, items_count, changed_count,
            metadata, parent_log_id,
            scheduler_job_id, next_run
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now,
        started_at or now,
        finished_at,
        log_type, module, item_id, description,
        status, severity, mode, duration_s,
        error_message, error_code, error_traceback,
        full_log, bytes_processed, items_count, changed_count,
        json.dumps(metadata) if metadata else None,
        parent_log_id,
        scheduler_job_id, next_run,
    ))
    _conn().commit()
    return cur.lastrowid


def update_activity_log(
    log_id: int,
    status: str = None,
    finished_at: str = None,
    duration_s: int = None,
    error_message: str = None,
    error_code: str = None,
    error_traceback: str = None,
    full_log: str = None,
    bytes_processed: int = None,
    items_count: int = None,
    changed_count: int = None,
    metadata: dict = None,
) -> None:
    """Aktualisiert einen bestehenden Activity-Log-Eintrag."""
    _init_activity_log()
    updates, params = [], []

    if status is not None:
        updates.append("status = ?"); params.append(status)
    if finished_at is not None:
        updates.append("finished_at = ?"); params.append(finished_at)
    if duration_s is not None:
        updates.append("duration_s = ?"); params.append(duration_s)
    if error_message is not None:
        updates.append("error_message = ?"); params.append(error_message)
    if error_code is not None:
        updates.append("error_code = ?"); params.append(error_code)
    if error_traceback is not None:
        updates.append("error_traceback = ?"); params.append(error_traceback)
    if full_log is not None:
        updates.append("full_log = ?"); params.append(full_log)
    if bytes_processed is not None:
        updates.append("bytes_processed = ?"); params.append(bytes_processed)
    if items_count is not None:
        updates.append("items_count = ?"); params.append(items_count)
    if changed_count is not None:
        updates.append("changed_count = ?"); params.append(changed_count)
    if metadata is not None:
        updates.append("metadata = ?"); params.append(json.dumps(metadata))

    if not updates:
        return
    params.append(log_id)
    _conn().execute(f"UPDATE activity_log SET {', '.join(updates)} WHERE id = ?", params)
    _conn().commit()


def list_activity(
    limit: int = 200,
    log_type: str = None,
    module: str = None,
    status: str = None,
    date_from: str = None,
    search: str = None,
    item_id: str = None,
) -> list:
    """Liest Activity-Log mit optionalen Filtern. Neueste zuerst."""
    _init_activity_log()
    query = "SELECT * FROM activity_log WHERE archived_at IS NULL"
    params = []
    if log_type:
        query += " AND log_type = ?"; params.append(log_type)
    if module:
        query += " AND module = ?"; params.append(module)
    if status:
        query += " AND status = ?"; params.append(status)
    if date_from:
        query += " AND DATE(created_at) >= ?"; params.append(date_from)
    if search:
        query += " AND description LIKE ?"; params.append(f"%{search}%")
    if item_id:
        query += " AND item_id = ?"; params.append(item_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in _conn().execute(query, params).fetchall()]


def get_activity_log(log_id: int) -> dict | None:
    """Liest einen einzelnen Activity-Log-Eintrag."""
    _init_activity_log()
    row = _conn().execute(
        "SELECT * FROM activity_log WHERE id = ?", (log_id,)
    ).fetchone()
    return dict(row) if row else None


def clear_activity_log() -> int:
    """Löscht alle activity_log und activity_log_lines Einträge. Gibt Anzahl zurück."""
    _init_activity_log()
    _init_log_lines()
    count = _conn().execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    _conn().execute("DELETE FROM activity_log_lines")
    _conn().execute("DELETE FROM activity_log")
    _conn().execute("DELETE FROM sqlite_sequence WHERE name IN ('activity_log','activity_log_lines')")
    _conn().commit()
    set_setting('activity_log_migrated', '1')
    return count


def get_latest_activity_log_id(module: str, item_id: str) -> int | None:
    """Gibt die ID des aktuellsten activity_log-Eintrags für (module, item_id) zurück."""
    _init_activity_log()
    row = _conn().execute(
        "SELECT id FROM activity_log WHERE module = ? AND item_id = ? ORDER BY created_at DESC LIMIT 1",
        (module, str(item_id)),
    ).fetchone()
    return row["id"] if row else None


def list_runs_for_item(module: str, item_id: str, limit: int = 30) -> list:
    """Gibt alle Runs für (module, item_id) zurück, neueste zuerst."""
    _init_activity_log()
    rows = _conn().execute(
        "SELECT id, started_at, status FROM activity_log "
        "WHERE module = ? AND item_id = ? ORDER BY created_at DESC LIMIT ?",
        (module, str(item_id), limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Job-History-Wrappers ──────────────────────────────────────────

def history_start(module: str, item_id: str, description: str, mode: str = "run") -> int:
    """Schreibt einen neuen Job-Eintrag in activity_log. Gibt die ID zurück."""
    return log_activity(
        log_type='job',
        module=module,
        item_id=item_id,
        description=description,
        status='running',
        mode=mode,
        started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def history_finish(history_id: int, status: str, duration_s: int) -> None:
    """Schließt einen Job-Eintrag in activity_log ab."""
    update_activity_log(
        log_id=history_id,
        status=status,
        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        duration_s=duration_s,
    )


def list_history(limit: int = 100, module: str = None) -> list:
    """Kompatibilitäts-Wrapper: liest Jobs aus activity_log."""
    return list_activity(limit=limit, module=module, log_type='job')


# ── Log Lines ─────────────────────────────────────────────────────

def append_log_line(log_id: int, line: str, level: str = 'INFO') -> None:
    """Schreibt eine Log-Zeile in die DB."""
    _init_log_lines()
    _conn().execute(
        "INSERT INTO activity_log_lines (log_id, line, level, ts) VALUES (?, ?, ?, ?)",
        (log_id, line, level.upper(), datetime.now().strftime("%H:%M:%S")),
    )
    _conn().commit()


def get_log_lines(log_id: int, after_id: int = 0) -> list:
    """Gibt neue Zeilen zurück (für SSE-Polling: after_id = letzte bekannte ID)."""
    _init_log_lines()
    rows = _conn().execute(
        "SELECT id, line, level FROM activity_log_lines WHERE log_id = ? AND id > ? ORDER BY id",
        (log_id, after_id),
    ).fetchall()
    return [dict(r) for r in rows]

# core/system/db.py
#
# Generische SQLite-Verbindungsverwaltung und Settings-Tabelle.
# Die App konfiguriert den DB-Pfad einmalig beim Start via configure().
#
import sqlite3
import threading
from pathlib import Path

_db_path: Path | None = None
_local   = threading.local()


def configure(db_path: Path | str) -> None:
    """Setzt den DB-Pfad. Muss vor dem ersten _conn()-Aufruf aufgerufen werden."""
    global _db_path
    _db_path = Path(db_path)


def _conn() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("core.system.db nicht konfiguriert – configure(db_path) aufrufen!")
    if not getattr(_local, "conn", None):
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(_db_path), check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        _local.conn = con
    return _local.conn


# ── Settings-Tabelle (key/value) ──────────────────────────────────

_SETTINGS_DDL = """
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT ''
    )
"""


def _init_settings() -> None:
    _conn().execute(_SETTINGS_DDL)
    _conn().commit()


def get_setting(key: str, default: str = "") -> str:
    _init_settings()
    row = _conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    _init_settings()
    _conn().execute(
        "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    _conn().commit()


# ── Generische Tabellen-Registry + CRUD ───────────────────────────

_TABLE_CONFIG: dict = {}  # key → {ddl, list_fields, col_in, col_out}


def register_table(
    key: str,
    ddl: str,
    list_fields: list | None = None,
    col_in:  dict | None = None,
    col_out: dict | None = None,
) -> None:
    """Registriert eine Tabelle für generisches CRUD.

    key:         Tabellenname (= Modul-Key)
    ddl:         CREATE TABLE IF NOT EXISTS …
    list_fields: DB-Spaltennamen die als '\\n'-getrennte Listen gespeichert werden
    col_in:      {db_col: python_key}  – Umbenennung beim Lesen aus der DB
    col_out:     {python_key: db_col}  – Umbenennung beim Schreiben in die DB
    """
    _TABLE_CONFIG[key] = {
        "ddl":         ddl,
        "list_fields": list_fields or [],
        "col_in":      col_in  or {},
        "col_out":     col_out or {},
    }


def _ensure_table(key: str) -> None:
    cfg = _TABLE_CONFIG.get(key)
    if cfg:
        _conn().execute(cfg["ddl"])
        _conn().commit()


def create_all_registered_tables() -> None:
    """Erstellt alle per register_table() registrierten Tabellen."""
    con = _conn()
    for cfg in _TABLE_CONFIG.values():
        con.execute(cfg["ddl"])
    con.commit()


def _to_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [line for line in val.split("\n") if line]
    return list(val)


def _row_to_dict(key: str, row) -> dict:
    d = dict(row)
    d["enabled"] = bool(d.get("enabled", 1))
    cfg = _TABLE_CONFIG.get(key, {})
    for field in cfg.get("list_fields", []):
        raw = d.get(field)
        d[field] = [line for line in raw.split("\n") if line] if raw else []
    for db_col, py_key in cfg.get("col_in", {}).items():
        if db_col in d:
            d[py_key] = d.pop(db_col)
    return d


def _dict_to_params(key: str, item: dict) -> dict:
    p = dict(item)
    p["enabled"] = 1 if item.get("enabled", True) else 0
    cfg = _TABLE_CONFIG.get(key, {})
    for py_key, db_col in cfg.get("col_out", {}).items():
        if py_key in p:
            p[db_col] = p.pop(py_key)
    for field in cfg.get("list_fields", []):
        p[field] = "\n".join(_to_list(p.get(field)))
    p.pop("id", None)
    return p


# ── Öffentliche generische CRUD-API ──────────────────────────────

def load_config(key: str) -> dict:
    """Gibt {str(id): item_dict} zurück."""
    _ensure_table(key)
    rows = _conn().execute(f"SELECT * FROM {key} ORDER BY id").fetchall()
    return {str(row["id"]): _row_to_dict(key, row) for row in rows}


def get_item(key: str, item_id) -> dict | None:
    _ensure_table(key)
    if item_id is None:
        return None
    try:
        iid = int(item_id)
    except (ValueError, TypeError):
        return None
    row = _conn().execute(f"SELECT * FROM {key} WHERE id=?", (iid,)).fetchone()
    return _row_to_dict(key, row) if row else None


def save_item(key: str, item_id, item: dict) -> None:
    _ensure_table(key)
    if item is None or not isinstance(item, dict):
        raise TypeError("item muss ein dict sein")
    p = _dict_to_params(key, item)
    con = _conn()
    try:
        iid = int(item_id)
    except (ValueError, TypeError):
        iid = None
    if iid:
        existing = con.execute(f"SELECT id FROM {key} WHERE id=?", (iid,)).fetchone()
        if existing:
            sets   = ", ".join(f"{k}=?" for k in p)
            values = list(p.values()) + [iid]
            con.execute(f"UPDATE {key} SET {sets} WHERE id=?", values)
            con.commit()
            return
    cols         = ", ".join(p.keys())
    placeholders = ", ".join("?" * len(p))
    con.execute(f"INSERT INTO {key} ({cols}) VALUES ({placeholders})", list(p.values()))
    con.commit()


def delete_item(key: str, item_id) -> bool:
    try:
        iid = int(item_id)
    except (ValueError, TypeError):
        return False
    cur = _conn().execute(f"DELETE FROM {key} WHERE id=?", (iid,))
    _conn().commit()
    return cur.rowcount > 0


def next_item_id(key: str) -> str:
    """Nächste freie ID (für Formulare die eine neue ID brauchen)."""
    row = _conn().execute(
        f"SELECT COALESCE(MAX(id), 0) + 1 AS next FROM {key}"
    ).fetchone()
    return str(row["next"])


def patch_item(key: str, item_id, **fields) -> None:
    """Aktualisiert einzelne Felder eines Eintrags ohne die übrigen zu überschreiben."""
    try:
        iid = int(item_id)
    except (ValueError, TypeError):
        return
    if not fields:
        return
    sets   = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [iid]
    _conn().execute(f"UPDATE {key} SET {sets} WHERE id=?", values)
    _conn().commit()


def get_entry(config: dict, item_id) -> dict | None:
    """Sucht einen Eintrag im Config-Dict – mit str- und int-Fallback.

    load_config() liefert {str(id): item}. Je nach Aufrufer kommt item_id
    als str oder int an. Diese Funktion probiert beide Varianten.
    """
    entry = config.get(item_id)
    if entry is None:
        str_id = str(item_id)
        entry = config.get(str_id)
        if entry is None and str_id.isdigit():
            entry = config.get(int(str_id))
    return entry


# ── Key-Value Store (kvstore) ─────────────────────────────────────
# Generischer String→JSON-Speicher für Module (ersetzt YAML-Dateien).
# Wird von SqliteStorage genutzt.

_KVSTORE_DDL = """
    CREATE TABLE IF NOT EXISTS kvstore (
        collection TEXT NOT NULL,
        key        TEXT NOT NULL,
        value      TEXT NOT NULL,
        PRIMARY KEY (collection, key)
    )"""


def _init_kvstore() -> None:
    _conn().execute(_KVSTORE_DDL)
    _conn().commit()


def kv_get(collection: str, key: str) -> str | None:
    _init_kvstore()
    row = _conn().execute(
        "SELECT value FROM kvstore WHERE collection=? AND key=?",
        (collection, key),
    ).fetchone()
    return row["value"] if row else None


def kv_set(collection: str, key: str, value: str) -> None:
    _init_kvstore()
    _conn().execute(
        "INSERT INTO kvstore (collection, key, value) VALUES (?,?,?) "
        "ON CONFLICT(collection, key) DO UPDATE SET value=excluded.value",
        (collection, key, value),
    )
    _conn().commit()


def kv_delete(collection: str, key: str) -> None:
    _init_kvstore()
    _conn().execute(
        "DELETE FROM kvstore WHERE collection=? AND key=?", (collection, key)
    )
    _conn().commit()


def kv_list(collection: str) -> dict[str, str]:
    """Gibt alle Einträge einer Collection als {key: raw_value_str} zurück."""
    _init_kvstore()
    rows = _conn().execute(
        "SELECT key, value FROM kvstore WHERE collection=? ORDER BY key",
        (collection,),
    ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def kv_clear(collection: str) -> None:
    _init_kvstore()
    _conn().execute("DELETE FROM kvstore WHERE collection=?", (collection,))
    _conn().commit()


def kv_set_many(collection: str, items: dict[str, str]) -> None:
    """Speichert mehrere Einträge auf einmal (bulk upsert)."""
    _init_kvstore()
    con = _conn()
    con.executemany(
        "INSERT INTO kvstore (collection, key, value) VALUES (?,?,?) "
        "ON CONFLICT(collection, key) DO UPDATE SET value=excluded.value",
        [(collection, k, v) for k, v in items.items()],
    )
    con.commit()

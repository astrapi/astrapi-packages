"""astrapi_packages.modules.debian.storage – DebianPackageStore.

Eigene SQLite-Tabelle `debian_packages` statt kvstore-JSON-Blobs.
Primary Key ist der Paketname (TEXT), identisch zum bisherigen kvstore-Key.
Beim ersten Start werden vorhandene kvstore-Daten automatisch migriert.
"""

from __future__ import annotations

import json
import threading

_TABLE = "debian_packages"
_KV_COLLECTION = "debian"

_DDL = """
CREATE TABLE IF NOT EXISTS debian_packages (
    name             TEXT PRIMARY KEY,
    source_url       TEXT NOT NULL DEFAULT '',
    distribution     TEXT NOT NULL DEFAULT 'bookworm',
    component        TEXT NOT NULL DEFAULT 'main',
    pkg_type         TEXT NOT NULL DEFAULT 'package',
    enabled          INTEGER NOT NULL DEFAULT 1,
    last_status      TEXT NOT NULL DEFAULT '',
    last_run         TEXT NOT NULL DEFAULT '',
    last_log         TEXT NOT NULL DEFAULT '',
    last_version     TEXT NOT NULL DEFAULT '',
    upstream_version TEXT NOT NULL DEFAULT ''
)"""

_COLS = (
    "name",
    "source_url",
    "distribution",
    "component",
    "pkg_type",
    "enabled",
    "last_status",
    "last_run",
    "last_log",
    "last_version",
    "upstream_version",
)
_BOOL_COLS = frozenset({"enabled"})

_log = __import__("logging").getLogger(__name__)


def _db():
    from astrapi_core.system.db import _conn

    return _conn()


class DebianPackageStore:
    """SQLite-backed Store mit eigener Tabelle `debian_packages`.

    Interface kompatibel mit SqliteStorage für CRUD-Router und Jobs.
    Primary Key ist der Paketname (TEXT).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._table_ready = False

    # ── Interna ──────────────────────────────────────────────────────────────

    def _ensure_table(self) -> bool:
        if self._table_ready:
            return True
        try:
            db = _db()
            db.execute(_DDL)
            db.commit()
            self._migrate_kvstore(db)
            self._table_ready = True
            return True
        except Exception:
            return False

    def _migrate_kvstore(self, db) -> None:
        """Migriert vorhandene Daten aus dem kvstore in die eigene Tabelle."""
        count = db.execute(f"SELECT COUNT(*) FROM {_TABLE}").fetchone()[0]
        if count > 0:
            return
        from astrapi_core.system.db import kv_clear, kv_list

        kv_data = kv_list(_KV_COLLECTION)
        if not kv_data:
            return
        for name, raw in kv_data.items():
            try:
                data = json.loads(raw)
                data["name"] = name
                row = self._to_db(data, include_pk=True)
                cols = list(row.keys())
                db.execute(
                    f"INSERT OR IGNORE INTO {_TABLE} ({','.join(cols)})"
                    f" VALUES ({','.join(['?'] * len(cols))})",
                    [row[c] for c in cols],
                )
            except Exception as e:
                _log.warning("Migration %s: %s", name, e)
        db.commit()
        kv_clear(_KV_COLLECTION)
        _log.info("Migriert: %s (%d Einträge) → %s", _KV_COLLECTION, len(kv_data), _TABLE)

    def _get_row(self, item_id: str):
        """Direkte DB-Abfrage ohne Lock – nur innerhalb von Lock-Blöcken verwenden."""
        return _db().execute(
            f"SELECT {','.join(_COLS)} FROM {_TABLE} WHERE name=?", (item_id,)
        ).fetchone()

    def _row_to_dict(self, row) -> dict:
        d = dict(zip(_COLS, row))
        for col in _BOOL_COLS:
            d[col] = bool(d.get(col, 0))
        return d

    def _to_db(self, data: dict, include_pk: bool = False) -> dict:
        """Wandelt Python-Dict in DB-Spaltenwerte um (nur bekannte Spalten)."""
        row: dict = {}
        for col in _COLS:
            if col == "name" and not include_pk:
                continue
            if col not in data:
                continue
            val = data[col]
            row[col] = (1 if val else 0) if col in _BOOL_COLS else val
        return row

    # ── Public interface ──────────────────────────────────────────────────────

    def list(self, filter_fn=None, offset: int = 0, limit=None) -> dict:
        if not self._ensure_table():
            return {}
        with self._lock:
            rows = _db().execute(
                f"SELECT {','.join(_COLS)} FROM {_TABLE} ORDER BY name"
            ).fetchall()
        result = {r[0]: self._row_to_dict(r) for r in rows}
        if filter_fn:
            result = {k: v for k, v in result.items() if filter_fn(k, v)}
        if offset:
            result = dict(list(result.items())[offset:])
        if limit is not None:
            result = dict(list(result.items())[:limit])
        return result

    def get(self, item_id: str) -> dict | None:
        if not self._ensure_table():
            return None
        with self._lock:
            row = self._get_row(item_id)
        return self._row_to_dict(row) if row else None

    def exists(self, item_id: str) -> bool:
        return self.get(item_id) is not None

    def create(self, item_id: str | None, data: dict) -> str:
        if item_id is None:
            raise ValueError(f"{_TABLE}: item_id darf nicht None sein")
        if not self._ensure_table():
            raise RuntimeError("DB nicht verfügbar")
        with self._lock:
            if self._get_row(item_id) is not None:
                raise KeyError(f"'{item_id}' existiert bereits")
            row = self._to_db(data, include_pk=True)
            row["name"] = item_id
            cols = list(row.keys())
            db = _db()
            db.execute(
                f"INSERT INTO {_TABLE} ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
                [row[c] for c in cols],
            )
            db.commit()
        return item_id

    def update(self, item_id: str, data: dict) -> None:
        if not self._ensure_table():
            raise RuntimeError("DB nicht verfügbar")
        row = self._to_db(data)
        if not row:
            return
        with self._lock:
            if self._get_row(item_id) is None:
                raise KeyError(f"'{item_id}' nicht gefunden")
            db = _db()
            sets = ", ".join(f"{k}=?" for k in row)
            db.execute(
                f"UPDATE {_TABLE} SET {sets} WHERE name=?",
                [*row.values(), item_id],
            )
            db.commit()

    def upsert(self, item_id: str, data: dict) -> dict:
        if not self._ensure_table():
            return {}
        row = self._to_db(data)
        if not row:
            return self.get(item_id) or {}
        with self._lock:
            db = _db()
            if self._get_row(item_id) is not None:
                sets = ", ".join(f"{k}=?" for k in row)
                db.execute(
                    f"UPDATE {_TABLE} SET {sets} WHERE name=?",
                    [*row.values(), item_id],
                )
            else:
                row["name"] = item_id
                cols = list(row.keys())
                db.execute(
                    f"INSERT INTO {_TABLE} ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
                    [row[c] for c in cols],
                )
            db.commit()
        return self.get(item_id) or {}

    def delete(self, item_id: str) -> bool:
        if not self._ensure_table():
            raise RuntimeError("DB nicht verfügbar")
        with self._lock:
            if self._get_row(item_id) is None:
                raise KeyError(f"'{item_id}' nicht gefunden")
            db = _db()
            db.execute(f"DELETE FROM {_TABLE} WHERE name=?", (item_id,))
            db.commit()
        return True

    def toggle(self, item_id: str, field: str = "enabled", default: bool = True) -> bool:
        if not self._ensure_table():
            raise RuntimeError("DB nicht verfügbar")
        with self._lock:
            row = _db().execute(
                f"SELECT {field} FROM {_TABLE} WHERE name=?", (item_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"'{item_id}' nicht gefunden")
            new_val = 0 if row[0] else 1
            _db().execute(
                f"UPDATE {_TABLE} SET {field}=? WHERE name=?", (new_val, item_id)
            )
            _db().commit()
        return bool(new_val)

    def __repr__(self) -> str:
        return f"DebianPackageStore(table={_TABLE!r})"

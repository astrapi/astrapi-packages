"""astrapi_packages.modules.builder.storage – BuilderImageStore.

Eigene SQLite-Tabelle `builder_images`. Primary Key ist die Image-ID (TEXT).
Ersetzt die vormals statische images.yaml (siehe
projects/packages/planung-datei-editor.md, Etappe 2/2.3) - bewusst ohne
automatische Migration, die Tabelle startet leer.
"""

from __future__ import annotations

import threading

_TABLE = "builder_images"

_DDL = """
CREATE TABLE IF NOT EXISTS builder_images (
    id          TEXT PRIMARY KEY,
    tag         TEXT NOT NULL DEFAULT 'latest',
    module      TEXT NOT NULL DEFAULT '',
    last_status TEXT NOT NULL DEFAULT 'neu',
    last_run    TEXT NOT NULL DEFAULT ''
)"""

_COLS = ("id", "tag", "module", "last_status", "last_run")


def _db():
    from astrapi_core.system.db import _conn

    return _conn()


class BuilderImageStore:
    """SQLite-backed Store mit eigener Tabelle `builder_images`.

    Interface kompatibel mit SqliteStorage für CRUD-Router und Jobs
    (analog DebianPackageStore/ArchlinuxPackageStore).
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
            self._table_ready = True
            return True
        except Exception:
            return False

    def _get_row(self, item_id: str):
        return (
            _db()
            .execute(f"SELECT {','.join(_COLS)} FROM {_TABLE} WHERE id=?", (item_id,))
            .fetchone()
        )

    def _row_to_dict(self, row) -> dict:
        return dict(zip(_COLS, row))

    def _to_db(self, data: dict, include_pk: bool = False) -> dict:
        row: dict = {}
        for col in _COLS:
            if col == "id" and not include_pk:
                continue
            if col not in data:
                continue
            row[col] = data[col]
        return row

    # ── Public interface ──────────────────────────────────────────────────────

    def list(self, filter_fn=None, offset: int = 0, limit=None) -> dict:
        if not self._ensure_table():
            return {}
        with self._lock:
            rows = _db().execute(f"SELECT {','.join(_COLS)} FROM {_TABLE} ORDER BY id").fetchall()
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
            row["id"] = item_id
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
            db.execute(f"UPDATE {_TABLE} SET {sets} WHERE id=?", [*row.values(), item_id])
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
                db.execute(f"UPDATE {_TABLE} SET {sets} WHERE id=?", [*row.values(), item_id])
            else:
                row["id"] = item_id
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
            db.execute(f"DELETE FROM {_TABLE} WHERE id=?", (item_id,))
            db.commit()
        return True

    def __repr__(self) -> str:
        return f"BuilderImageStore(table={_TABLE!r})"

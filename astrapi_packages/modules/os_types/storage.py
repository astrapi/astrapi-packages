"""astrapi_packages.modules.os_types.storage – OsTypeStore.

Eigene SQLite-Tabelle `os_types`. Primary Key ist der frei vergebene
OS-Typ-Schlüssel (z.B. "debian", "archlinux", "ubuntu" ...) -- siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul": ein neuer
OS-Typ lässt sich hier anlegen, ohne dass dafür App-Code existieren muss.
Startet bewusst leer (nackter Start, wie builder_images seit Etappe 2).
"""

from __future__ import annotations

import threading

_TABLE = "os_types"

_DDL = """
CREATE TABLE IF NOT EXISTS os_types (
    key                  TEXT PRIMARY KEY,
    label                TEXT NOT NULL DEFAULT '',
    repo_subdir          TEXT NOT NULL DEFAULT '',
    depends_url_template TEXT NOT NULL DEFAULT '',
    gnupg_home           TEXT NOT NULL DEFAULT '',
    gpg_key_id           TEXT NOT NULL DEFAULT ''
)"""

_COLS = ("key", "label", "repo_subdir", "depends_url_template", "gnupg_home", "gpg_key_id")


def _db():
    from astrapi_core.system.db import _conn

    return _conn()


class OsTypeStore:
    """SQLite-backed Store mit eigener Tabelle `os_types`.

    Interface kompatibel mit SqliteStorage für CRUD-Router (analog
    BuilderImageStore).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._table_ready = False

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
            .execute(f"SELECT {','.join(_COLS)} FROM {_TABLE} WHERE key=?", (item_id,))
            .fetchone()
        )

    def _row_to_dict(self, row) -> dict:
        return dict(zip(_COLS, row))

    def _to_db(self, data: dict, include_pk: bool = False) -> dict:
        row: dict = {}
        for col in _COLS:
            if col == "key" and not include_pk:
                continue
            if col not in data:
                continue
            row[col] = data[col]
        return row

    def list(self, filter_fn=None, offset: int = 0, limit=None) -> dict:
        if not self._ensure_table():
            return {}
        with self._lock:
            rows = _db().execute(f"SELECT {','.join(_COLS)} FROM {_TABLE} ORDER BY key").fetchall()
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
            row["key"] = item_id
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
            db.execute(f"UPDATE {_TABLE} SET {sets} WHERE key=?", [*row.values(), item_id])
            db.commit()

    def delete(self, item_id: str) -> bool:
        if not self._ensure_table():
            raise RuntimeError("DB nicht verfügbar")
        with self._lock:
            if self._get_row(item_id) is None:
                raise KeyError(f"'{item_id}' nicht gefunden")
            db = _db()
            db.execute(f"DELETE FROM {_TABLE} WHERE key=?", (item_id,))
            db.commit()
        return True

    def __repr__(self) -> str:
        return f"OsTypeStore(table={_TABLE!r})"

"""astrapi_packages.modules.packages.storage – PackageStore.

Eigene SQLite-Tabelle `packages`, ersetzt strukturell die vormaligen
`debian_packages`/`archlinux_packages` (siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul"). Ein
OS-Typ ist jetzt ein Datenwert (Spalte os_type, Fremdschlüssel auf
os_types.key) statt zweier getrennter Tabellen -- primary Key ist deshalb
"{os_type}:{name}" statt reinem Namen, da name allein über mehrere OS-Typen
hinweg kollidieren kann (z.B. "openssl" bei debian UND archlinux).

Bewusst kein automatischer Import aus debian_packages/archlinux_packages
(nackter Start, wie builder_images seit Etappe 2) -- die alten Tabellen
bleiben unangetastet liegen.
"""

from __future__ import annotations

import threading

_TABLE = "packages"

_DDL = """
CREATE TABLE IF NOT EXISTS packages (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL DEFAULT '',
    os_type           TEXT NOT NULL DEFAULT '',
    source_url        TEXT NOT NULL DEFAULT '',
    source_subdir     TEXT NOT NULL DEFAULT '',
    source_type       TEXT NOT NULL DEFAULT 'git',
    depends           TEXT NOT NULL DEFAULT '',
    image             TEXT NOT NULL DEFAULT '',
    pkg_type          TEXT NOT NULL DEFAULT 'package',
    enabled           INTEGER NOT NULL DEFAULT 1,
    last_status       TEXT NOT NULL DEFAULT 'neu',
    last_run          TEXT NOT NULL DEFAULT '',
    last_log          TEXT NOT NULL DEFAULT '',
    last_version      TEXT NOT NULL DEFAULT '',
    upstream_version  TEXT NOT NULL DEFAULT '',
    orphaned          INTEGER NOT NULL DEFAULT 0
)"""

_COLS = (
    "id",
    "name",
    "os_type",
    "source_url",
    "source_subdir",
    "source_type",
    "depends",
    "image",
    "pkg_type",
    "enabled",
    "last_status",
    "last_run",
    "last_log",
    "last_version",
    "upstream_version",
    "orphaned",
)
_BOOL_COLS = frozenset({"enabled", "orphaned"})


def make_id(os_type: str, name: str) -> str:
    return f"{os_type}:{name}"


def split_id(item_id: str) -> tuple[str, str]:
    """(os_type, name) aus einer id -- name kann selbst ':' enthalten,
    deshalb nur am ersten ':' splitten."""
    os_type, _, name = item_id.partition(":")
    return os_type, name


def _db():
    from astrapi_core.system.db import _conn

    return _conn()


class PackageStore:
    """SQLite-backed Store mit eigener Tabelle `packages`.

    Interface kompatibel mit SqliteStorage für CRUD-Router und Jobs (analog
    dem vormaligen DebianPackageStore/ArchlinuxPackageStore).
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
            .execute(f"SELECT {','.join(_COLS)} FROM {_TABLE} WHERE id=?", (item_id,))
            .fetchone()
        )

    def _row_to_dict(self, row) -> dict:
        d = dict(zip(_COLS, row))
        for col in _BOOL_COLS:
            d[col] = bool(d.get(col, 0))
        return d

    def _to_db(self, data: dict, include_pk: bool = False) -> dict:
        row: dict = {}
        for col in _COLS:
            if col == "id" and not include_pk:
                continue
            if col not in data:
                continue
            val = data[col]
            row[col] = (1 if val else 0) if col in _BOOL_COLS else val
        return row

    def list(self, filter_fn=None, offset: int = 0, limit=None) -> dict:
        if not self._ensure_table():
            return {}
        with self._lock:
            rows = _db().execute(f"SELECT {','.join(_COLS)} FROM {_TABLE} ORDER BY id").fetchall()
        result = {r[0]: self._row_to_dict(r) for r in rows}
        for item in result.values():
            item["pkg_type_label"] = {"package": "Paket", "dependency": "Abhängigkeit"}.get(
                item.get("pkg_type", ""), ""
            )
            item["orphaned_label"] = "verwaist" if item.get("orphaned") else ""
            item["source_type_label"] = (
                "DB"
                if item.get("source_type") == "db"
                else ("Repo" if item.get("source_url") else "")
            )
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

    def toggle(self, item_id: str, field: str = "enabled", default: bool = True) -> bool:
        if not self._ensure_table():
            raise RuntimeError("DB nicht verfügbar")
        with self._lock:
            row = _db().execute(f"SELECT {field} FROM {_TABLE} WHERE id=?", (item_id,)).fetchone()
            if row is None:
                raise KeyError(f"'{item_id}' nicht gefunden")
            new_val = 0 if row[0] else 1
            _db().execute(f"UPDATE {_TABLE} SET {field}=? WHERE id=?", (new_val, item_id))
            _db().commit()
        return bool(new_val)

    def __repr__(self) -> str:
        return f"PackageStore(table={_TABLE!r})"

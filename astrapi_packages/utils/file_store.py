"""astrapi_packages.utils.file_store – DB-gestuetzte, versionierte Dateiverwaltung.

Append-only: jede Aenderung (auch Loeschen) ist ein neuer INSERT in
`managed_files`, nie ein UPDATE/DELETE auf bestehende Zeilen. Die aktuelle
Version einer Datei ist die juengste Zeile fuer (owner_type, owner_id,
filename). Gemeinsam genutzt von builder/debian/archlinux (owner_type
unterscheidet), siehe projects/packages/planung-datei-editor.md, Abschnitt 2.1.
"""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path

_TABLE = "managed_files"

_DDL = """
CREATE TABLE IF NOT EXISTS managed_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL,
    owner_id   TEXT NOT NULL,
    filename   TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    message    TEXT NOT NULL DEFAULT '',
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)"""

_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_managed_files_owner "
    "ON managed_files(owner_type, owner_id, filename)"
)

_table_ready = False


def _db():
    from astrapi_core.system.db import _conn

    return _conn()


def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    db = _db()
    db.execute(_DDL)
    db.execute(_INDEX_DDL)
    db.commit()
    _table_ready = True


def _latest_row(owner_type: str, owner_id: str, filename: str):
    _ensure_table()
    return (
        _db()
        .execute(
            f"SELECT * FROM {_TABLE} WHERE owner_type=? AND owner_id=? AND filename=? "
            "ORDER BY id DESC LIMIT 1",
            (owner_type, owner_id, filename),
        )
        .fetchone()
    )


def list_files(owner_type: str, owner_id: str) -> list[dict]:
    """Aktuelle Version je Datei fuer diesen Owner, ohne geloeschte Dateien."""
    _ensure_table()
    rows = (
        _db()
        .execute(
            f"""
        SELECT m.* FROM {_TABLE} m
        INNER JOIN (
            SELECT filename, MAX(id) AS max_id
            FROM {_TABLE}
            WHERE owner_type=? AND owner_id=?
            GROUP BY filename
        ) latest ON m.filename = latest.filename AND m.id = latest.max_id
        WHERE m.is_deleted = 0
        ORDER BY m.filename
        """,
            (owner_type, owner_id),
        )
        .fetchall()
    )
    return [dict(r) for r in rows]


def read(owner_type: str, owner_id: str, filename: str) -> str | None:
    """Aktueller Inhalt einer Datei, oder None wenn nie angelegt/geloescht."""
    row = _latest_row(owner_type, owner_id, filename)
    if row is None or row["is_deleted"]:
        return None
    return row["content"]


def save(owner_type: str, owner_id: str, filename: str, content: str, message: str = "") -> None:
    """Legt eine neue, aktuelle Version an (INSERT, kein Overwrite)."""
    _ensure_table()
    db = _db()
    db.execute(
        f"INSERT INTO {_TABLE} (owner_type, owner_id, filename, content, message, is_deleted) "
        "VALUES (?,?,?,?,?,0)",
        (owner_type, owner_id, filename, content, message),
    )
    db.commit()


def delete(owner_type: str, owner_id: str, filename: str, message: str = "") -> None:
    """Markiert eine Datei als geloescht (neue Version, keine physische Loeschung)."""
    _ensure_table()
    db = _db()
    db.execute(
        f"INSERT INTO {_TABLE} (owner_type, owner_id, filename, content, message, is_deleted) "
        "VALUES (?,?,?,'',?,1)",
        (owner_type, owner_id, filename, message),
    )
    db.commit()


def diff(owner_type: str, owner_id: str, filename: str, new_content: str) -> str:
    """Unified diff zwischen aktueller Version und dem vorgeschlagenen neuen Inhalt."""
    old_content = read(owner_type, owner_id, filename) or ""
    return "".join(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"{filename} (aktuell)",
            tofile=f"{filename} (neu)",
        )
    )


def history(owner_type: str, owner_id: str, filename: str, limit: int = 20) -> list[dict]:
    """Vergangene Versionen einer Datei, neueste zuerst."""
    _ensure_table()
    rows = (
        _db()
        .execute(
            f"SELECT * FROM {_TABLE} WHERE owner_type=? AND owner_id=? AND filename=? "
            "ORDER BY id DESC LIMIT ?",
            (owner_type, owner_id, filename, limit),
        )
        .fetchall()
    )
    return [dict(r) for r in rows]


def restore(owner_type: str, owner_id: str, filename: str, version_id: int) -> None:
    """Legt den Inhalt einer historischen Version als neue aktuelle Version an."""
    _ensure_table()
    row = (
        _db()
        .execute(
            f"SELECT content FROM {_TABLE} WHERE id=? AND owner_type=? AND owner_id=? AND filename=?",
            (version_id, owner_type, owner_id, filename),
        )
        .fetchone()
    )
    if row is None:
        raise KeyError(f"Version {version_id} von '{filename}' nicht gefunden")
    save(owner_type, owner_id, filename, row["content"], message="Wiederhergestellt")


def materialize(owner_type: str, owner_id: str, target_dir: Path) -> None:
    """Schreibt alle aktuellen Dateien nach target_dir (fuer den Docker-Build).

    target_dir wird vorher geleert, damit keine veralteten/geloeschten
    Dateien aus einem frueheren Materialisierungslauf liegen bleiben.
    """
    target_dir = Path(target_dir)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for entry in list_files(owner_type, owner_id):
        (target_dir / entry["filename"]).write_text(entry["content"], encoding="utf-8")

# core/system/secrets.py
#
# Alle Credentials landen Fernet-verschlüsselt in SQLite.
#
# Trennung von Key und Daten (Threat-Model: DB-Datei-Diebstahl via Backup):
#
#   DB   → <app>/data/app.db         (landet in Backups → verschlüsselt)
#   Key  → <key_path>                (AUSSERHALB des Backup-Pfads, chmod 600)
#
# Ein Backup-Dump der DB ist ohne den Key wertlos.
# Der Key allein ist ohne die DB wertlos.
# Beide sind nie im selben Backup.

import os
from pathlib import Path
from cryptography.fernet import Fernet

_key_path_prod: Path | None = None
_key_path_dev:  Path | None = None


def configure(key_path: Path | str, dev_key_path: Path | str = None) -> None:
    """Setzt den Key-Pfad. Von der App beim Start aufzurufen.

    key_path:     Produktiv-Pfad (außerhalb des Backup-Verzeichnisses)
    dev_key_path: Fallback für Entwicklungsumgebungen ohne Produktiv-Pfad
    """
    global _key_path_prod, _key_path_dev
    _key_path_prod = Path(key_path)
    _key_path_dev  = Path(dev_key_path) if dev_key_path else None


def _key_path() -> Path:
    if _key_path_prod is None:
        raise RuntimeError("core.system.secrets nicht konfiguriert – configure() aufrufen!")
    try:
        _key_path_prod.parent.mkdir(parents=True, exist_ok=True)
        return _key_path_prod
    except (PermissionError, OSError):
        if _key_path_dev is None:
            raise
        _key_path_dev.parent.mkdir(parents=True, exist_ok=True)
        return _key_path_dev


def _fernet() -> Fernet:
    path = _key_path()
    if not path.exists():
        key = Fernet.generate_key()
        path.write_bytes(key)
        path.chmod(0o600)
    return Fernet(path.read_bytes())


def _db_set(key: str, value: str) -> None:
    from core.system.db import set_setting
    token = _fernet().encrypt(value.encode()).decode()
    set_setting(f"__secret__{key}", token)
    os.environ[key] = value


def _db_get(key: str, default: str = "") -> str:
    from core.system.db import get_setting
    token = get_setting(f"__secret__{key}", "")
    if not token:
        return default
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:
        return default


# ── Öffentliche API ───────────────────────────────────────────────────────────

def set_secret(key: str, value: str) -> None:
    """Speichert einen Credential-Wert Fernet-verschlüsselt in SQLite."""
    _db_set(key, value)


def get_secret(key: str) -> str:
    """Gibt einen Credential-Wert zurück – wirft RuntimeError wenn nicht gesetzt."""
    val = _db_get(key) or os.environ.get(key, "")
    if not val:
        raise RuntimeError(f"Secret '{key}' ist nicht gesetzt!")
    return val


def get_secret_safe(key: str, default: str = "") -> str:
    """Gibt einen Credential-Wert zurück, oder default wenn nicht gesetzt."""
    return _db_get(key) or os.environ.get(key, default) or default


def get_all_secrets() -> dict:
    """Gibt alle gesetzten Secrets als Klartext-Dict zurück."""
    from core.system.db import _conn, _init_settings
    _init_settings()
    rows = _conn().execute(
        "SELECT key, value FROM settings WHERE key LIKE '__secret__%'"
    ).fetchall()
    f = _fernet()
    result = {}
    for row in rows:
        env_key = row["key"].replace("__secret__", "", 1)
        try:
            result[env_key] = f.decrypt(row["value"].encode()).decode()
        except Exception:
            result[env_key] = ""
    return result


def key_location() -> str:
    """Gibt den tatsächlich verwendeten Key-Pfad zurück (für Logging/Diagnose)."""
    return str(_key_path())


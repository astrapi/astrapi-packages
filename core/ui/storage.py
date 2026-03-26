"""
core/ui/storage.py  –  SQLite-backed Key-Value Store für alle Module.

Daten werden in der zentralen SQLite-Datenbank in der Tabelle `kvstore`
gespeichert (Werte als JSON).  Ersetzt den früheren YAML-basierten Speicher.

Verwendung in einem Modul:
    from astrapi.core.ui.storage import SqliteStorage
    store = SqliteStorage("hosts")

    store.list()                          # dict aller Einträge
    store.get("web-01")                   # einzelner Eintrag oder None
    store.create("web-01", {...})         # neu anlegen
    store.update("web-01", {...})         # vorhandenen Eintrag aktualisieren
    store.delete("web-01")               # löschen
    store.toggle("web-01")               # enabled-Flag umschalten

Rückwärtskompatibilität: YamlStorage ist ein Alias für SqliteStorage.
Bestehende YAML-Dateien werden beim ersten Zugriff automatisch migriert.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable


class StorageNotInitialized(RuntimeError):
    pass


class SqliteStorage:
    """SQLite-backed Storage für eine Collection.

    Args:
        collection: Name der Collection (= früherer YAML-Dateiname ohne .yaml)
        seed_data:  Optionale Startdaten wenn die Collection leer ist
    """

    # Wird von init() gesetzt; nur für YAML-Migration benötigt
    _DATA_DIR: Path | None = None

    @classmethod
    def init(cls, app_root: Path) -> None:
        """Setzt das Datenverzeichnis und migriert alle vorhandenen YAML-Dateien.
        Wird automatisch von core/ui/app.py beim Start aufgerufen.
        """
        cls._DATA_DIR = app_root / "data"
        cls._DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls._migrate_all_yaml()

    @classmethod
    def _migrate_all_yaml(cls) -> None:
        """Migriert alle *.yaml-Dateien im Datenverzeichnis nach SQLite."""
        if cls._DATA_DIR is None:
            return
        for yaml_path in sorted(cls._DATA_DIR.glob("*.yaml")):
            if yaml_path.name == "settings.yaml":
                continue  # wird von settings_registry migriert
            collection = yaml_path.stem
            try:
                from astrapi.core.system.db import kv_list, kv_set_many
                if kv_list(collection):
                    yaml_path.rename(yaml_path.with_suffix(".yaml.migrated"))
                    continue
                import yaml as _yaml
                raw = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                if raw:
                    kv_set_many(collection, {k: json.dumps(v) for k, v in raw.items()})
                yaml_path.rename(yaml_path.with_suffix(".yaml.migrated"))
                print(f"[storage] Migriert: {collection} ({len(raw)} Einträge) → SQLite")
            except Exception as e:
                print(f"[storage] YAML-Migration fehlgeschlagen für {collection}: {e}")

    @classmethod
    def reset(cls) -> None:
        """Setzt den Klassen-Zustand zurück (für Test-Isolation)."""
        cls._DATA_DIR = None

    def __init__(self, collection: str, seed_data: dict | None = None):
        self.collection = collection
        self._seed      = seed_data or {}
        self._lock      = threading.Lock()
        self._migrated  = False

    # ── YAML-Migration ────────────────────────────────────────────

    def _maybe_migrate(self) -> None:
        """Fallback-Migration falls init() noch nicht aufgerufen wurde."""
        if self._migrated or SqliteStorage._DATA_DIR is None:
            self._migrated = True
            return
        # _migrate_all_yaml() wurde bereits in init() für alle YAMLs aufgerufen
        self._migrated = True

    # ── Lesen ─────────────────────────────────────────────────────

    def _load_all(self) -> dict:
        """Gibt alle Einträge der Collection als dict zurück."""
        from astrapi.core.system.db import kv_list
        raw = kv_list(self.collection)
        return {k: json.loads(v) for k, v in raw.items()}

    def list(
        self,
        filter_fn: "Callable[[str, dict], bool] | None" = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> dict:
        self._maybe_migrate()
        with self._lock:
            data = self._load_all()
            if not data and self._seed:
                from astrapi.core.system.db import kv_set_many
                kv_set_many(self.collection, {k: json.dumps(v) for k, v in self._seed.items()})
                data = dict(self._seed)

        if filter_fn is not None:
            data = {k: v for k, v in data.items() if filter_fn(k, v)}
        if offset:
            data = dict(list(data.items())[offset:])
        if limit is not None:
            data = dict(list(data.items())[:limit])
        return data

    def get(self, key: str) -> dict | None:
        self._maybe_migrate()
        from astrapi.core.system.db import kv_get
        raw = kv_get(self.collection, key)
        return json.loads(raw) if raw is not None else None

    def exists(self, key: str) -> bool:
        self._maybe_migrate()
        from astrapi.core.system.db import kv_get
        return kv_get(self.collection, key) is not None

    # ── Schreiben ─────────────────────────────────────────────────

    def create(self, key: str | None, values: dict) -> str:
        """Legt einen neuen Eintrag an.

        key=None ist für YamlStorage nicht sinnvoll (kein auto-increment) und
        wirft einen ValueError.  Gibt den verwendeten Schlüssel zurück.
        """
        if key is None:
            raise ValueError(
                f"YamlStorage '{self.collection}' unterstützt kein auto-increment "
                "(item_id=None). Bitte einen expliziten Schlüssel übergeben."
            )
        self._maybe_migrate()
        with self._lock:
            from astrapi.core.system.db import kv_get, kv_set
            if kv_get(self.collection, key) is not None:
                raise KeyError(f"'{key}' existiert bereits in '{self.collection}'")
            kv_set(self.collection, key, json.dumps(values))
        return key

    def update(self, key: str, values: dict) -> None:
        self._maybe_migrate()
        with self._lock:
            from astrapi.core.system.db import kv_get, kv_set
            raw = kv_get(self.collection, key)
            if raw is None:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            existing = json.loads(raw)
            existing.update(values)
            kv_set(self.collection, key, json.dumps(existing))

    def upsert(self, key: str, values: dict) -> dict:
        self._maybe_migrate()
        with self._lock:
            from astrapi.core.system.db import kv_get, kv_set
            raw = kv_get(self.collection, key)
            if raw is not None:
                existing = json.loads(raw)
                existing.update(values)
            else:
                existing = values
            kv_set(self.collection, key, json.dumps(existing))
        return existing

    def delete(self, key: str) -> bool:
        self._maybe_migrate()
        with self._lock:
            from astrapi.core.system.db import kv_get, kv_delete
            if kv_get(self.collection, key) is None:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            kv_delete(self.collection, key)
        return True

    def toggle(self, key: str, field: str = "enabled", default: bool = True) -> bool:
        self._maybe_migrate()
        with self._lock:
            from astrapi.core.system.db import kv_get, kv_set
            raw = kv_get(self.collection, key)
            if raw is None:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            data = json.loads(raw)
            current = bool(data.get(field, default))
            data[field] = not current
            kv_set(self.collection, key, json.dumps(data))
        return data[field]

    def __repr__(self) -> str:
        return f"SqliteStorage(collection={self.collection!r})"


# Rückwärtskompatibilität
YamlStorage = SqliteStorage


def init(app_root: Path) -> None:
    """Setzt das Datenverzeichnis für YAML-Migration.
    Wird automatisch von core/ui/app.py beim Start aufgerufen.
    """
    SqliteStorage.init(app_root)

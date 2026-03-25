"""
core/ui/settings_registry.py  –  Einstellungs-Registry (SQLite-backed)

Alle Einstellungen werden in der zentralen SQLite-Datenbank gespeichert
(kvstore-Tabelle, collection="_settings", Werte als JSON).

Beim ersten Start werden bestehende settings.yaml-Daten automatisch migriert.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_COLLECTION = "_settings"


class SettingsRegistry:
    """Kapselt den gesamten Zustand der Einstellungs-Registry.

    Alle öffentlichen Methoden sind thread-safe.
    Die Klasse kann mit reset() in den Ausgangszustand zurückversetzt werden
    (nützlich für Test-Isolation).
    """

    def __init__(self):
        self._data_dir: Path | None = None
        self._lock = threading.Lock()
        self._migrated = False

    def reset(self) -> None:
        with self._lock:
            self._data_dir = None
            self._migrated = False

    def init(self, app_root: Path) -> None:
        self._data_dir = app_root / "data"
        self._data_dir.mkdir(exist_ok=True)
        self._maybe_migrate()

    # ── YAML-Migration ─────────────────────────────────────────────

    def _maybe_migrate(self) -> None:
        if self._migrated or self._data_dir is None:
            return
        self._migrated = True
        yaml_path = self._data_dir / "settings.yaml"
        if not yaml_path.exists():
            return
        try:
            from core.system.db import kv_list
            if kv_list(_COLLECTION):
                yaml_path.rename(yaml_path.with_suffix(".yaml.migrated"))
                return
        except Exception:
            return  # DB noch nicht konfiguriert
        try:
            import yaml as _yaml

            class _SafeLoader(yaml.SafeLoader):
                pass
            _SafeLoader.add_multi_constructor(
                "tag:yaml.org,2002:python/",
                lambda loader, suffix, node: None,
            )
            raw = _yaml.load(yaml_path.read_text(encoding="utf-8"), Loader=_SafeLoader) or {}
            if raw:
                from core.system.db import kv_set_many
                kv_set_many(_COLLECTION, {k: json.dumps(v) for k, v in raw.items()})
            yaml_path.rename(yaml_path.with_suffix(".yaml.migrated"))
            print(f"[settings] Migriert: {len(raw)} Einstellungen → SQLite")
        except Exception as e:
            print(f"[settings] YAML-Migration fehlgeschlagen: {e}")

    # ── Interne Helfer ─────────────────────────────────────────────

    def _load(self) -> dict:
        try:
            from core.system.db import kv_list
            return {k: json.loads(v) for k, v in kv_list(_COLLECTION).items()}
        except Exception:
            return {}

    def _save_one(self, key: str, value: Any) -> None:
        try:
            from core.system.db import kv_set
            kv_set(_COLLECTION, key, json.dumps(value))
        except Exception:
            pass

    def _save_many(self, items: dict) -> None:
        try:
            from core.system.db import kv_set_many
            kv_set_many(_COLLECTION, {k: json.dumps(v) for k, v in items.items()})
        except Exception:
            pass

    def _delete_one(self, key: str) -> None:
        try:
            from core.system.db import kv_delete
            kv_delete(_COLLECTION, key)
        except Exception:
            pass

    # ── Öffentliche API ────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            data = self._load()
            return data.get(key, default)

    def get_module(self, module_key: str, key: str, default: Any = None) -> Any:
        return self.get(f"module.{module_key}.{key}", default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._save_one(key, value)

    def set_module(self, module_key: str, key: str, value: Any) -> None:
        self.set(f"module.{module_key}.{key}", value)

    def set_many(self, values: dict) -> None:
        with self._lock:
            self._save_many(values)

    def all_settings(self) -> dict:
        with self._lock:
            return self._load()

    def seed_defaults(self, global_defaults: dict, modules: list) -> None:
        """Füllt fehlende Werte mit Defaults auf und bereinigt verwaiste Modul-Keys."""
        with self._lock:
            current = self._load()
            to_add: dict = {}

            for k, v in global_defaults.items():
                if k not in current:
                    to_add[k] = v

            for mod in modules:
                for k, v in mod.settings_defaults.items():
                    full_key = f"module.{mod.key}.{k}"
                    if full_key not in current:
                        to_add[full_key] = v

            if to_add:
                self._save_many(to_add)
                current.update(to_add)

            # Verwaiste Modul-Keys entfernen
            known = {mod.key for mod in modules}
            orphaned = [
                k for k in current
                if k.startswith("module.") and k.split(".")[1] not in known
            ]
            for k in orphaned:
                self._delete_one(k)


# Modul-level Singleton
_registry = SettingsRegistry()


def __getattr__(name: str):
    return getattr(_registry, name)

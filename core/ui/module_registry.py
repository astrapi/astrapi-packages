"""
core/ui/module_registry.py  –  AstrapiFlaskUi V3  Modul-Registry

Navigation:
  1. app/templates/navigation/items.yaml   – optionaler Override (Reihenfolge, Label, Gruppe)
  2. core/templates/navigation/items.yaml  – Core-Module (sysinfo, settings)
  3. Alle geladenen App-Module die in keiner YAML stehen → automatisch angehängt

Ein neues Modul erscheint also automatisch in der Nav, sobald sein Ordner
existiert und eine Module-Instanz exportiert. Die YAML ist optional.
"""

from __future__ import annotations

import importlib.util
import sys
import warnings
from pathlib import Path

CORE_ROOT    = Path(__file__).resolve().parent           # core/ui/  (templates, static)
CORE_MOD_DIR = Path(__file__).resolve().parents[1] / "modules"  # core/modules/
CORE_NAV_YAML = Path(__file__).resolve().parents[1] / "navigation.yaml"  # core/navigation.yaml


class ModuleRegistry:
    """Kapselt das Modul-Verzeichnis der geladenen Module.

    Kann mit reset() in den Ausgangszustand zurückversetzt werden
    (nützlich für Test-Isolation).
    """

    def __init__(self):
        self._registry: dict = {}

    def reset(self) -> None:
        """Setzt die Registry zurück (für Test-Isolation)."""
        self._registry = {}

    def update(self, modules: dict) -> None:
        """Aktualisiert die Registry mit einem Dict aus {key: module}."""
        self._registry.update(modules)

    def get(self, key: str):
        """Gibt eine Modul-Instanz anhand ihres Keys zurück oder None."""
        return self._registry.get(key)

    def all(self) -> dict:
        """Gibt eine Kopie der gesamten Registry zurück."""
        return dict(self._registry)

    def __contains__(self, key: str) -> bool:
        return key in self._registry

    def __getitem__(self, key: str):
        return self._registry[key]


# Modul-level Singleton – wird von load_modules() befüllt; von FastAPI-Templates genutzt
_instance = ModuleRegistry()

# Rückwärtskompatibilität: Code der direkt auf _mod_registry zugreift
_mod_registry: dict = _instance._registry


# ── Laden ─────────────────────────────────────────────────────────────────────

def _load_from_dir(modules_dir: Path, pkg_prefix: str) -> dict:
    """Lädt alle Module-Instanzen aus einem Verzeichnis → {key: instance}."""
    from astrapi.core.ui._base import Module

    found: dict[str, Module] = {}
    if not modules_dir.exists():
        return found

    for entry in sorted(modules_dir.iterdir()):
        if entry.name.startswith("_"):
            continue

        if entry.is_dir():
            py_file = entry / "__init__.py"
            name = entry.name
            mod_root = entry
        elif entry.is_file() and entry.suffix == ".py":
            py_file = entry
            name = entry.stem
            mod_root = None
        else:
            continue

        if not py_file.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"{pkg_prefix}.{name}", py_file
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[f"{pkg_prefix}.{name}"] = mod
            spec.loader.exec_module(mod)
            instance = getattr(mod, "module", None)
            if instance is None or not isinstance(instance, Module):
                warnings.warn(f"Modul '{name}' ({pkg_prefix}): keine Module-Instanz gefunden")
                continue
            if mod_root is not None:
                # module_root nur setzen wenn dieses Verzeichnis Templates hat
                # oder noch kein module_root gesetzt ist (z.B. app re-exportiert Core-Instanz)
                if instance.module_root is None or (mod_root / "templates").exists():
                    instance.module_root = mod_root
                # settings.yaml nachladen wenn das Modul es nicht selbst gesetzt hat
                if not instance.settings_schema:
                    settings_yaml = mod_root / "settings.yaml"
                    if settings_yaml.exists():
                        import yaml as _yaml
                        with open(settings_yaml, encoding="utf-8") as _f:
                            instance.settings_schema = _yaml.safe_load(_f) or []
            found[instance.key] = instance
        except Exception as e:
            warnings.warn(f"Modul '{name}' ({pkg_prefix}) konnte nicht geladen werden: {e}")

    return found


def load_modules(app_root: Path) -> list:
    """Lädt Module aus core/modules/, app/overrides/ und app/modules/.

    Priorität (höher überschreibt niedrigere):
      app/modules/    > app/overrides/ > core/modules/
    app/overrides/   – Module die Core-Module überschreiben/ergänzen
    app/modules/      – reine App-Module
    Reihenfolge im Ergebnis: core zuerst, dann app-exklusive.

    Core-Module können per Einstellung deaktiviert werden:
      core.module.<key>.enabled = "0"  →  Modul wird nicht geladen
    """
    core_mods = _load_from_dir(CORE_MOD_DIR,              "core.modules")
    ext_mods  = _load_from_dir(app_root / "overrides",   "app.overrides")
    app_mods  = _load_from_dir(app_root / "modules",      "app.modules")

    # Deaktivierte Core-Module herausfiltern (Einstellung: core.module.<key>.enabled != "0")
    try:
        from astrapi.core.ui.settings_registry import get as _settings_get
        core_mods = {
            k: v for k, v in core_mods.items()
            if _settings_get(f"core.module.{k}.enabled", "1") != "0"
        }
    except Exception:
        pass

    # module_root erben: Overrides ohne eigene Templates übernehmen Core-Pfad
    def _inherit_root(overrides: dict, base: dict) -> None:
        for key, m in overrides.items():
            if key in base:
                ref = base[key]
                if m.module_root is None or not (m.module_root / "templates").exists():
                    m.module_root = ref.module_root

    _inherit_root(ext_mods, core_mods)
    _inherit_root(app_mods, {**core_mods, **ext_mods})

    merged  = {**core_mods, **ext_mods, **app_mods}
    ordered = []
    seen: set = set()
    for key in sorted(core_mods):
        ordered.append(merged[key]); seen.add(key)
    for key in sorted({**ext_mods, **app_mods}):
        if key not in seen:
            ordered.append(merged[key]); seen.add(key)
    _instance.update({m.key: m for m in ordered})
    return ordered


# ── Registrieren ──────────────────────────────────────────────────────────────

def register_flask_modules(flask_app, modules: list, jinja_loaders: list) -> None:
    from jinja2 import FileSystemLoader, PrefixLoader

    for mod in modules:
        if mod.module_root:
            tpl_dir = mod.module_root / "templates"
            if tpl_dir.exists():
                # PrefixLoader mit mod.key als Prefix → unabhängig vom Ordnernamen.
                # render_template("hosts/partials/list.html") sucht in
                # {module_root}/templates/partials/list.html – egal ob der Ordner
                # "hosts", "test" oder anders heißt.
                jinja_loaders.insert(0, PrefixLoader(
                    {mod.key: FileSystemLoader(str(tpl_dir))}
                ))

        if mod.ui_blueprint is not None:
            try:
                flask_app.register_blueprint(mod.ui_blueprint)
            except Exception as e:
                warnings.warn(f"Blueprint '{mod.key}' konnte nicht registriert werden: {e}")


def register_fastapi_modules(fastapi_app, modules: list) -> None:
    for mod in modules:
        if mod.api_router is not None:
            try:
                fastapi_app.include_router(
                    mod.api_router,
                    prefix=f"/api/{mod.key}",
                    tags=[mod.key],
                )
            except Exception as e:
                warnings.warn(f"Router '{mod.key}' konnte nicht registriert werden: {e}")


# ── Navigation ────────────────────────────────────────────────────────────────

def _yaml_to_nav_items(yaml_path: "Path | None", modules: dict, raw: list = None) -> list[dict]:
    """Liest Nav-Einträge aus einer items.yaml oder direkt aus einer Liste."""
    import yaml

    if raw is None:
        if yaml_path is None or not yaml_path.exists():
            return []
        with open(yaml_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []

    items: list[dict] = []
    current_group: str = ""

    for entry in raw:
        key = entry.get("key")
        if not key:
            continue

        mod   = modules.get(key)
        # Modul-Einträge ohne explizite URL überspringen wenn Modul nicht geladen
        if mod is None and not entry.get("url"):
            continue
        group = entry.get("group", "")

        if group != current_group:
            items.append({"separator": True, "group": group})
            current_group = group

        items.append({
            "key":       key,
            "label":     entry.get("label") or (mod.label if mod else key.replace("_", " ").title()),
            "url":       entry.get("url")   or (mod.nav_url if mod else f"/{key}"),
            "icon":      entry.get("icon")  or (mod.icon if mod else "home"),
            "default":   bool(entry.get("default", False)),
            "separator": False,
        })

    return items


def _auto_nav_item(mod) -> dict:
    """Erzeugt einen Nav-Eintrag direkt aus der Modul-Instanz."""
    return mod.to_nav_item()


def build_nav_items(modules: list, app_root: Path) -> list[dict]:
    """Baut die komplette nav_items-Liste.

    Reihenfolge:
      1. app/navigation.yaml  – App-spezifische Module
      2. App-Module die nicht in der YAML stehen → automatisch angehängt (Gruppe "Module")
      3. core/navigation.yaml – Core-Module (notify, scheduler, sysinfo, settings)
    """
    mod_map = {m.key: m for m in modules}

    app_yaml  = app_root / "navigation.yaml"
    core_yaml = CORE_NAV_YAML

    app_items  = _yaml_to_nav_items(app_yaml,  mod_map)
    core_items = _yaml_to_nav_items(core_yaml, mod_map)

    # App-Module die in keiner YAML stehen → automatisch anhängen
    yaml_keys  = {i["key"] for i in app_items  if not i.get("separator")}
    yaml_keys |= {i["key"] for i in core_items if not i.get("separator")}

    core_modules_dir = CORE_MOD_DIR
    auto_mods = [
        m for m in modules
        if m.key not in yaml_keys
        and not (m.module_root and m.module_root.parent == core_modules_dir)
    ]

    if auto_mods:
        existing_groups = {i.get("group") for i in app_items if i.get("separator")}
        if "Module" not in existing_groups:
            app_items.append({"separator": True, "group": "Module"})
        for mod in auto_mods:
            app_items.append(_auto_nav_item(mod))

    # Core-Items deduplizieren: Keys die bereits in app_items stehen überspringen.
    app_keys = {i["key"] for i in app_items if not i.get("separator")}
    filtered_core: list[dict] = []
    pending_sep = None
    for item in core_items:
        if item.get("separator"):
            pending_sep = item
        elif item["key"] not in app_keys:
            if pending_sep:
                filtered_core.append(pending_sep)
                pending_sep = None
            filtered_core.append(item)

    items = app_items + filtered_core

    # Fallback wenn gar nichts da ist
    if not items:
        seen_groups: set[str] = set()
        for mod in modules:
            group = mod.nav_group or "Module"
            if group not in seen_groups:
                items.append({"separator": True, "group": group})
                seen_groups.add(group)
            items.append(_auto_nav_item(mod))
        items.append({"separator": True, "group": "System"})
        items.append({
            "key": "settings", "label": "Einstellungen",
            "url": "/ui/settings", "icon": "settings",
            "default": False, "separator": False,
        })

    _set_default(items)
    return items


def list_available_core_modules() -> list:
    """Gibt alle verfügbaren Core-Module mit key, label und enabled-Status zurück.

    Liest die modul.yaml für den Anzeigenamen. Der enabled-Status kommt aus der
    Settings-Registry (core.module.<key>.enabled != '0' → aktiv).
    """
    import yaml as _yaml
    try:
        from astrapi.core.ui.settings_registry import get as _settings_get
    except Exception:
        def _settings_get(k, d=None): return d

    result = []
    if not CORE_MOD_DIR.exists():
        return result
    for entry in sorted(CORE_MOD_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        key = entry.name
        enabled = _settings_get(f"core.module.{key}.enabled", "1") != "0"
        label = key.replace("_", " ").title()
        modul_yaml = entry / "modul.yaml"
        if modul_yaml.exists():
            try:
                data = _yaml.safe_load(modul_yaml.read_text(encoding="utf-8")) or {}
                label = data.get("label", label)
            except Exception:
                pass
        result.append({"key": key, "label": label, "enabled": enabled})
    return result


def _set_default(items: list[dict]) -> None:
    """Setzt das erste Non-Separator-Item als Default wenn keines gesetzt ist."""
    if not any(not i.get("separator") and i.get("default") for i in items):
        for item in items:
            if not item.get("separator"):
                item["default"] = True
                break

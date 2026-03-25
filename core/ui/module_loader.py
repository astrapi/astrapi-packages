"""
core/ui/module_loader.py  –  Lädt modul.yaml und erstellt Module-Instanz

modul.yaml liegt im Root jedes Moduls neben __init__.py:

  label:       Hosts
  icon:        server
  nav_group:   Module
  nav_default: true

  settings_defaults:
    default_port: "22"
"""

import yaml
from pathlib import Path

# ---------------------------------------------------------------------------
# Vordefinierte Aktionstypen – Defaults sind nicht überschreibbar.
# YAML kann nur  url  und  hx_push_url  ergänzen.
# ---------------------------------------------------------------------------
_CARD_ACTION_TYPES: dict[str, dict] = {
    "run": {
        "title":           "Ausführen",
        "icon":            "play",
        "style":           "run",
        "hx_post":         "/api/{module}/{item}/run",
        "hx_target":       "#{container_id}",
        "hx_swap":         "innerHTML",
        "hx_headers":      '{"HX-Request": "true"}',
        "disabled_if_off": True,
    },
    "run_debug": {
        "title":           "Ausführen (Debug)",
        "icon":            "play-debug",
        "style":           "debug",
        "hx_post":         "/api/{module}/{item}/run?debug=true",
        "hx_target":       "#{container_id}",
        "hx_swap":         "innerHTML",
        "hx_headers":      '{"HX-Request": "true"}',
    },
    "log": {
        "title":    "Log anzeigen",
        "icon":     "file-text",
        "style":    "log",
        "hx_get":   "/api/{module}/{item}/logs",
        "hx_target":"body",
        "hx_swap":  "beforeend",
    },
    "search": {
        "title":    "Durchsuchen",
        "icon":     "search",
        "style":    "run",
        "hx_get":   "",
        "hx_target":"#main-content",
        "hx_swap":  "innerHTML",
    },
    "bar-chart": {
        "title":    "Statistiken",
        "icon":     "bar-chart",
        "style":    "log",
        "hx_get":   "",
        "hx_target":"#main-content",
        "hx_swap":  "innerHTML",
    },
    "power-on": {
        "title":           "Aufwecken (Wake on LAN)",
        "icon":            "power-on",
        "style":           "run",
        "hx_get":          "",
        "hx_target":       "body",
        "hx_swap":         "beforeend",
        "disabled_if_off": True,
    },
    "power-off": {
        "title":           "Herunterfahren (SSH Poweroff)",
        "icon":            "power-off",
        "style":           "danger",
        "hx_get":          "",
        "hx_target":       "body",
        "hx_swap":         "beforeend",
        "disabled_if_off": True,
    },
    "scan-host-key": {
        "title":     "SSH Host Key eintragen (known_hosts)",
        "icon":      "shield",
        "style":     "log",
        "hx_get":    "",
        "hx_target": "body",
        "hx_swap":   "beforeend",
    },
    "preview": {
        "title":    "Befehlsvorschau",
        "icon":     "terminal",
        "style":    "log",
        "hx_get":   "/api/{module}/{item}/preview",
        "hx_target":"body",
        "hx_swap":  "beforeend",
    },
    "archives": {
        "title":    "Archive anzeigen",
        "icon":     "archive",
        "style":    "log",
        "hx_get":   "/api/{module}/{item}/archives",
        "hx_target":"body",
        "hx_swap":  "beforeend",
    },
    "stats": {
        "title":    "Statistiken",
        "icon":     "bar-chart",
        "style":    "log",
        "hx_get":   "/api/{module}/{item}/stats",
        "hx_target":"body",
        "hx_swap":  "beforeend",
    },
}

_POST_TYPES = {"run", "run_debug"}


def _expand_card_actions(actions: list, module_key: str) -> list:
    """Expandiert Typ-Shortcuts zu vollständigen card_action-Dicts.

    Erlaubte YAML-Felder neben  type:  url, hx_push_url.
    Alle anderen Felder (title, icon, style …) kommen ausschließlich
    aus _CARD_ACTION_TYPES und sind nicht überschreibbar.
    """
    expanded = []
    for action in actions:
        t = action.get("type")
        if t and t in _CARD_ACTION_TYPES:
            merged = {k: v for k, v in _CARD_ACTION_TYPES[t].items()}
            # {module}-Platzhalter in den Defaults ersetzen
            for k, v in merged.items():
                if isinstance(v, str):
                    merged[k] = v.replace("{module}", module_key)
            # Nur  url  und  hx_push_url  dürfen aus der YAML kommen
            if "url" in action:
                url = action["url"]
                if t in _POST_TYPES:
                    merged["hx_post"] = url
                else:
                    merged["hx_get"] = url
            if "hx_push_url" in action:
                merged["hx_push_url"] = action["hx_push_url"]
            expanded.append(merged)
        else:
            expanded.append(action)
    return expanded


def load_modul(module_dir: Path, key: str, api_router, ui_blueprint) -> "Module":
    from core.ui._base import Module

    yaml_path = module_dir / "modul.yaml"
    cfg = {}
    if yaml_path.exists():
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # settings.yaml laden (dict-Format mit modal_width + fields, oder Legacy-Liste)
    settings_yaml = module_dir / "settings.yaml"
    settings_schema: list = []
    settings_modal_width: int = 480
    if settings_yaml.exists():
        with open(settings_yaml, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if isinstance(raw, dict):
            settings_schema = raw.get("fields", [])
            settings_modal_width = raw.get("modal_width", 480)
        else:
            settings_schema = raw  # Legacy: flache Liste

    # Defaults aus settings.yaml extrahieren; modul.yaml settings_defaults haben Vorrang
    schema_defaults = {
        field["key"]: field["default"]
        for field in settings_schema
        if "key" in field and "default" in field
    }
    merged_defaults = {**schema_defaults, **cfg.get("settings_defaults", {})}

    return Module(
        key                  = key,
        label                = cfg.get("label",       key.capitalize()),
        icon                 = cfg.get("icon",         "list"),
        api_router           = api_router,
        ui_blueprint         = ui_blueprint,
        nav_group            = cfg.get("nav_group",    "Module"),
        nav_default          = bool(cfg.get("nav_default", False)),
        settings_defaults    = merged_defaults,
        settings_schema      = settings_schema,
        settings_modal_width = settings_modal_width,
        card_actions         = _expand_card_actions(cfg.get("card_actions", []), key),
        module_root          = module_dir,
    )


def reload_settings(mod: "Module") -> None:
    """Liest settings.yaml neu ein und aktualisiert mod in-place (für Dev-Hot-Reload)."""
    if mod.module_root is None:
        return
    settings_yaml = mod.module_root / "settings.yaml"
    if not settings_yaml.exists():
        return
    with open(settings_yaml, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if isinstance(raw, dict):
        mod.settings_schema = raw.get("fields", [])
        mod.settings_modal_width = raw.get("modal_width", 480)
    else:
        mod.settings_schema = raw

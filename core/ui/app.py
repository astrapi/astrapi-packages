"""
core/ui/app.py  –  AstrapiFlaskUi V3  Framework-Factory

Neu gegenüber V2:
  - Lädt alle Module aus app/modules/ automatisch
  - Registriert Modul-Flask-Blueprints und Template-Loader
  - Baut Navigation aus Modulen + optionaler items.yaml zusammen
  - Initialisiert Einstellungs-Registry (global + Modul-Defaults)
  - Registriert /settings als festen Endpunkt mit Speicher-Routen
"""

from __future__ import annotations

from flask import Flask, redirect, send_from_directory, render_template, request, jsonify
from pathlib import Path
from jinja2 import ChoiceLoader, FileSystemLoader
import importlib.util
from typing import Optional, Callable

from .page_factory import register_pages
from .swagger_utils import register_ui_docs
from .module_registry import load_modules, register_flask_modules, build_nav_items, list_available_core_modules
from ..system.version import get_app_version, get_app_name, get_display_name, get_core_version
from .settings_registry import (
    init as settings_init, seed_defaults, set_many, all_settings,
    get as settings_get, set as settings_set,
)
from .storage import init as storage_init

CORE_ROOT = Path(__file__).resolve().parent


def _load_module_file(name: str, path: Path):
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def create(
    app_root:   Path,
    config:     Optional[dict] = None,
    extra_init: Optional[Callable] = None,
    modules:    Optional[list] = None,
) -> Flask:
    """Erstellt und konfiguriert die Flask-Anwendung mit Modul-Unterstützung.

    modules: Vorgeladene Modulliste (z.B. aus main.py). Wird nicht neu geladen
             wenn angegeben – verhindert doppelten Modulaufruf.
    """

    core_static = CORE_ROOT / "static"
    app_static  = app_root / "static"

    # ── Flask-Subklasse: app/static/ überschreibt core/static/ ──────────────
    class _App(Flask):
        def send_static_file(self, filename: str):
            candidate = app_static / filename
            if app_static.exists() and candidate.is_file():
                return send_from_directory(str(app_static), filename)
            return super().send_static_file(filename)

    app = _App(
        __name__,
        static_folder=str(core_static),
        static_url_path="/static",
    )

    import os
    _debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.config.update(
        DEBUG=_debug,
        TEMPLATES_AUTO_RELOAD=_debug,
        SEND_FILE_MAX_AGE_DEFAULT=0 if _debug else 3600,
    )
    if config:
        app.config.update(config)

    # ── App-Konfiguration laden ───────────────────────────────────────────────
    app_cfg: dict = {}
    cfg_yaml = app_root / "config.yaml"
    if cfg_yaml.exists():
        import yaml as _yaml
        with open(cfg_yaml, encoding="utf-8") as _f:
            _raw = _yaml.safe_load(_f) or {}
        _app = _raw.get("app", {})
        app_cfg = {
            "APP_NAME":       _app.get("name",       "myapp"),
            "APP_LANG":       _app.get("lang",        "de"),
            "LIGHT_MODE":     bool(_app.get("light_mode", False)),
            "APP_LOGO_SVG":   _app.get("logo_svg",   None),
            "APP_ICON_THEME": _app.get("icon_theme", "default"),
        }
    else:
        for cfg_name in ("settings.py", "config.py"):
            cfg_path = app_root / cfg_name
            if cfg_path.exists():
                mod     = _load_module_file("app_settings", cfg_path)
                app_cfg = {k: v for k, v in vars(mod).items() if not k.startswith("_")}
                break

    _app_version  = get_app_version(app_root)
    _app_name     = get_app_name(app_root)
    _display_name = get_display_name(app_root)
    _core_version = get_core_version(CORE_ROOT.parent)

    light_mode: bool = app_cfg.get("LIGHT_MODE", False)

    # ── Module laden (nur wenn nicht bereits von außen übergeben) ─────────────
    if modules is None:
        modules = load_modules(app_root)

    # ── Einstellungs-Registry initialisieren ──────────────────────────────────
    settings_init(app_root)
    storage_init(app_root)
    _light_default = "1" if app_cfg.get("LIGHT_MODE", False) else "0"
    global_defaults = {
        k: v for k, v in app_cfg.items()
        if k not in ("LIGHT_MODE", "APP_LOGO_SVG", "APP_ICON_THEME") and not callable(v)
    }
    global_defaults.setdefault("LIGHT_MODE",      _light_default)
    global_defaults.setdefault("APP_ICON_THEME",  app_cfg.get("APP_ICON_THEME", "lucide"))
    global_defaults.setdefault("TIMEZONE",        "Europe/Berlin")
    global_defaults.setdefault("DATE_FORMAT",     "DD.MM.YYYY")
    seed_defaults(global_defaults, modules)

    app.config["LOADED_MODULES"] = modules

    # ── Template-Loader: Modul > App > Core ──────────────────────────────────
    app_templates  = app_root / "templates"
    core_templates = CORE_ROOT / "templates"

    base_loaders: list = []
    if app_templates.exists():
        base_loaders.append(FileSystemLoader(str(app_templates)))
    base_loaders.append(FileSystemLoader(str(core_templates)))

    # register_flask_modules fügt Modul-Loader vorne ein (höchste Priorität)
    all_loaders = list(base_loaders)
    register_flask_modules(app, modules, all_loaders)

    app.jinja_env.loader = ChoiceLoader(all_loaders)
    app.jinja_env.auto_reload = True
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # ── Globale Template-Variablen ────────────────────────────────────────────
    _mod_map: dict = {m.key: m for m in modules}

    @app.context_processor
    def _inject_globals():
        def module_has_settings(key: str) -> bool:
            m = _mod_map.get(key)
            return bool(m and m.settings_schema)

        def module_label(key: str) -> str:
            m = _mod_map.get(key)
            return m.label if m else key.replace("_", " ").title()

        def module_card_actions(key: str) -> list:
            m = _mod_map.get(key)
            return m.card_actions if m else []

        def col_widths(module_key: str) -> str:
            return settings_get(f"ui.col_widths.{module_key}", "{}")

        def resolve_remote_host(remote_id) -> str:
            if not remote_id:
                return "—"
            try:
                from app.modules.remotes.engine import get_remote
                r = get_remote(remote_id)
                return r.get("host") or "—" if r else "—"
            except Exception:
                return "—"

        def last_run_status(module: str, item_id) -> str | None:
            try:
                from core.system.activity_log import list_runs_for_item
                runs = list_runs_for_item(module, str(item_id), limit=5)
                for run in runs:
                    if run.get("status") != "running":
                        return run.get("status")
            except Exception:
                pass
            return None

        from core.ui.settings_registry import get as _srget
        _light = _srget("LIGHT_MODE", _light_default)
        return {
            "app_name":             _display_name,
            "app_version":          _app_version,
            "core_version":         _core_version,
            "app_logo_svg":         app_cfg.get("APP_LOGO_SVG", None),
            "app_lang":             _srget("APP_LANG", app_cfg.get("APP_LANG", "de")),
            "light_mode":           (_light == "1" or _light is True),
            "icon_theme":           _srget("APP_ICON_THEME", app_cfg.get("APP_ICON_THEME", "lucide"))
                                    if _srget("APP_ICON_THEME", "lucide") in {"lucide", "heroicons", "tabler"}
                                    else "lucide",
            "modules":              modules,
            "module_has_settings":  module_has_settings,
            "module_label":         module_label,
            "module_card_actions":  module_card_actions,
            "col_widths":           col_widths,
            "resolve_remote_host":  resolve_remote_host,
            "last_run_status":      last_run_status,
        }

    # ── Navigation aus Modulen + optionaler items.yaml ────────────────────────
    nav_items  = build_nav_items(modules, app_root=app_root)

    @app.context_processor
    def _inject_nav():
        return {"nav_items": nav_items}

    # ── Seiten-Routen registrieren (Page + Tab + List pro Nav-Item) ───────────
    # "settings" wird von _register_settings_routes separat behandelt
    # Modul-Keys mit eigenem Blueprint registrieren tab/list selbst
    module_keys = {m.key for m in modules if m.ui_blueprint is not None}
    # Nur "settings" herausfiltern — Modul-Keys bleiben drin für Shell+Redirect
    register_pages(app, [it for it in nav_items if it.get("key") != "settings"],
                   shell_only_keys=module_keys)

    # ── Optionale App-Blueprints: app/routes/__init__.py ─────────────────────
    routes_init_path = app_root / "routes" / "__init__.py"
    if routes_init_path.exists():
        mod = _load_module_file("app_routes", routes_init_path)
        if hasattr(mod, "register"):
            mod.register(app)
        elif hasattr(mod, "blueprint"):
            app.register_blueprint(mod.blueprint)

    # ── Einstellungs-Routen ───────────────────────────────────────────────────
    # Hat ein settings-Modul einen eigenen Blueprint, übernimmt er /ui/settings/content.
    settings_has_blueprint = any(m.key == "settings" and m.ui_blueprint for m in modules)
    _register_settings_routes(app, modules, app_cfg,
                               skip_content=settings_has_blueprint)
    _register_preferences_routes(app)

    # ── Generische Modul-Settings-Modal-Routen ────────────────────────────────
    _register_module_settings_routes(app, modules)

    # ── Projektspezifischer Hook ──────────────────────────────────────────────
    if extra_init:
        extra_init(app)

    # ── Scheduler starten ─────────────────────────────────────────────────────
    try:
        from core.modules.scheduler.engine import init as scheduler_init
        scheduler_init()
    except Exception as _e:
        import warnings
        warnings.warn(f"Scheduler konnte nicht gestartet werden: {_e}")

    # ── Root-Redirect → erstes/default Nav-Item ───────────────────────────────
    default_item = next(
        (it for it in nav_items if not it.get("separator") and it.get("default")),
        next((it for it in nav_items if not it.get("separator")), None),
    )
    if default_item:
        @app.get("/")
        def _root():
            return redirect(f"/{default_item['key']}")

    # ── Swagger UI-Docs ───────────────────────────────────────────────────────
    swagger_html = CORE_ROOT / "static" / "swagger.html"
    if not swagger_html.exists():
        swagger_html = app_root / "static" / "swagger.html"
    try:
        register_ui_docs(app, project_root=CORE_ROOT.parent, swagger_html_path=swagger_html)
    except Exception as e:
        import warnings
        warnings.warn(f"UI-Docs konnten nicht registriert werden: {e}")

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Einstellungs-Routen
# ─────────────────────────────────────────────────────────────────────────────

def _register_settings_routes(app: Flask, modules: list, app_cfg: dict,
                               skip_content: bool = False) -> None:
    """Registriert Tab- und Speicher-Routen für die Einstellungsseite.

    skip_content: True wenn ein settings-Modul mit Blueprint /ui/settings/content selbst bedient.
    """

    def _ctx(flash: str = "") -> dict:
        return {
            "settings":         all_settings(),
            "modules":          modules,
            "app_cfg":          app_cfg,
            "flash_message":    flash,
            "core_module_list": list_available_core_modules(),
        }

    @app.route("/settings")
    def settings_shell():
        return render_template(
            "index.html",
            active_tab="settings",
            initial_content_url="/ui/settings/content",
            title="Einstellungen",
        )

    if not skip_content:
        @app.route("/ui/settings/content")
        def settings_content():
            return render_template("partials/lists/settings.html", **_ctx())

    @app.route("/ui/settings/save/global", methods=["POST"])
    def settings_save_global():
        set_many(request.form.to_dict())
        return render_template(
            "partials/lists/settings.html",
            **_ctx("Globale Einstellungen gespeichert."),
        )

    @app.route("/ui/settings/save/module/<module_key>", methods=["POST"])
    def settings_save_module(module_key: str):
        mod = next((m for m in modules if m.key == module_key), None)
        if mod is None:
            return "Modul nicht gefunden", 404
        prefixed = {f"module.{module_key}.{k}": v
                    for k, v in request.form.to_dict().items()}
        set_many(prefixed)
        return render_template(
            "partials/lists/settings.html",
            **_ctx(f"Einstellungen für \"{mod.label}\" gespeichert."),
        )

    @app.route("/ui/settings/core-module/<key>/toggle", methods=["POST"])
    def settings_toggle_core_module(key: str):
        current = settings_get(f"core.module.{key}.enabled", "1")
        settings_set(f"core.module.{key}.enabled", "0" if current != "0" else "1")
        return render_template(
            "partials/lists/settings.html",
            **_ctx(f"Core-Modul '{key}' {'deaktiviert' if current != '0' else 'aktiviert'}. Neustart erforderlich."),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Generische Modul-Settings-Modal-Routen
# ─────────────────────────────────────────────────────────────────────────────

def _register_module_settings_routes(app: Flask, modules: list) -> None:
    """Registriert GET/POST /ui/<key>/settings für Module mit settings_schema."""
    from .settings_registry import get_module, set_many as _set_many
    from core.system.secrets import set_secret, get_secret_safe

    mod_map = {m.key: m for m in modules if m.settings_schema}
    if not mod_map:
        return

    @app.route("/ui/<module_key>/settings", methods=["GET", "POST"])
    def module_settings_modal(module_key: str):
        mod = mod_map.get(module_key)
        if mod is None:
            return "", 404

        if request.method == "GET":
            from core.ui.module_loader import reload_settings
            reload_settings(mod)

        if request.method == "POST":
            password_keys = {
                f["key"] for f in mod.settings_schema if f.get("type") == "password"
            }
            list_keys = {
                f["key"] for f in mod.settings_schema if f.get("type") == "list"
            }
            prefixed = {}
            # Listen-Felder: fieldname_0, fieldname_1, … → list
            for lk in list_keys:
                items = []
                i = 0
                while True:
                    val = request.form.get(f"{lk}_{i}")
                    if val is None:
                        break
                    if val.strip():
                        items.append(val.strip())
                    i += 1
                prefixed[f"module.{module_key}.{lk}"] = items
            # Alle anderen Felder
            handled = {f"{lk}_{i}" for lk in list_keys for i in range(50)}
            for k, v in request.form.to_dict().items():
                if k in handled:
                    continue
                if k in password_keys:
                    if v.strip():
                        set_secret(f"module.{module_key}.{k}", v.strip())
                    # Leeres Passwort-Feld nicht speichern
                else:
                    prefixed[f"module.{module_key}.{k}"] = v
            _set_many(prefixed)

        password_keys_all = {
            f["key"] for f in mod.settings_schema if f.get("type") == "password"
        }
        current_values = {
            field["key"]: (
                get_secret_safe(f"module.{module_key}.{field['key']}", field.get("default", ""))
                if field["key"] in password_keys_all
                else get_module(module_key, field["key"], field.get("default", ""))
            )
            for field in mod.settings_schema
            if "key" in field
        }
        from core.ui.field_resolver import resolve_options_endpoint
        return render_template(
            "partials/settings_modal.html",
            mod=mod,
            schema=resolve_options_endpoint(mod.settings_schema),
            values=current_values,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Preferences-Routen (Spaltenbreiten etc.)
# ─────────────────────────────────────────────────────────────────────────────

def _register_preferences_routes(app: Flask) -> None:

    @app.route("/ui/preferences/col-widths/<module_key>", methods=["GET", "POST"])
    def preferences_col_widths(module_key: str):
        key = f"ui.col_widths.{module_key}"
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            import json
            settings_set(key, json.dumps(data.get("widths", {})))
            return jsonify({"ok": True})
        return jsonify({"widths": __import__("json").loads(settings_get(key, "{}"))})

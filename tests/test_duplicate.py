"""Test: Duplikat-Erkennung beim Anlegen eines Pakets."""
import sys
import os
import tempfile

# Pfade einrichten
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from astrapi.core.system.paths import configure as _configure_paths
_configure_paths("astrapi-packages")

import pytest
from astrapi.core.system.db import configure as _configure_db, create_all_registered_tables


@pytest.fixture()
def app(tmp_path):
    """Minimale Flask-App mit In-Memory-DB."""
    _configure_db(str(tmp_path / "test.db"))
    create_all_registered_tables()

    from astrapi.core.ui.settings_registry import init as settings_init
    settings_init(tmp_path)

    # Store zurücksetzen
    from astrapi_packages.modules.pakete.storage import store
    # Blueprint holen
    from astrapi_packages.modules.pakete.ui import bp

    from flask import Flask
    from jinja2 import ChoiceLoader, FileSystemLoader
    from pathlib import Path

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False

    # Template-Loader
    core_tpl  = Path(__file__).parent.parent / ".venv/lib/python3.14/site-packages/astrapi/core/ui/templates"
    mod_tpl   = Path(__file__).parent.parent / "astrapi_packages/modules/pakete/templates"
    from jinja2 import PrefixLoader
    flask_app.jinja_env.loader = ChoiceLoader([
        PrefixLoader({"pakete": FileSystemLoader(str(mod_tpl))}),
        FileSystemLoader(str(mod_tpl)),
        FileSystemLoader(str(core_tpl)),
    ])

    # Dummy-Globals die Templates brauchen
    @flask_app.context_processor
    def _globals():
        import json
        def ui_stub(*a, **kw): return ""
        return {
            "module_has_settings": lambda k: False,
            "module_label":        lambda k: k,
            "module_card_actions": lambda k: [],
            "col_widths":          lambda k: "{}",
            "last_run_status":     lambda m, i: None,
            "nav_items":           [],
        }

    flask_app.register_blueprint(bp)
    return flask_app, store


def test_duplicate_returns_hx_trigger(app):
    flask_app, store = app

    # Erstes Paket anlegen
    store.create("test-pkg", {"source_url": "https://aur.archlinux.org/test-pkg.git",
                               "enabled": True})

    with flask_app.test_client() as c:
        resp = c.post("/ui/pakete/", data={
            "pkg_name":   "test-pkg",
            "source_url": "https://aur.archlinux.org/test-pkg.git",
            "pkg_type":   "package",
        })

    print("Status:", resp.status_code)
    print("HX-Reswap:", resp.headers.get("HX-Reswap"))
    print("HX-Trigger:", resp.headers.get("HX-Trigger"))
    print("Body:", resp.data[:200])

    assert resp.status_code == 200
    assert resp.headers.get("HX-Reswap") == "none", "HX-Reswap sollte 'none' sein"
    assert "paketeModalError" in (resp.headers.get("HX-Trigger") or ""), \
        "HX-Trigger sollte paketeModalError enthalten"

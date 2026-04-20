"""Test: Duplikat-Erkennung beim Anlegen eines Pakets."""
import sys
import os
import tempfile

# Pfade einrichten
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from astrapi_core.system.paths import configure as _configure_paths
_configure_paths("astrapi-packages")

import pytest
from astrapi_core.system.db import configure as _configure_db, create_all_registered_tables
from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


@pytest.fixture()
def app(tmp_path):
    """Minimale FastAPI-App mit In-Memory-DB."""
    _configure_db(str(tmp_path / "test.db"))
    create_all_registered_tables()

    from astrapi_core.ui.settings_registry import init as settings_init
    settings_init(tmp_path)

    from astrapi_packages.modules.pakete.ui import router
    from astrapi_core.ui.fastapi_templates import configure as configure_templates
    from jinja2 import ChoiceLoader, FileSystemLoader, Environment, PrefixLoader
    from starlette.templating import Jinja2Templates
    from pathlib import Path
    from astrapi_core.ui.render import configure as configure_render

    core_tpl = Path(__file__).parent.parent / ".venv/lib/python3.14/site-packages/astrapi_core/ui/templates"
    mod_tpl  = Path(__file__).parent.parent / "astrapi_packages/modules/pakete/templates"

    jinja_env = Environment(
        loader=ChoiceLoader([
            PrefixLoader({"pakete": FileSystemLoader(str(mod_tpl))}),
            FileSystemLoader(str(mod_tpl)),
            FileSystemLoader(str(core_tpl)),
        ]),
        autoescape=True,
    )
    templates = Jinja2Templates(env=jinja_env)
    configure_templates(templates)

    # Globaler Context (Stub)
    def _ctx():
        return {
            "module_has_settings": lambda k: False,
            "module_label":        lambda k: k,
            "module_card_actions": lambda k: [],
            "col_widths":          lambda k: "{}",
            "last_run_status":     lambda m, i: None,
            "nav_items":           [],
        }
    configure_render(_ctx)

    api = FastAPI()
    api.include_router(router)

    from astrapi_packages.modules.pakete.storage import store
    return api, store


def test_duplicate_returns_hx_trigger(app):
    api, store = app

    # Erstes Paket anlegen
    store.create("test-pkg", {"source_url": "https://aur.archlinux.org/test-pkg.git",
                               "enabled": True})

    client = TestClient(api)
    resp = client.post("/ui/pakete/", data={
        "pkg_name":   "test-pkg",
        "source_url": "https://aur.archlinux.org/test-pkg.git",
        "pkg_type":   "package",
    })

    print("Status:", resp.status_code)
    print("HX-Reswap:", resp.headers.get("HX-Reswap"))
    print("HX-Trigger:", resp.headers.get("HX-Trigger"))
    print("Body:", resp.text[:200])

    assert resp.status_code == 200
    assert resp.headers.get("HX-Reswap") == "none", "HX-Reswap sollte 'none' sein"
    assert "paketeModalError" in (resp.headers.get("HX-Trigger") or ""), \
        "HX-Trigger sollte paketeModalError enthalten"

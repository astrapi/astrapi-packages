from pathlib import Path
from typing import Optional

from astrapi_core.ui.controls import ContentTable, Header
from astrapi_core.ui.crud_router import make_crud_router
from astrapi_core.ui.module_loader import load_modul
from pydantic import BaseModel

from .storage import BuilderImageStore

_KEY = Path(__file__).parent.name
KEY = _KEY
_DIR = Path(__file__).parent

# ── Store ─────────────────────────────────────────────────────────────────────
# Seit Etappe 2 (siehe projects/packages/planung-datei-editor.md) ersetzt die
# DB-gestuetzte BuilderImageStore die vormals statische images.yaml. Bewusst
# ohne automatische Migration -- die Tabelle startet leer, bisherige
# Dockerfile-Inhalte liegen als Referenz unter examples/builders/.

store = BuilderImageStore()

# ── Helper ────────────────────────────────────────────────────────────────────


def images_for_module(module: str) -> list[dict]:
    """Für Dropdowns: registrierte Images eines Fach-Moduls (debian/archlinux)."""
    return [
        {"value": f"ctl/{img_id}:{cfg['tag']}", "label": img_id}
        for img_id, cfg in store.list().items()
        if cfg.get("module") == module
    ]


# ── Dynamische Dropdown-Optionen für options_endpoint (settings.yaml) ────────

from astrapi_core.ui.field_resolver import (  # noqa: E402
    register_options_fetcher as _register_options_fetcher,
)


def _images_options_fetcher(endpoint: str) -> list:
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(endpoint).query)
    module = qs.get("module", [None])[0]
    return images_for_module(module) if module else []


_register_options_fetcher("/api/builder/images/for-select", _images_options_fetcher)


from .ui import router as ui_router  # noqa: E402 – ui/ package

# ── Pydantic-Modell + JSON-CRUD-Router ────────────────────────────────────────


class ItemIn(BaseModel):
    tag: Optional[str] = "latest"
    module: Optional[str] = ""


router = make_crud_router(store, KEY, ItemIn)

_ui_content = ContentTable(
    has_create=True,
    has_edit=True,
    has_delete=True,
    has_toggle=False,
    last_run_label="Letzter Build",
)

module = load_modul(
    _DIR,
    _KEY,
    router,
    ui_router,
    ui_header=Header(
        [
            Header.link_button("Alle exportieren", href=f"/ui/{_KEY}/export"),
            Header.action_button(
                "Importieren",
                hx_get=f"/ui/{_KEY}/import-dialog",
                hx_target="body",
            ),
            Header.action_button(
                "Neu",
                hx_get=f"/ui/{_KEY}/create",
                hx_target="body",
            ),
        ]
    ),
    ui_content=_ui_content,
)

# Config-Loader registrieren
from astrapi_packages.api.run import register_config_loader  # noqa: E402

register_config_loader(_KEY, store.list)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    from .jobs import build_image

    register_action(
        f"{_KEY}.build_arch_builder",
        "arch-builder: Aktualisieren",
        lambda: build_image("arch-builder"),
        source=_KEY,
        source_label="Builder",
    )
    register_action(
        f"{_KEY}.build_debian_builder",
        "debian-builder: Aktualisieren",
        lambda: build_image("debian-builder"),
        source=_KEY,
        source_label="Builder",
    )
except Exception:
    pass

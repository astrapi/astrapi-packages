from pathlib import Path
from typing import Optional

from astrapi_core.ui.crud_router import make_crud_router
from astrapi_core.ui.module_loader import load_modul
from pydantic import BaseModel

from .storage import ArchlinuxPackageStore

_KEY = Path(__file__).parent.name
KEY = _KEY

# ── Store ─────────────────────────────────────────────────────────────────────

store = ArchlinuxPackageStore()

# ── Pydantic-Modell für JSON-API ──────────────────────────────────────────────


class ItemIn(BaseModel):
    name: Optional[str] = ""
    source_url: Optional[str] = ""
    aur_deps: Optional[str] = ""
    pkg_type: Optional[str] = "package"
    enabled: bool = True


# ── JSON-CRUD-Router ──────────────────────────────────────────────────────────

from .jobs import delete_package  # noqa: E402

router = make_crud_router(store, KEY, ItemIn, on_delete=delete_package)

from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402

from .ui import router as ui_router  # noqa: E402  # ui/ package

_ui_content = ContentTable(
    columns=[
        Col.version_badge("last_version", "Version"),
        Col.text("pkg_type_label", "Typ", css="col-type"),
        Col.text("source_type_label", "Quelle", css="col-type"),
        Col.badge_enum(
            "orphaned_label",
            "",
            {"verwaist": {"label": "verwaist", "cls": "badge-status-warn"}},
            css="col-type",
        ),
    ],
    last_run_label="Letzter Build",
)

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_content=_ui_content,
    ui_header=Header(
        [
            Header.action_button(
                "Auf Updates prüfen",
                hx_post=f"/ui/{_KEY}/check-updates",
                hx_target="#main-content",
                hx_swap="innerHTML",
                style="ghost",
            ),
            Header.action_button(
                "Neu",
                hx_get=f"/ui/{_KEY}/create",
                hx_target="body",
            ),
        ]
    ),
)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    from .jobs import mark_orphan_deps, update_all_packages

    register_action(
        f"{_KEY}.update_all",
        "Arch Linux: Aktualisieren",
        update_all_packages,
        source=_KEY,
        source_label="Arch Linux",
    )
    register_action(
        f"{_KEY}.mark_orphans",
        "Arch Linux: Verwaiste markieren",
        mark_orphan_deps,
        source=_KEY,
        source_label="Arch Linux",
    )
except Exception:
    pass

# ── Config-Loader für den zentralen Run-Router ───────────────────────────────
# Ohne das faellt api/run.py's load_config() auf storage.store zurueck, das es
# hier nicht gibt (store lebt in __init__.py) - die Zeile nach manuellem Start
# wurde dadurch mit komplett leeren Daten gerendert (T-157-PACKAGES).

from astrapi_packages.api.run import register_config_loader  # noqa: E402

register_config_loader(KEY, store.list)

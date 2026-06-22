"""astrapi_packages.modules.debian – Debian-Paket-Verwaltung."""

from pathlib import Path
from typing import Optional

from astrapi_core.ui.crud_router import make_crud_router
from astrapi_core.ui.module_loader import load_modul
from pydantic import BaseModel

from .storage import DebianPackageStore

_KEY = Path(__file__).parent.name
KEY = _KEY

# ── Store ─────────────────────────────────────────────────────────────────────

store = DebianPackageStore()

# ── Pydantic-Modell für JSON-API ──────────────────────────────────────────────


class ItemIn(BaseModel):
    name: Optional[str] = ""
    source_url: Optional[str] = ""
    distribution: Optional[str] = "bookworm"
    component: Optional[str] = "main"
    pkg_type: Optional[str] = "package"
    enabled: bool = True


# ── JSON-CRUD-Router ──────────────────────────────────────────────────────────

from .jobs import delete_package  # noqa: E402

router = make_crud_router(store, KEY, ItemIn, on_delete=delete_package)

from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402

from .ui import router as ui_router  # noqa: E402

_ui_content = ContentTable(
    columns=[
        Col.version_badge("last_version", "Version"),
        Col.text("pkg_type_label", "Typ", css="col-type"),
        Col.text("source_type_label", "Quelle", css="col-type"),
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
                style="primary",
            ),
        ]
    ),
)

# ── Scheduler-Aktionen ────────────────────────────────────────────────────────

try:
    from astrapi_core.modules.scheduler.engine import register_action

    from .jobs import update_all_packages

    register_action(
        f"{KEY}.update_all",
        "Debian: Aktualisieren",
        update_all_packages,
        source=KEY,
        source_label="Debian",
    )
except Exception:
    pass

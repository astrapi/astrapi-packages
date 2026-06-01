"""astrapi_packages.modules.debian – Debian-Paket-Verwaltung."""

from pathlib import Path
from typing import Optional

from astrapi_core.ui.crud_router import make_crud_router
from astrapi_core.ui.module_loader import load_modul
from astrapi_core.ui.storage import YamlStorage
from pydantic import BaseModel

_KEY = Path(__file__).parent.name
KEY = _KEY

# ── Store ─────────────────────────────────────────────────────────────────────

store = YamlStorage(KEY)

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

from astrapi_core.ui.controls import Header  # noqa: E402

from .ui import router as ui_router  # noqa: E402

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header(
        [
            Header.action_button(
                "Alle bauen",
                hx_post=f"/ui/{_KEY}/build-all",
                hx_target=f"#mod-{_KEY}",
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
        f"{KEY}.build_all",
        "Debian: Alle Pakete bauen",
        update_all_packages,
    )
except Exception:
    pass

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
    aur_deps: Optional[str] = ""
    pkg_type: Optional[str] = "package"
    enabled: bool = True


# ── JSON-CRUD-Router ──────────────────────────────────────────────────────────

from .jobs import delete_package  # noqa: E402

router = make_crud_router(store, KEY, ItemIn, on_delete=delete_package)

from astrapi_core.ui.controls import Header

from .ui import router as ui_router  # noqa: E402  # ui/ package

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header(
        [
            Header.action_button(
                "Updates prüfen",
                hx_post=f"/ui/{_KEY}/check-updates",
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

try:
    from astrapi_core.modules.scheduler.engine import register_action

    from .jobs import mark_orphan_deps, update_all_packages

    register_action(
        f"{_KEY}.update_all",
        "Pakete: Aktualisieren",
        update_all_packages,
        source=_KEY,
        source_label="Pakete",
    )
    register_action(
        f"{_KEY}.mark_orphans",
        "Pakete: Verwaiste markieren",
        mark_orphan_deps,
        source=_KEY,
        source_label="Pakete",
    )
except Exception:
    pass

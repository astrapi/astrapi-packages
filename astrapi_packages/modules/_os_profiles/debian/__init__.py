"""astrapi_packages.modules._os_profiles.debian – Debian-Paket-Verwaltung."""

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
            Header.action_button(
                "Neu (PKGBUILD)",
                hx_get=f"/ui/{_KEY}/new-in-db",
                hx_target="body",
                style="ghost",
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

# ── Config-Loader für den zentralen Run-Router ───────────────────────────────
# Ohne das faellt api/run.py's load_config() auf storage.store zurueck, das es
# hier nicht gibt (store lebt in __init__.py) - die Zeile nach manuellem Start
# wurde dadurch mit komplett leeren Daten gerendert (T-157-PACKAGES).

from astrapi_packages.api.run import register_config_loader  # noqa: E402

register_config_loader(KEY, store.list)

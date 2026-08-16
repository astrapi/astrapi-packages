"""astrapi_packages.modules.packages – generisches Pakete-Modul.

Ersetzt die vormaligen astrapi_packages.modules.debian/archlinux (siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul"): ein
Nav-Eintrag statt zweien, Filter nach os_type statt getrennter Module. Ein
neuer OS-Typ (astrapi_packages.modules.os_types) erscheint hier automatisch
im Filter, ohne Code-Änderung.
"""

from pathlib import Path
from typing import Optional

from astrapi_core.ui.crud_router import make_crud_router
from astrapi_core.ui.module_loader import load_modul
from pydantic import BaseModel

from .storage import PackageStore

_KEY = Path(__file__).parent.name
KEY = _KEY

store = PackageStore()


class ItemIn(BaseModel):
    name: Optional[str] = ""
    os_type: Optional[str] = ""
    source_url: Optional[str] = ""
    source_subdir: Optional[str] = ""
    depends: Optional[str] = ""
    image: Optional[str] = ""
    pkg_type: Optional[str] = "package"
    enabled: bool = True


from .jobs import delete_package  # noqa: E402

router = make_crud_router(store, KEY, ItemIn, on_delete=delete_package)

from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402

from .ui import router as ui_router  # noqa: E402


def _os_type_options() -> list[dict]:
    from astrapi_packages.modules.os_types import store as os_types_store

    return [{"value": k, "label": v.get("label") or k} for k, v in os_types_store.list().items()]


_ui_content = ContentTable(
    columns=[
        Col.text("os_type", "OS-Typ", css="col-type"),
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
            Header.filter_select(
                "os_type",
                options_fn=_os_type_options,
                all_label="Alle OS",
            ),
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
                style="primary",
                icon="plus",
            ),
            Header.action_button(
                "Neu (PKGBUILD)",
                hx_get=f"/ui/{_KEY}/new-in-db",
                hx_target="body",
                style="ghost",
                icon="plus",
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

# ── Config-Loader für den zentralen Run-Router ───────────────────────────────

from astrapi_packages.api.run import register_config_loader  # noqa: E402

register_config_loader(KEY, store.list)

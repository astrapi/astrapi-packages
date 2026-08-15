"""astrapi_packages.modules.os_types – OS-Typen als Daten statt Code.

Ersetzt das kurzlebige packages_config-Modul (zwei Ja/Nein-Schalter für
debian/archlinux) durch echtes CRUD: jeder OS-Typ (Schlüssel frei wählbar)
steuert per Daten, wie das packages-Modul für ihn baut/veröffentlicht (siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul").
"""

from pathlib import Path
from typing import Optional

from astrapi_core.ui.controls import Col, ContentTable, Header
from astrapi_core.ui.crud_router import make_crud_router
from astrapi_core.ui.module_loader import load_modul
from pydantic import BaseModel

from .storage import OsTypeStore

_KEY = Path(__file__).parent.name
KEY = _KEY

store = OsTypeStore()


class ItemIn(BaseModel):
    label: Optional[str] = ""
    repo_subdir: Optional[str] = ""
    depends_url_template: Optional[str] = ""
    gnupg_home: Optional[str] = ""
    gpg_key_id: Optional[str] = ""


router = make_crud_router(store, KEY, ItemIn)

from .ui import router as ui_router  # noqa: E402

_ui_content = ContentTable(
    columns=[
        Col.text("label", "Anzeigename"),
        Col.mono("repo_subdir", "Repo-Unterordner"),
        Col.mono("depends_url_template", "Abhängigkeiten-URL-Vorlage"),
    ],
    has_run_buttons=False,
    has_status=False,
    has_toggle=False,
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
                "Neu",
                hx_get=f"/ui/{_KEY}/create",
                hx_target="body",
            ),
        ]
    ),
)
# In den Einstellungen eingebettet statt eigener Nav-Eintrag, siehe
# projects/core/planung-os-types-settings-embed.md
module.hidden = True
module.settings_embed = True

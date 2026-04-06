from pathlib import Path
from astrapi.core.ui.module_loader import load_modul
from .api import router
from .ui import router as ui_router

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, ui_router)

try:
    from astrapi.core.modules.scheduler.engine import register_action
    from .jobs import update_all_packages, mark_orphan_deps
    register_action(f"{_KEY}.update_all", "Pakete: Aktualisieren",
                    update_all_packages, source=_KEY, source_label="Pakete")
    register_action(f"{_KEY}.mark_orphans", "Pakete: Verwaiste markieren",
                    mark_orphan_deps, source=_KEY, source_label="Pakete")
except Exception:
    pass

from pathlib import Path
from astrapi_core.ui.module_loader import load_modul
from .api import router
from .ui import router as ui_router

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, ui_router)

try:
    from astrapi_core.modules.scheduler.engine import register_action
    from .jobs import build_image
    register_action(f"{_KEY}.build_arch_builder", "arch-builder: Aktualisieren",
                    lambda: build_image("arch-builder"), source=_KEY, source_label="Docker")
except Exception:
    pass

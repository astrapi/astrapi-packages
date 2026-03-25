from pathlib import Path
from core.ui.module_loader import load_modul
from .api import router
from .ui import bp

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, bp)

try:
    from core.modules.scheduler.engine import register_action
    from .jobs import build_package
    register_action(f"{_KEY}.build", "Pakete: Paket bauen", build_package, source=_KEY, source_label="Pakete")
except Exception:
    pass

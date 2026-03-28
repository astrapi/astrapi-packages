from pathlib import Path
from astrapi.core.ui.module_loader import load_modul
from .api import router
from .ui import bp

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, bp)

try:
    from astrapi.core.modules.scheduler.engine import register_action
    from .jobs import build_image
    register_action(f"{_KEY}.build", "Docker: Image bauen", build_image, source=_KEY, source_label="Docker")
except Exception:
    pass

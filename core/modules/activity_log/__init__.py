from pathlib import Path
from core.ui.module_loader import load_modul
from .api import router
from .ui import bp

module = load_modul(Path(__file__).parent, "activity_log", router, bp)

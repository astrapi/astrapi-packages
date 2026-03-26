"""core/modules/sysinfo/__init__.py – System-Informationen Modul."""

from astrapi.core.ui import Module
from .api import router
from .ui import bp

module = Module(
    key          = "sysinfo",
    label        = "System",
    icon         = "monitor",
    api_router   = router,
    ui_blueprint = bp,
    nav_group    = "System",
)

"""core/modules/settings/__init__.py – Framework-Einstellungen Modul."""

from astrapi.core.ui import Module
from .ui import bp

module = Module(
    key          = "settings",
    label        = "Einstellungen",
    icon         = "settings",
    nav_group    = "System",
    ui_blueprint = bp,
)

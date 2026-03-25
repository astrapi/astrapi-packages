"""
core/ui/_base.py  –  Modul-Basisklasse des Astrapi-Frameworks

Jedes Modul erstellt eine Module-Instanz und exportiert sie als `module`:

    from core.ui import Module

    module = Module(
        key          = "mein_modul",
        label        = "Mein Modul",
        icon         = "box",
        api_router   = router,
        ui_blueprint = bp,
    )

Das Framework (core/ui/module_registry.py) lädt alle Module automatisch
aus core/modules/, app/modules/ und app/overrides/ und registriert sie.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter
    from flask import Blueprint


@dataclass
class Module:
    """Registrierungs-Descriptor für ein Astrapi-Modul.

    Pflichtfelder:
        key     – eindeutiger Bezeichner, wird als URL-Segment genutzt
        label   – Anzeigename in der Navigation
        icon    – Icon-Name (siehe core/templates/navigation/index.html)

    Optionale Felder:
        api_router        – FastAPI-Router für /api/<key>/...
        ui_blueprint      – Flask-Blueprint für UI-Routen (/ui/<key>/...)
        nav_url           – URL für hx-push-url (sichtbare Browser-URL, default: /<key>)
        nav_default       – ob dieser Eintrag die Startseite ist
        nav_group         – Gruppenbezeichnung in der Navigation
        settings_defaults – Default-Werte für Modul-Einstellungen
        settings_schema   – Felder-Schema aus settings.yaml
        card_actions      – Liste modul-eigener Card-Footer-Buttons (aus modul.yaml)
        module_root       – Pfad zum Modul-Verzeichnis (wird automatisch gesetzt)
    """

    key:   str
    label: str
    icon:  str = "list"

    api_router:   Optional[object] = field(default=None, repr=False)
    ui_blueprint: Optional[object] = field(default=None, repr=False)

    nav_url:     Optional[str]  = None
    nav_default: bool           = False
    nav_group:   Optional[str]  = None

    settings_defaults:     dict          = field(default_factory=dict)
    settings_schema:       list          = field(default_factory=list)
    settings_modal_width:  int           = 480
    card_actions:          list          = field(default_factory=list)

    module_root: Optional[Path] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.nav_url is None:
            self.nav_url = f"/{self.key}"

    def to_nav_item(self) -> dict:
        """Gibt den Nav-Item-Dict zurück (kompatibel mit navigation.py)."""
        return {
            "key":       self.key,
            "label":     self.label,
            "url":       self.nav_url,
            "icon":      self.icon or "box",
            "default":   self.nav_default,
            "separator": False,
        }

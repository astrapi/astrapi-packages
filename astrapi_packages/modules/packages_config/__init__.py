"""astrapi_packages.modules.packages_config – Auswahl der aktiven OS-Profile.

Reines Einstellungs-Modul (kein Content, keine eigenen Routen): steuert per
Settings-Karte (siehe /ui/settings), welche OS-Profile aus
astrapi_packages.modules._os_profiles beim Start geladen werden. Die
eigentliche Auswertung passiert in astrapi_packages._app.create_app().
"""

from pathlib import Path

from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

module = load_modul(Path(__file__).parent, _KEY, None, None)

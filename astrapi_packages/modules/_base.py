"""
app/modules/_base.py  –  Rückwärtskompatibilitäts-Shim

Die Klasse wurde nach core/ui/_base.py verschoben und in Module umbenannt.
Dieser Import bleibt für externe App-Code erhalten.
"""

from astrapi.core.ui._base import Module as AstrapiModule  # noqa: F401

__all__ = ["AstrapiModule"]

from __future__ import annotations

from typing import TYPE_CHECKING

from .app import create
from ._base import Module

if TYPE_CHECKING:
    # Nur für Typ-Checker sichtbar – kein Laufzeit-Import
    from ._base import Module as Module  # noqa: F811

__all__ = ["create", "Module"]

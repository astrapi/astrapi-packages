# core/modules/notify/schema.py
"""Pydantic-Modelle und Metadaten für Benachrichtigungen.

Architektur:
  Kanal  – Backend-Konfiguration (Server, Zugangsdaten)
  Job    – Benachrichtigungs-Regel (Kanal + Ereignisse + Quellen)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Ereignistypen ──────────────────────────────────────────────────────────────
# Tuple: (key, label, farbe)
ALL_EVENTS: list[tuple[str, str, str]] = [
    ("error",   "Fehler",     "#f87171"),
    ("warning", "Warnungen",  "#fbbf24"),
    ("success", "Erfolge",    "#4ade80"),
    ("info",    "Info",       "#60a5fa"),
]

EVENT_COLORS: dict[str, str] = {k: c for k, _, c in ALL_EVENTS}
EVENT_LABELS: dict[str, str] = {k: l for k, l, _ in ALL_EVENTS}


# ── Pydantic-Modelle ───────────────────────────────────────────────────────────

class ChannelIn(BaseModel):
    """Backend-Konfiguration eines Benachrichtigungskanals (Server, Zugangsdaten)."""

    label:      str  = ""
    backend:    str  = "ntfy"
    enabled:    bool = True

    # ntfy-spezifische Felder
    ntfy_url:        str  = "https://ntfy.sh"
    ntfy_topic:      str  = ""
    ntfy_token:      str  = ""
    ntfy_verify_ssl: bool = True

    # E-Mail-spezifische Felder
    mail_smtp_host:     str  = ""
    mail_smtp_port:     int  = 587
    mail_smtp_user:     str  = ""
    mail_smtp_password: str  = ""
    mail_smtp_tls:      bool = True
    mail_from:          str  = ""
    mail_to:            str  = ""
    mail_subject_prefix: str = "[Notify]"


class JobIn(BaseModel):
    """Benachrichtigungs-Job: verknüpft einen Kanal mit Ereignissen und Quellen."""

    label:      str       = ""
    channel_id: str       = ""
    enabled:    bool      = True
    events:     list[str] = Field(default_factory=lambda: ["error", "warning"])
    sources:    list[str] = Field(default_factory=list)


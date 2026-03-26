# core/modules/notify/engine.py
"""Benachrichtigungs-Engine - Multi-Channel-Architektur.

Beim Aufruf von send() werden alle passenden aktiven Kanaele benachrichtigt.

Nutzung:
    from astrapi.core.modules.notify import engine as notify
    notify.send("Backup fertig", "web-01 gesichert", event=notify.SUCCESS)
    notify.send("Host down",    "web-01 nicht erreichbar", event=notify.WARNING, source="hosts")

Quelle registrieren (in __init__.py des Moduls):
    from astrapi.core.modules.notify.engine import register_source
    register_source("hosts", "Hosts")

Eigenes Backend registrieren (in main.py, vor App-Start):
    from astrapi.core.modules.notify.engine import register_backend, BaseNotifier

    class TelegramNotifier(BaseNotifier):
        def __init__(self, bot_token, chat_id):
            self.bot_token = bot_token
            self.chat_id   = chat_id
        def send(self, title, message, priority="default", tags=None) -> bool:
            ...

    register_backend(
        "telegram",
        lambda cfg: TelegramNotifier(
            bot_token = cfg.get("tg_token", ""),
            chat_id   = cfg.get("tg_chat_id", ""),
        )
    )
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Optional

from astrapi.core.ui.storage import SqliteStorage

log = logging.getLogger(__name__)

KEY       = "notify"
store     = SqliteStorage("notify_channels")
job_store = SqliteStorage("notify_jobs")

# Ereignis-Konstanten

SUCCESS = "success"
ERROR   = "error"
WARNING = "warning"
INFO    = "info"

_PRIORITY_MAP: dict[str, str] = {
    SUCCESS: "default",
    INFO:    "low",
    WARNING: "high",
    ERROR:   "urgent",
}

_TAG_MAP: dict[str, list[str]] = {
    SUCCESS: ["white_check_mark"],
    INFO:    ["information_source"],
    WARNING: ["warning"],
    ERROR:   ["rotating_light"],
}


class BaseNotifier(ABC):
    """Abstrakte Basisklasse fuer Benachrichtigungs-Backends."""

    @abstractmethod
    def send(
        self,
        title:    str,
        message:  str,
        priority: str       = "default",
        tags:     list[str] = None,
    ) -> bool:
        """Sendet eine Benachrichtigung. Returns True bei Erfolg."""
        ...


class NotifyEngine:
    """Kapselt Backend-Registry und Source-Registry der Benachrichtigungs-Engine.

    Kann mit reset() in den Ausgangszustand zurückversetzt werden
    (nützlich für Test-Isolation).
    """

    def __init__(self):
        # Backend-Registry: key -> factory(channel_dict) -> BaseNotifier
        self._backends: dict[str, Callable[[dict], BaseNotifier]] = {}
        # Source-Registry: key -> label (Anzeigename in der Kanal-UI)
        self._sources: dict[str, str] = {}

    def reset(self) -> None:
        """Setzt den internen Zustand zurück (für Test-Isolation)."""
        self._backends = {}
        self._sources = {}

    # ── Source-Registry ───────────────────────────────────────────────────────

    def register_source(self, key: str, label: str) -> None:
        self._sources[key] = label

    def unregister_source(self, key: str) -> None:
        self._sources.pop(key, None)

    def get_registered_sources(self) -> dict[str, str]:
        return dict(self._sources)

    # ── Backend-Registry ──────────────────────────────────────────────────────

    def register_backend(self, key: str, factory: Callable[[dict], BaseNotifier]) -> None:
        self._backends[key] = factory

    def get_registered_backends(self) -> list[str]:
        return list(self._backends.keys())

    # ── Kanal-CRUD ────────────────────────────────────────────────────────────

    def list_channels(self) -> dict:
        return store.list()

    def get_channel(self, channel_id: str):
        return store.get(channel_id)

    def create_channel(self, channel_id: str, data: dict) -> dict:
        return store.create(channel_id, data)

    def update_channel(self, channel_id: str, data: dict) -> dict:
        return store.update(channel_id, data)

    def toggle_channel(self, channel_id: str) -> bool:
        return store.toggle(channel_id, default=False)

    def delete_channel(self, channel_id: str) -> None:
        store.delete(channel_id)

    # ── Job-CRUD ──────────────────────────────────────────────────────────────

    def list_jobs(self) -> dict:
        return job_store.list()

    def get_job(self, job_id: str):
        return job_store.get(job_id)

    def create_job(self, job_id: str, data: dict) -> dict:
        return job_store.create(job_id, data)

    def update_job(self, job_id: str, data: dict) -> dict:
        return job_store.update(job_id, data)

    def toggle_job(self, job_id: str) -> bool:
        return job_store.toggle(job_id, default=False)

    def delete_job(self, job_id: str) -> None:
        job_store.delete(job_id)

    # ── Senden ────────────────────────────────────────────────────────────────

    def _notifier_for_channel(self, channel: dict) -> Optional[BaseNotifier]:
        """Erstellt den passenden Notifier fuer einen Kanal-Config-Dict."""
        backend_key = channel.get("backend", "ntfy")

        factory = self._backends.get(backend_key)
        if factory is not None:
            try:
                return factory(channel)
            except Exception as e:
                log.error("notify: Factory fuer Backend '%s' fehlgeschlagen: %s", backend_key, e)
                return None

        if backend_key == "ntfy":
            from .backends.ntfy import NtfyNotifier
            return NtfyNotifier(
                url        = channel.get("ntfy_url",   "https://ntfy.sh") or "https://ntfy.sh",
                topic      = channel.get("ntfy_topic", "") or "",
                token      = channel.get("ntfy_token") or None,
                verify_ssl = bool(channel.get("ntfy_verify_ssl", True)),
            )

        if backend_key == "email":
            from .backends.email import EmailNotifier
            return EmailNotifier(
                smtp_host            = channel.get("mail_smtp_host", "localhost") or "localhost",
                smtp_port            = int(channel.get("mail_smtp_port") or 587),
                smtp_user            = channel.get("mail_smtp_user", "") or "",
                smtp_password        = channel.get("mail_smtp_password", "") or "",
                smtp_tls             = bool(channel.get("mail_smtp_tls", True)),
                mail_from            = channel.get("mail_from", "") or "",
                mail_to              = channel.get("mail_to", "") or "",
                mail_subject_prefix  = channel.get("mail_subject_prefix", "[Notify]") or "[Notify]",
            )

        log.warning("notify: Unbekanntes Backend '%s' - Kanal wird uebersprungen", backend_key)
        return None

    def send(
        self,
        title:    str,
        message:  str,
        event:    str           = INFO,
        source:   Optional[str] = None,
        tags:     list[str]     = None,
        priority: Optional[str] = None,
    ) -> int:
        """Sendet ueber alle aktiven Jobs, die zum Ereignistyp und zur Quelle passen."""
        channels = store.list()
        jobs     = job_store.list()

        if not jobs:
            return 0

        eff_priority = priority or _PRIORITY_MAP.get(event, "default")
        eff_tags     = list(tags or []) + _TAG_MAP.get(event, [])
        sent         = 0

        for job_id, job in jobs.items():
            if not job.get("enabled", False):
                continue
            job_events = job.get("events") or []
            if event not in job_events:
                continue
            job_sources = job.get("sources") or []
            if job_sources and source is not None and source not in job_sources:
                continue

            channel_id = job.get("channel_id", "")
            channel    = channels.get(channel_id)
            if channel is None:
                log.warning("notify: Job '%s' verweist auf unbekannten Kanal '%s'", job_id, channel_id)
                continue
            if not channel.get("enabled", False):
                continue

            notifier = self._notifier_for_channel(channel)
            if notifier is None:
                continue

            try:
                ok = notifier.send(title, message, eff_priority, eff_tags)
                if ok:
                    sent += 1
                    log.debug("notify: '%s' via Job '%s' (Kanal '%s') gesendet", title, job_id, channel_id)
                else:
                    log.warning("notify: Job '%s' (Kanal '%s') lieferte Fehler fuer '%s'", job_id, channel_id, title)
            except Exception as e:
                log.error("notify: Job '%s' (Kanal '%s') Fehler beim Senden: %s", job_id, channel_id, e)

        return sent

    def test_channel(self, channel_id: str) -> tuple[bool, str]:
        """Sendet eine Testbenachrichtigung direkt ueber einen bestimmten Kanal."""
        channel = store.get(channel_id)
        if channel is None:
            return False, f"Kanal '{channel_id}' nicht gefunden."

        notifier = self._notifier_for_channel(channel)
        if notifier is None:
            return False, f"Backend '{channel.get('backend', '?')}' nicht verfügbar."

        try:
            ok = notifier.send(
                title    = "Testbenachrichtigung",
                message  = "Benachrichtigungen sind korrekt konfiguriert",
                priority = "default",
                tags     = ["bell"],
            )
            if ok:
                return True, "Testbenachrichtigung erfolgreich gesendet."
            return False, "Backend lieferte einen Fehler (kein HTTP 2xx)."
        except Exception as e:
            return False, str(e)

    def test_job(self, job_id: str) -> tuple[bool, str]:
        """Sendet eine Testbenachrichtigung ueber den Kanal eines bestimmten Jobs."""
        job = job_store.get(job_id)
        if job is None:
            return False, f"Job '{job_id}' nicht gefunden."
        channel_id = job.get("channel_id", "")
        channel    = store.get(channel_id)
        if channel is None:
            return False, f"Kanal '{channel_id}' nicht gefunden (Job '{job_id}')."

        notifier = self._notifier_for_channel(channel)
        if notifier is None:
            return False, f"Backend '{channel.get('backend', '?')}' nicht verfügbar."

        try:
            ok = notifier.send(
                title    = "Testbenachrichtigung",
                message  = f"Job '{job.get('label', job_id)}' ist korrekt konfiguriert",
                priority = "default",
                tags     = ["bell"],
            )
            if ok:
                return True, "Testbenachrichtigung erfolgreich gesendet."
            return False, "Backend lieferte einen Fehler (kein HTTP 2xx)."
        except Exception as e:
            return False, str(e)


# Modul-level Singleton
_engine = NotifyEngine()


def __getattr__(name: str):
    return getattr(_engine, name)


def send_simple(message: str, priority: str | None = None) -> None:
    """Sendet eine Benachrichtigung mit dem App-Namen als Titel (Kurzform)."""
    if not message or not message.strip():
        return
    try:
        from astrapi.core.modules.settings.engine import get_app_name
        _engine.send(
            title    = get_app_name(),
            message  = message,
            event    = INFO,
            source   = "app",
            tags     = ([f"priority:{priority}"] if priority else []),
        )
    except Exception as e:
        log.error("notify: send_simple fehlgeschlagen: %s", e)


# Rückwärtskompatibilität
test = _engine.test_channel

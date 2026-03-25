# core/modules/notify/backends/ntfy.py
"""ntfy-Backend für core.modules.notify.

ntfy ist ein einfacher HTTP-basierter Push-Notification-Dienst.
Selbst hosten oder ntfy.sh nutzen: https://ntfy.sh

Prioritäten (ntfy-Skala):
  min | low | default | high | urgent

Tags: Emoji-Kurzformen wie "white_check_mark", "warning", "rotating_light"
      Siehe https://docs.ntfy.sh/emojis/
"""

from __future__ import annotations

import logging
import ssl
import urllib.error
import urllib.request
from typing import Optional

from ..engine import BaseNotifier

log = logging.getLogger(__name__)


class NtfyNotifier(BaseNotifier):
    """Benachrichtigungs-Backend für ntfy (https://ntfy.sh).

    Sendet Nachrichten per HTTP POST an einen ntfy-Server.
    Verwendet ausschließlich die Python-Standardbibliothek (urllib).

    Eigene ntfy-Instanz:
        NtfyNotifier(url="https://ntfy.meinserver.de", topic="alerts", token="tk_...")

    ntfy.sh (ohne Auth):
        NtfyNotifier(url="https://ntfy.sh", topic="mein-geheimes-thema")
    """

    def __init__(
        self,
        url:        str           = "https://ntfy.sh",
        topic:      str           = "",
        token:      Optional[str] = None,
        verify_ssl: bool          = True,
    ) -> None:
        self.url        = (url or "https://ntfy.sh").rstrip("/")
        self.topic      = (topic or "").strip()
        self.token      = (token or "").strip() or None
        self.verify_ssl = verify_ssl

    def send(
        self,
        title:    str,
        message:  str,
        priority: str       = "default",
        tags:     list[str] = None,
    ) -> bool:
        if not self.topic:
            log.warning("ntfy: Kein Thema (Topic) konfiguriert – Benachrichtigung übersprungen.")
            return False

        endpoint = f"{self.url}/{self.topic}"
        headers: dict[str, str] = {
            "Title":        title,
            "Priority":     priority,
            "Content-Type": "text/plain; charset=utf-8",
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        payload = message.encode("utf-8")

        ssl_ctx = None if self.verify_ssl else ssl.create_default_context()
        if ssl_ctx is not None:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode    = ssl.CERT_NONE

        try:
            req = urllib.request.Request(
                url     = endpoint,
                data    = payload,
                headers = headers,
                method  = "POST",
            )
            with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
                success = 200 <= resp.status < 300
                if not success:
                    log.warning("ntfy: Unerwarteter HTTP-Status %s", resp.status)
                return success

        except urllib.error.HTTPError as e:
            log.error("ntfy HTTP-Fehler %s %s (URL: %s)", e.code, e.reason, endpoint)
            return False
        except urllib.error.URLError as e:
            log.error("ntfy Verbindungsfehler: %s", e.reason)
            return False
        except Exception as e:
            log.error("ntfy unerwarteter Fehler: %s", e)
            return False

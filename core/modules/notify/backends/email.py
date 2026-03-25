# core/modules/notify/backends/email.py
"""E-Mail-Backend für core.modules.notify.

Versendet Benachrichtigungen per SMTP. Unterstützt:
  - SMTP mit STARTTLS (Port 587)
  - SMTP über TLS/SSL (Port 465)
  - Unsichere SMTP-Verbindung (Port 25, nur für lokale Relays)
  - Optionale SMTP-Authentifizierung (Benutzername + Passwort)

Verwendet ausschließlich die Python-Standardbibliothek (smtplib, email).

Beispiele:
    Gmail:
        EmailNotifier(smtp_host="smtp.gmail.com", smtp_port=587,
                      smtp_user="me@gmail.com", smtp_password="app-pw",
                      mail_from="me@gmail.com", mail_to="dest@example.com")

    Lokaler Relay (kein Auth):
        EmailNotifier(smtp_host="localhost", smtp_port=25,
                      smtp_tls=False, mail_from="app@intern", mail_to="ops@intern")
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from ..engine import BaseNotifier

log = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    """Benachrichtigungs-Backend für E-Mail via SMTP."""

    def __init__(
        self,
        smtp_host:     str           = "localhost",
        smtp_port:     int           = 587,
        smtp_user:     str           = "",
        smtp_password: str           = "",
        smtp_tls:      bool          = True,
        mail_from:     str           = "",
        mail_to:       str           = "",
        mail_subject_prefix: str     = "[Notify]",
    ) -> None:
        self.smtp_host     = smtp_host or "localhost"
        self.smtp_port     = int(smtp_port or 587)
        self.smtp_user     = (smtp_user or "").strip()
        self.smtp_password = (smtp_password or "").strip()
        self.smtp_tls      = bool(smtp_tls)
        self.mail_from     = (mail_from or "").strip()
        self.mail_to       = (mail_to or "").strip()
        self.mail_subject_prefix = (mail_subject_prefix or "[Notify]").strip()

    def send(
        self,
        title:    str,
        message:  str,
        priority: str       = "default",
        tags:     list[str] = None,
    ) -> bool:
        if not self.mail_to:
            log.warning("email: Kein Empfänger konfiguriert – Benachrichtigung übersprungen.")
            return False
        if not self.mail_from:
            log.warning("email: Kein Absender konfiguriert – Benachrichtigung übersprungen.")
            return False

        subject = f"{self.mail_subject_prefix} {title}".strip()

        # Einfacher Text-Body; Tags als Zeile voranstellen wenn vorhanden
        body_parts = []
        if tags:
            body_parts.append(f"[{', '.join(tags)}]")
        body_parts.append(message)
        if priority and priority not in ("default", "low"):
            body_parts.append(f"\nPriorität: {priority}")
        body = "\n".join(body_parts)

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"]    = self.mail_from
        msg["To"]      = self.mail_to
        msg.set_content(body)

        try:
            if self.smtp_port == 465:
                # SSL direkt (kein STARTTLS)
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=ctx, timeout=15) as s:
                    if self.smtp_user:
                        s.login(self.smtp_user, self.smtp_password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as s:
                    if self.smtp_tls:
                        ctx = ssl.create_default_context()
                        s.starttls(context=ctx)
                    if self.smtp_user:
                        s.login(self.smtp_user, self.smtp_password)
                    s.send_message(msg)
            log.debug("email: '%s' → %s gesendet", subject, self.mail_to)
            return True

        except smtplib.SMTPAuthenticationError as e:
            log.error("email: Authentifizierungsfehler: %s", e)
        except smtplib.SMTPConnectError as e:
            log.error("email: Verbindung zu %s:%s fehlgeschlagen: %s", self.smtp_host, self.smtp_port, e)
        except smtplib.SMTPException as e:
            log.error("email: SMTP-Fehler: %s", e)
        except OSError as e:
            log.error("email: Netzwerkfehler: %s", e)
        return False

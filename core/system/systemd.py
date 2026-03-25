# core/systemd.py
"""Systemd-Integration: sd_notify und Watchdog-Thread."""
import os
import socket
import threading
import time


def sd_notify(msg: str) -> None:
    """Sendet eine Nachricht an systemd (NOTIFY_SOCKET) falls verfügbar."""
    try:
        sock_path = os.environ.get("NOTIFY_SOCKET", "")
        if not sock_path:
            return
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(sock_path)
            s.sendall(msg.encode())
    except Exception:
        pass


def start_watchdog(interval: int = 20, check_fn=None) -> None:
    """Startet einen Watchdog-Thread für systemd.

    Sendet alle `interval` Sekunden WATCHDOG=1 an systemd.
    Falls check_fn angegeben, wird WATCHDOG=1 nur gesendet wenn check_fn() True zurückgibt.
    WatchdogSec in der Unit sollte mindestens 3× interval betragen (z.B. 60s bei interval=20).
    Tut nichts wenn NOTIFY_SOCKET nicht gesetzt ist.
    """
    if not os.environ.get("NOTIFY_SOCKET"):
        return

    def _ping():
        while True:
            time.sleep(interval)
            try:
                if check_fn is None or check_fn():
                    sd_notify("WATCHDOG=1")
            except Exception:
                pass

    threading.Thread(target=_ping, daemon=True, name="systemd-watchdog").start()

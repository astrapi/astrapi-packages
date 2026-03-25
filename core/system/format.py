# core/system/format.py
"""Gemeinsame Formatierungsfunktionen."""


def fmt_bytes(n: float | None) -> str:
    """Formatiert eine Byte-Anzahl lesbar (B, KB, MB, GB, TB, PB)."""
    if n is None:
        return "—"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

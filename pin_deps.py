#!/usr/bin/env python3
"""
pin_deps.py – Schreibt exakte Versionen aus der aktuellen Umgebung
in pyproject.toml.

Ausführen aus dem astrapi-packages-Verzeichnis:

    python pin_deps.py            # Vorschau + Schreiben
    python pin_deps.py --dry-run  # Nur Vorschau, nichts schreiben

Astrapi-Pakete (astrapi-*) behalten >= (Mindestversion), alle anderen
Dependencies werden auf die exakt installierte Version gepinnt (==).
"""

import re
import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

# Diese Pakete behalten >= statt == (interne Pakete, die separat versioniert werden)
_KEEP_GE_PREFIX = "astrapi-"


def _normalize(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def _installed(package: str) -> str | None:
    try:
        return pkg_version(package)
    except PackageNotFoundError:
        return None


def pin(pyproject_path: Path, *, dry_run: bool = False) -> None:
    text = pyproject_path.read_text(encoding="utf-8")

    with open(pyproject_path, "rb") as f:
        cfg = tomllib.load(f)

    deps: list[str] = cfg.get("project", {}).get("dependencies", [])
    if not deps:
        print("Keine [project].dependencies gefunden.")
        return

    new_text = text
    changed: list[str] = []
    missing: list[str] = []

    for dep in deps:
        # "fastapi>=0.115"  oder  "uvicorn[standard]>=0.30"
        m = re.match(r'^([A-Za-z0-9_\-\.]+)(\[[^\]]+\])?(.*)', dep.strip())
        if not m:
            continue

        pkg   = m.group(1)          # z.B. "fastapi"
        extra = m.group(2) or ""    # z.B. "[standard]"  oder ""
        spec  = m.group(3)          # z.B. ">=0.115"

        ver = _installed(pkg)
        if ver is None:
            missing.append(f"  ! {pkg}: nicht in dieser Umgebung installiert")
            continue

        keep_ge = pkg.lower().startswith(_KEEP_GE_PREFIX)
        new_spec = f">={ver}" if keep_ge else f"=={ver}"

        if spec == new_spec:
            continue  # bereits korrekt

        old_entry = f'"{pkg}{extra}{spec}"'
        new_entry = f'"{pkg}{extra}{new_spec}"'

        if old_entry not in new_text:
            missing.append(f"  ! {pkg}: Eintrag '{old_entry}' nicht gefunden (manuell prüfen)")
            continue

        new_text = new_text.replace(old_entry, new_entry, 1)
        changed.append(f"  {pkg}{extra}:  {spec or '(ohne)'} → {new_spec}")

    if not changed and not missing:
        print("Alles bereits auf dem aktuellen Stand.")
        return

    if changed:
        print("Änderungen:")
        for line in changed:
            print(line)

    if missing:
        print("\nHinweise:")
        for line in missing:
            print(line)

    if dry_run:
        print("\n[dry-run] Datei wurde NICHT geschrieben.")
        return

    pyproject_path.write_text(new_text, encoding="utf-8")
    print(f"\n✓ {pyproject_path.name} aktualisiert.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    pyproject = Path(__file__).parent / "pyproject.toml"

    if not pyproject.exists():
        sys.exit(f"Fehler: {pyproject} nicht gefunden.")

    pin(pyproject, dry_run=dry_run)

"""astrapi_packages.utils.git_import – einmaliger Import eines Pakets aus
einem Git-Repo in die DB-Verwaltung (file_store), siehe
projects/packages/planung-datei-editor.md, Etappe 3/1.2.

Gezielt pro Paket auslösbar, kein automatischer Massenimport des ganzen
Bestands. Das Git-Repo bleibt danach unangetastet liegen -- nur eine
Momentaufnahme wandert in die DB.
"""

import subprocess
import tempfile
from pathlib import Path

from astrapi_packages.utils import file_store


class GitImportError(Exception):
    pass


def import_package_from_git(
    owner_type: str, item_id: str, source_url: str, source_subdir: str
) -> None:
    """Klont source_url flach, uebernimmt alle Dateien aus dem Paket-Unter-
    verzeichnis (source_subdir oder item_id) per file_store.save().

    Setzt source_type auf dem Store-Eintrag NICHT selbst -- das macht der
    Aufrufer (Route), da diese Funktion den owner_type-spezifischen Store
    nicht kennt.
    """
    if not source_url:
        raise GitImportError("Keine Git-URL hinterlegt.")

    subdir = source_subdir or item_id

    with tempfile.TemporaryDirectory(prefix="astrapi-git-import-") as tmp:
        result = subprocess.run(
            ["git", "clone", "--depth=1", source_url, tmp],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise GitImportError(f"git clone fehlgeschlagen: {result.stderr.strip()[-500:]}")

        src_dir = Path(tmp) / subdir
        if not (src_dir / "PKGBUILD").exists():
            raise GitImportError(f"Keine PKGBUILD in '{subdir}' gefunden.")

        imported = 0
        for entry in sorted(src_dir.iterdir()):
            if not entry.is_file():
                continue
            content = entry.read_text(encoding="utf-8", errors="replace")
            file_store.save(owner_type, item_id, entry.name, content, message="Import aus Git-Repo")
            imported += 1

        if imported == 0:
            raise GitImportError(f"Keine Dateien in '{subdir}' gefunden.")

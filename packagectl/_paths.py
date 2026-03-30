# packagectl/_paths.py
from pathlib import Path

from astrapi.core.system.paths import work_dir, db_path, log_dir  # noqa: F401 – re-export


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent


def repo_dir() -> Path:
    """Lokales Pacman-Repository im Arbeitsverzeichnis."""
    return work_dir() / "repo"

# astrapi_packages/_paths.py
from pathlib import Path

from astrapi_core.system.paths import work_dir, db_path, log_dir  # noqa: F401 – re-export


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent


def debian_repo_dir() -> Path:
    """Wurzelverzeichnis des lokalen Debian-Repos. Zusatzspeicher ist
    Pflicht (kein stiller Rückfall aufs Arbeitsverzeichnis) -- ein
    Paket-Repo ist um Größenordnungen zu groß für die Root-Partition."""
    from astrapi_core.system.paths import require_extra_disk

    return Path(require_extra_disk()).resolve() / "debian"


def arch_repo_dir() -> Path:
    """Wurzelverzeichnis des lokalen Arch-Repos. Zusatzspeicher ist
    Pflicht, siehe debian_repo_dir()."""
    from astrapi_core.system.paths import require_extra_disk

    return Path(require_extra_disk()).resolve() / "arch"

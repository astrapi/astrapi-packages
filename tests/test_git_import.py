"""Tests fuer astrapi_packages.utils.git_import (Etappe 3).

Nutzt ein lokales Git-Repo (file://) statt eines echten Netzwerkzugriffs.
"""

import subprocess

import pytest

from astrapi_packages.utils.git_import import GitImportError, import_package_from_git


@pytest.fixture
def fresh_db(tmp_path):
    from astrapi_core.system import db as core_db

    from astrapi_packages.utils import file_store

    core_db._local.conn = None
    core_db.configure(tmp_path / "test.db")
    file_store._table_ready = False
    yield
    core_db._local.conn = None


@pytest.fixture
def git_repo(tmp_path):
    """Lokales Git-Repo mit einem Paket-Unterordner (PKGBUILD + Zusatzdatei)."""
    repo = tmp_path / "packages_debian.git_checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)

    pkg_dir = repo / "homepage"
    pkg_dir.mkdir()
    (pkg_dir / "PKGBUILD").write_text("pkgname=homepage\npkgver=1.13.2\npkgrel=2\n")
    (pkg_dir / "homepage.service").write_text("[Unit]\nDescription=homepage\n")

    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    return repo


def test_import_uebernimmt_alle_dateien(fresh_db, git_repo):
    from astrapi_packages.utils import file_store

    import_package_from_git("debian", "homepage", f"file://{git_repo}", "homepage")

    files = {f["filename"]: f["content"] for f in file_store.list_files("debian", "homepage")}
    assert set(files) == {"PKGBUILD", "homepage.service"}
    assert "pkgver=1.13.2" in files["PKGBUILD"]


def test_import_ohne_source_url_wirft(fresh_db):
    with pytest.raises(GitImportError):
        import_package_from_git("debian", "homepage", "", "homepage")


def test_import_fehlende_pkgbuild_wirft(fresh_db, tmp_path):
    empty_repo = tmp_path / "leer.git_checkout"
    empty_repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=empty_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=empty_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=empty_repo, check=True)
    (empty_repo / "README.md").write_text("nichts hier")
    subprocess.run(["git", "add", "."], cwd=empty_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=empty_repo, check=True)

    with pytest.raises(GitImportError):
        import_package_from_git("debian", "irgendwas", f"file://{empty_repo}", "irgendwas")

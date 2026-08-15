"""Tests fuer _build_cmd() in astrapi_packages.modules.debian.jobs (Etappe 3).

Deckt beide Build-Pfade ab: der bestehende git-Clone-Pfad (source_type='git',
Default, AUR/externe Altfaelle) muss unveraendert funktionieren, der neue
Bind-Mount-Pfad (source_type='db') darf keinen git clone mehr enthalten.
"""

from pathlib import Path

from astrapi_packages.modules.debian.jobs import _build_cmd


def test_git_variante_unveraendert():
    cmd = _build_cmd(
        "homepage",
        "https://github.com/astrapi/packages_debian.git",
        "",
        "ctl/debian-builder:latest",
        Path("/repo/debian"),
    )
    assert cmd[:6] == [
        "docker",
        "run",
        "--rm",
        "-v",
        "/repo/debian:/repo",
        "ctl/debian-builder:latest",
    ]
    script = cmd[-1]
    assert (
        "git clone --depth=1 'https://github.com/astrapi/packages_debian.git' /build/src" in script
    )
    assert "cd /build/src/homepage" in script


def test_git_variante_mit_source_subdir():
    cmd = _build_cmd(
        "mypkg",
        "https://gitlab.com/example/monorepo.git",
        "packages/mypkg",
        "ctl/debian-builder:latest",
        Path("/repo/debian"),
    )
    assert "cd /build/src/packages/mypkg" in cmd[-1]


def test_db_variante_kein_git_clone():
    cmd = _build_cmd(
        "homepage",
        "",
        "",
        "ctl/debian-builder:latest",
        Path("/repo/debian"),
        source_type="db",
        host_src_dir=Path("/tmp/materialized/homepage"),
    )
    assert "-v" in cmd
    assert "/tmp/materialized/homepage:/build/src/homepage:ro" in cmd
    script = cmd[-1]
    assert "git clone" not in script
    assert "cd /build/src/homepage" in script
    assert '[[ ! -f PKGBUILD ]] && { echo "FEHLER: PKGBUILD nicht gefunden' in script


def test_db_variante_ignoriert_source_subdir():
    """Bei source_type='db' bestimmt immer item_id das Zielverzeichnis --
    source_subdir stammt aus der Git-Vergangenheit des Pakets und ist fuer
    DB-verwaltete Pakete irrelevant."""
    cmd = _build_cmd(
        "homepage",
        "",
        "irgendein/alter/pfad",
        "ctl/debian-builder:latest",
        Path("/repo/debian"),
        source_type="db",
        host_src_dir=Path("/tmp/materialized/homepage"),
    )
    assert "cd /build/src/homepage" in cmd[-1]
    assert "irgendein/alter/pfad" not in cmd[-1]


def test_db_variante_ohne_host_src_dir_wirft():
    import pytest

    with pytest.raises(AssertionError):
        _build_cmd(
            "homepage",
            "",
            "",
            "ctl/debian-builder:latest",
            Path("/repo/debian"),
            source_type="db",
        )

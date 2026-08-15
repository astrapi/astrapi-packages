"""Tests fuer _build_cmd() in astrapi_packages.modules._os_profiles.archlinux.jobs (Etappe 3)."""

from pathlib import Path

from astrapi_packages.modules._os_profiles.archlinux.jobs import _build_cmd


def test_git_variante_unveraendert():
    cmd = _build_cmd(
        "epsonscan2",
        "https://aur.archlinux.org/epsonscan2.git",
        "",
        "ctl/arch-builder:latest",
        "/repo/arch/x86_64",
        "pkgctl",
    )
    assert cmd == [
        "docker",
        "run",
        "--rm",
        "-v",
        "/repo/arch/x86_64:/home/makepkg/repo",
        "-e",
        "REPO_NAME=pkgctl",
        "ctl/arch-builder:latest",
        "epsonscan2",
        "https://aur.archlinux.org/epsonscan2.git",
    ]


def test_git_variante_mit_source_subdir():
    cmd = _build_cmd(
        "mypkg",
        "https://gitlab.com/example/monorepo.git",
        "packages/mypkg",
        "ctl/arch-builder:latest",
        "/repo/arch/x86_64",
        "pkgctl",
    )
    assert "-e" in cmd
    assert "SOURCE_SUBDIR=packages/mypkg" in cmd


def test_db_variante_mountet_source_und_leert_url():
    cmd = _build_cmd(
        "homepage",
        "",
        "",
        "ctl/arch-builder:latest",
        "/repo/arch/x86_64",
        "pkgctl",
        source_type="db",
        host_src_dir=Path("/tmp/materialized/homepage"),
    )
    assert "-v" in cmd
    assert "/tmp/materialized/homepage:/home/makepkg/source:ro" in cmd
    # Kein SOURCE_SUBDIR-Env fuer DB-verwaltete Pakete
    assert not any(a.startswith("SOURCE_SUBDIR=") for a in cmd)
    # Letztes Argument (source_url) ist leer -> arch-build.sh nutzt den Mount
    assert cmd[-1] == ""
    assert cmd[-2] == "homepage"


def test_db_variante_ohne_host_src_dir_wirft():
    import pytest

    with pytest.raises(AssertionError):
        _build_cmd(
            "homepage",
            "",
            "",
            "ctl/arch-builder:latest",
            "/repo/arch/x86_64",
            "pkgctl",
            source_type="db",
        )

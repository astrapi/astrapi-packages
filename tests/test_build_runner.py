"""Tests fuer astrapi_packages.utils.build_runner -- generischer Docker-Bau
(ersetzt debian/jobs.py:_build_cmd() und archlinux/jobs.py:_build_cmd()+
arch-build.sh+host-seitiges repo-add, siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul").

Kein echter Docker-Daemon in dieser Umgebung -- getestet wird Materialisierung/
Pfadauflösung, nicht der tatsächliche `docker run`."""

import os

import pytest

from astrapi_packages.utils import build_runner


@pytest.fixture
def fresh_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRAPI_PACKAGES_WORK_DIR", str(tmp_path))
    from astrapi_core.system import db as core_db
    from astrapi_core.system.paths import configure as configure_paths

    from astrapi_packages.utils import file_store

    configure_paths("astrapi-packages")
    core_db._local.conn = None
    core_db.configure(tmp_path / "test.db")
    file_store._table_ready = False

    # Store-Singletons cachen _table_ready pro Instanz -- ohne Reset wuerde
    # eine bereits gegen eine fruehere tmp-DB erfolgreich gelaufene
    # _ensure_table() das CREATE TABLE gegen die NEUE Verbindung ueberspringen
    # ("no such table"), siehe dasselbe Muster bei astrapi_packages._app.
    from astrapi_packages.modules.builder import store as builder_store

    builder_store._table_ready = False

    yield tmp_path
    core_db._local.conn = None


def test_repo_path_legt_unterordner_an(fresh_env):
    p = build_runner.repo_path("debian")
    assert p.exists()
    assert p.name == "debian"


def test_repo_path_leer_gibt_basis(fresh_env):
    p = build_runner.repo_path("")
    assert p.exists()


def test_repo_path_verhindert_traversal(fresh_env):
    with pytest.raises(build_runner.BuildRunnerError):
        build_runner.repo_path("../../etc")


def test_repo_path_verschachtelter_unterordner(fresh_env):
    p = build_runner.repo_path("arch/x86_64")
    assert p.exists()
    assert p.name == "x86_64"


def test_materialize_source_db_liest_aus_file_store(fresh_env):
    from astrapi_packages.utils import file_store

    file_store.save("packages", "debian:foo", "PKGBUILD", "pkgname=foo\npkgver=1\npkgrel=1\n")
    src_dir, tmp_handle = build_runner.materialize_source(
        "packages", "debian:foo", "db", "", "", default_subdir="foo"
    )
    assert (src_dir / "PKGBUILD").exists()
    assert tmp_handle is None


def test_materialize_source_git_ohne_url_wirft(fresh_env):
    with pytest.raises(build_runner.BuildRunnerError):
        build_runner.materialize_source(
            "packages", "debian:foo", "git", "", "", default_subdir="foo"
        )


def test_materialize_source_git_klont_und_findet_pkgbuild(fresh_env, tmp_path):
    import subprocess

    repo_dir = tmp_path / "upstream_repo"
    pkg_dir = repo_dir / "foo"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "PKGBUILD").write_text("pkgname=foo\npkgver=1\npkgrel=1\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "x",
        ],
        check=True,
    )

    src_dir, tmp_handle = build_runner.materialize_source(
        "packages", "debian:foo", "git", f"file://{repo_dir}", "", default_subdir="foo"
    )
    try:
        assert (src_dir / "PKGBUILD").exists()
    finally:
        if tmp_handle:
            tmp_handle.cleanup()


def test_materialize_source_git_fehlende_pkgbuild_wirft(fresh_env, tmp_path):
    import subprocess

    repo_dir = tmp_path / "upstream_repo2"
    repo_dir.mkdir()
    (repo_dir / "readme.txt").write_text("x")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "x",
        ],
        check=True,
    )

    with pytest.raises(build_runner.BuildRunnerError):
        build_runner.materialize_source(
            "packages", "debian:foo", "git", f"file://{repo_dir}", "", default_subdir="foo"
        )


def test_run_publish_ohne_publish_sh_wird_uebersprungen(fresh_env):
    from astrapi_packages.modules.builder import store as builder_store

    builder_store.create("debian-builder", {"tag": "latest"})
    rc, msg = build_runner.run_publish(
        "ctl/debian-builder:latest", "debian-builder", build_runner.repo_path("debian")
    )
    assert rc == 0
    assert "übersprungen" in msg


def test_run_build_ohne_build_sh_meldet_fehler(fresh_env):
    from astrapi_packages.modules.builder import store as builder_store

    builder_store.create("empty-builder", {"tag": "latest"})
    rc, msg = build_runner.run_build(
        "ctl/empty-builder:latest", "empty-builder", os.getcwd(), build_runner.repo_path("debian")
    )
    assert rc == 1
    assert "build.sh" in msg

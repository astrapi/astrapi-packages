"""Tests fuer astrapi_packages.utils.pkgbuild -- konsolidiertes
PKGBUILD-Parsing (ersetzt debian/ui/crud.py:_pkgbuild_info() und
archlinux/ui/crud.py:_version_from_pkgbuild_url(), siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul")."""

import pytest

from astrapi_packages.utils import pkgbuild

_SAMPLE = """\
pkgname=foo
pkgver=1.2.3
pkgrel=2
pkgdesc="Ein Beispielpaket"
arch=('x86_64')
depends=('bar' 'baz>=1.0')
makedepends=('git' "cmake")
"""


def test_parse_version():
    assert pkgbuild.parse_version(_SAMPLE) == "1.2.3-2"


def test_parse_version_ohne_pkgrel():
    text = "pkgname=foo\npkgver=9.0\n"
    assert pkgbuild.parse_version(text) == "9.0"


def test_parse_version_fehlt():
    assert pkgbuild.parse_version("pkgname=foo\n") == ""


def test_parse_deps_entfernt_versions_constraints_und_dubletten():
    deps = pkgbuild.parse_deps(_SAMPLE)
    assert deps == ["bar", "baz", "git", "cmake"]


def test_parse_deps_ohne_depends_block():
    assert pkgbuild.parse_deps("pkgname=foo\npkgver=1\n") == []


@pytest.fixture
def fresh_db(tmp_path):
    from astrapi_core.system import db as core_db

    from astrapi_packages.utils import file_store

    core_db._local.conn = None
    core_db.configure(tmp_path / "test.db")
    file_store._table_ready = False
    yield
    core_db._local.conn = None


def test_read_local_pkgbuild(fresh_db):
    from astrapi_packages.utils import file_store

    file_store.save("packages", "debian:foo", "PKGBUILD", _SAMPLE)
    version, deps = pkgbuild.read_local_pkgbuild("packages", "debian:foo")
    assert version == "1.2.3-2"
    assert deps == ["bar", "baz", "git", "cmake"]


def test_read_local_pkgbuild_ohne_datei(fresh_db):
    version, deps = pkgbuild.read_local_pkgbuild("packages", "debian:nichtvorhanden")
    assert version == ""
    assert deps == []

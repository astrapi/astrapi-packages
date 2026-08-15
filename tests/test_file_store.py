"""Tests fuer astrapi_packages.utils.file_store (Etappe 1 aus
projects/packages/planung-datei-editor.md).

Jede Testfunktion bekommt eine frische, isolierte SQLite-DB ueber die
fresh_db-Fixture -- astrapi_core.system.db haelt die Verbindung
thread-lokal, deshalb muss sowohl der Modul-Pfad als auch die gecachte
Verbindung und file_store's eigener _table_ready-Flag pro Test
zurueckgesetzt werden.
"""

import pytest

from astrapi_packages.utils import file_store


@pytest.fixture
def fresh_db(tmp_path):
    from astrapi_core.system import db as core_db

    core_db._local.conn = None
    core_db.configure(tmp_path / "test.db")
    file_store._table_ready = False
    yield
    core_db._local.conn = None


def test_read_unbekannte_datei_gibt_none(fresh_db):
    assert file_store.read("builder", "arch-builder", "Dockerfile") is None


def test_save_und_read(fresh_db):
    file_store.save("builder", "arch-builder", "Dockerfile", "FROM archlinux\n")
    assert file_store.read("builder", "arch-builder", "Dockerfile") == "FROM archlinux\n"


def test_save_erzeugt_neue_version_statt_ueberschreiben(fresh_db):
    file_store.save("debian", "homepage", "PKGBUILD", "pkgver=1\n")
    file_store.save("debian", "homepage", "PKGBUILD", "pkgver=2\n")
    assert file_store.read("debian", "homepage", "PKGBUILD") == "pkgver=2\n"
    versions = file_store.history("debian", "homepage", "PKGBUILD")
    assert len(versions) == 2
    assert versions[0]["content"] == "pkgver=2\n"  # neueste zuerst
    assert versions[1]["content"] == "pkgver=1\n"


def test_list_files_nur_aktuelle_version_pro_datei(fresh_db):
    file_store.save("archlinux", "epsonscan2", "PKGBUILD", "a")
    file_store.save("archlinux", "epsonscan2", "PKGBUILD", "b")
    file_store.save("archlinux", "epsonscan2", "fix.patch", "diff --git a b")
    files = file_store.list_files("archlinux", "epsonscan2")
    assert {f["filename"] for f in files} == {"PKGBUILD", "fix.patch"}
    pkgbuild = next(f for f in files if f["filename"] == "PKGBUILD")
    assert pkgbuild["content"] == "b"


def test_list_files_isoliert_nach_owner(fresh_db):
    file_store.save("debian", "homepage", "PKGBUILD", "debian-inhalt")
    file_store.save("archlinux", "homepage", "PKGBUILD", "archlinux-inhalt")
    debian_files = file_store.list_files("debian", "homepage")
    assert len(debian_files) == 1
    assert debian_files[0]["content"] == "debian-inhalt"


def test_delete_versteckt_datei_aus_list_und_read(fresh_db):
    file_store.save("builder", "debian-builder", "Dockerfile", "FROM debian\n")
    file_store.delete("builder", "debian-builder", "Dockerfile", message="nicht mehr gebraucht")
    assert file_store.read("builder", "debian-builder", "Dockerfile") is None
    assert file_store.list_files("builder", "debian-builder") == []
    # Historie bleibt erhalten -- Loeschen ist auch nur ein neuer Eintrag
    versions = file_store.history("builder", "debian-builder", "Dockerfile")
    assert len(versions) == 2
    assert versions[0]["is_deleted"] == 1


def test_diff_gegen_leeren_stand(fresh_db):
    d = file_store.diff("builder", "arch-builder", "Dockerfile", "FROM archlinux\n")
    assert "+FROM archlinux" in d


def test_diff_zwischen_zwei_versionen(fresh_db):
    file_store.save("builder", "arch-builder", "Dockerfile", "FROM archlinux\nRUN echo alt\n")
    d = file_store.diff("builder", "arch-builder", "Dockerfile", "FROM archlinux\nRUN echo neu\n")
    assert "-RUN echo alt" in d
    assert "+RUN echo neu" in d


def test_restore_legt_alte_version_als_neue_an(fresh_db):
    file_store.save("debian", "homepage", "PKGBUILD", "pkgver=1\n")
    file_store.save("debian", "homepage", "PKGBUILD", "pkgver=2\n")
    versions = file_store.history("debian", "homepage", "PKGBUILD")
    old_version_id = versions[1]["id"]  # pkgver=1

    file_store.restore("debian", "homepage", "PKGBUILD", old_version_id)

    assert file_store.read("debian", "homepage", "PKGBUILD") == "pkgver=1\n"
    all_versions = file_store.history("debian", "homepage", "PKGBUILD")
    assert len(all_versions) == 3, "Restore ist ein neuer Eintrag, keine Ueberschreibung"


def test_restore_unbekannte_version_wirft(fresh_db):
    with pytest.raises(KeyError):
        file_store.restore("debian", "homepage", "PKGBUILD", 999)


def test_materialize_schreibt_aktuelle_dateien(fresh_db, tmp_path):
    file_store.save("builder", "arch-builder", "Dockerfile", "FROM archlinux\n")
    file_store.save("builder", "arch-builder", "arch-build.sh", "#!/bin/bash\n")

    target = tmp_path / "materialized"
    file_store.materialize("builder", "arch-builder", target)

    assert (target / "Dockerfile").read_text() == "FROM archlinux\n"
    assert (target / "arch-build.sh").read_text() == "#!/bin/bash\n"


def test_materialize_raeumt_geloeschte_dateien_aus_altem_lauf_auf(fresh_db, tmp_path):
    target = tmp_path / "materialized"
    target.mkdir()
    (target / "veraltet.txt").write_text("sollte weg")

    file_store.save("builder", "arch-builder", "Dockerfile", "FROM archlinux\n")
    file_store.materialize("builder", "arch-builder", target)

    assert not (target / "veraltet.txt").exists()
    assert (target / "Dockerfile").exists()

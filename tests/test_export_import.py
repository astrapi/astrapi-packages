"""Tests fuer astrapi_packages.utils.export_import (Etappe 4)."""

import pytest

from astrapi_packages.utils.export_import import export_items, import_items


class _FakeStore:
    """Minimaler Store analog file_store-kompatiblen Stores (dict-basiert)."""

    def __init__(self):
        self._data: dict[str, dict] = {}

    def list(self) -> dict:
        return dict(self._data)

    def get(self, item_id: str) -> dict | None:
        return self._data.get(item_id)

    def create(self, item_id: str, data: dict) -> None:
        self._data[item_id] = dict(data)

    def update(self, item_id: str, data: dict) -> None:
        self._data.setdefault(item_id, {}).update(data)


@pytest.fixture
def fresh_db(tmp_path):
    from astrapi_core.system import db as core_db

    from astrapi_packages.utils import file_store

    core_db._local.conn = None
    core_db.configure(tmp_path / "test.db")
    file_store._table_ready = False
    yield
    core_db._local.conn = None


def test_export_enthaelt_metadaten_und_dateien(fresh_db):
    from astrapi_packages.utils import file_store

    store = _FakeStore()
    store.create("arch-builder", {"tag": "latest", "module": "archlinux", "last_status": "ok"})
    file_store.save("builder", "arch-builder", "arch-builder.dockerfile", "FROM archlinux\n")

    result = export_items("builder", store, metadata_fields=["tag", "module"])

    assert len(result) == 1
    assert result[0]["item_id"] == "arch-builder"
    assert result[0]["metadata"] == {"tag": "latest", "module": "archlinux"}
    assert "last_status" not in result[0]["metadata"], (
        "Laufzeit-Status darf nicht exportiert werden"
    )
    assert result[0]["files"] == [
        {"filename": "arch-builder.dockerfile", "content": "FROM archlinux\n"}
    ]


def test_export_nur_ausgewaehlte_ids(fresh_db):
    store = _FakeStore()
    store.create("a", {"tag": "latest"})
    store.create("b", {"tag": "latest"})

    result = export_items("builder", store, metadata_fields=["tag"], item_ids=["a"])

    assert [r["item_id"] for r in result] == ["a"]


def test_import_legt_fehlendes_an(fresh_db):
    from astrapi_packages.utils import file_store

    store = _FakeStore()
    data = [
        {
            "item_id": "neu",
            "metadata": {"tag": "latest", "module": "debian"},
            "files": [{"filename": "neu.dockerfile", "content": "FROM debian\n"}],
        }
    ]

    summary = import_items("builder", store, data)

    assert summary == {"created": 1, "updated": 0, "files_imported": 1}
    assert store.get("neu") == {"tag": "latest", "module": "debian"}
    assert file_store.read("builder", "neu", "neu.dockerfile") == "FROM debian\n"


def test_import_gleicht_vorhandenes_ab_ohne_historie_zu_verlieren(fresh_db):
    from astrapi_packages.utils import file_store

    store = _FakeStore()
    store.create("bestehend", {"tag": "alt"})
    file_store.save("builder", "bestehend", "x.dockerfile", "alte Version")

    data = [
        {
            "item_id": "bestehend",
            "metadata": {"tag": "neu"},
            "files": [{"filename": "x.dockerfile", "content": "neue Version"}],
        }
    ]
    summary = import_items("builder", store, data)

    assert summary["created"] == 0
    assert summary["updated"] == 1
    assert store.get("bestehend")["tag"] == "neu"
    assert file_store.read("builder", "bestehend", "x.dockerfile") == "neue Version"
    # Alte Version bleibt in der Historie erhalten
    history = file_store.history("builder", "bestehend", "x.dockerfile")
    assert len(history) == 2
    assert history[-1]["content"] == "alte Version"


def test_roundtrip_export_dann_import_in_zweite_instanz(fresh_db):
    """Simuliert Dev -> Prod: Export aus einem Store, Import in einen anderen."""
    from astrapi_packages.utils import file_store

    dev_store = _FakeStore()
    dev_store.create("homepage", {"tag": "latest", "module": "debian"})
    file_store.save("builder", "homepage", "PKGBUILD", "pkgver=1.13.2\n")

    exported = export_items("builder", dev_store, metadata_fields=["tag", "module"])

    prod_store = _FakeStore()
    summary = import_items("builder", prod_store, exported)

    assert summary["created"] == 1
    assert prod_store.get("homepage")["tag"] == "latest"
    assert file_store.read("builder", "homepage", "PKGBUILD") == "pkgver=1.13.2\n"

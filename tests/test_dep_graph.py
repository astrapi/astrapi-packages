"""Tests fuer astrapi_packages.utils.dep_graph -- verschoben+generalisiert aus
dem vormaligen archlinux/utils/dep_graph.py (siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul"): gilt jetzt
fuer jeden os_type, Store-Keys sind "{os_type}:{name}" waehrend depends
blanke Namen enthaelt (wie in einer PKGBUILD)."""

import pytest

from astrapi_packages.utils import dep_graph


class FakeStore:
    """Minimaler store.list()-kompatibler Stand-in, kein DB-Zugriff noetig."""

    def __init__(self, items: dict):
        self._items = dict(items)

    def list(self):
        return dict(self._items)

    def get(self, item_id):
        return self._items.get(item_id)

    def create(self, item_id, data):
        if item_id in self._items:
            raise KeyError(item_id)
        self._items[item_id] = data

    def update(self, item_id, data):
        self._items[item_id].update(data)

    def delete(self, item_id):
        del self._items[item_id]


@pytest.fixture
def store():
    return FakeStore(
        {
            "archlinux:a": {
                "name": "a",
                "os_type": "archlinux",
                "depends": "b",
                "pkg_type": "package",
            },
            "archlinux:b": {
                "name": "b",
                "os_type": "archlinux",
                "depends": "",
                "pkg_type": "dependency",
            },
        }
    )


def test_parse_deps_leer():
    assert dep_graph.parse_deps({"depends": ""}) == []
    assert dep_graph.parse_deps({}) == []


def test_parse_deps_kommagetrennt():
    assert dep_graph.parse_deps({"depends": "a, b ,c"}) == ["a", "b", "c"]


def test_resolve_build_order_blaetter_zuerst(store):
    order = dep_graph.resolve_build_order(["archlinux:a"], store)
    assert order == ["archlinux:b", "archlinux:a"]


def test_resolve_build_order_ignoriert_unbekannte_deps():
    s = FakeStore({"archlinux:a": {"name": "a", "os_type": "archlinux", "depends": "nichtimstore"}})
    order = dep_graph.resolve_build_order(["archlinux:a"], s)
    assert order == ["archlinux:a"]


def test_resolve_build_order_erkennt_zyklus():
    s = FakeStore(
        {
            "archlinux:a": {"name": "a", "os_type": "archlinux", "depends": "b"},
            "archlinux:b": {"name": "b", "os_type": "archlinux", "depends": "a"},
        }
    )
    with pytest.raises(dep_graph.CyclicDependencyError):
        dep_graph.resolve_build_order(["archlinux:a"], s)


def test_find_orphan_deps(store):
    orphans = dep_graph.find_orphan_deps("archlinux:a", store)
    assert orphans == ["archlinux:b"]


def test_find_orphan_deps_bleibt_bei_manuellem_paket():
    s = FakeStore(
        {
            "archlinux:a": {"name": "a", "os_type": "archlinux", "depends": "b"},
            "archlinux:b": {
                "name": "b",
                "os_type": "archlinux",
                "depends": "",
                "pkg_type": "package",
            },
        }
    )
    # b ist pkg_type='package' (nicht 'dependency') -- gilt nie als verwaist
    assert dep_graph.find_orphan_deps("archlinux:a", s) == []


def test_find_all_orphan_deps(store):
    assert dep_graph.find_all_orphan_deps(store) == []
    store.delete("archlinux:a")
    assert dep_graph.find_all_orphan_deps(store) == ["archlinux:b"]


def test_autocreate_deps_ohne_template_tut_nichts(store):
    created = dep_graph.autocreate_deps(
        "archlinux:a", store.get("archlinux:a"), store, url_template=""
    )
    assert created == []


def test_autocreate_deps_legt_fehlende_dep_an():
    s = FakeStore({"archlinux:a": {"name": "a", "os_type": "archlinux", "depends": "neu"}})
    created = dep_graph.autocreate_deps(
        "archlinux:a",
        s.get("archlinux:a"),
        s,
        url_template="https://aur.archlinux.org/{name}.git",
    )
    assert created == ["archlinux:neu"]
    neu = s.get("archlinux:neu")
    assert neu["source_url"] == "https://aur.archlinux.org/neu.git"
    assert neu["pkg_type"] == "dependency"


def test_autocreate_deps_ueberschreibt_bestehende_nicht():
    s = FakeStore(
        {
            "archlinux:a": {"name": "a", "os_type": "archlinux", "depends": "b"},
            "archlinux:b": {"name": "b", "os_type": "archlinux", "source_url": "custom"},
        }
    )
    created = dep_graph.autocreate_deps(
        "archlinux:a", s.get("archlinux:a"), s, url_template="https://aur.archlinux.org/{name}.git"
    )
    assert created == []
    assert s.get("archlinux:b")["source_url"] == "custom"

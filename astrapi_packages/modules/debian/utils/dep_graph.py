"""app/modules/debian/dep_graph.py – Dependency-Graph-Logik für Debian-Pakete.

1:1 nach dem Vorbild von archlinux/utils/dep_graph.py (gleiches PKGBUILD-
basiertes Abhängigkeitsmodell, siehe "Bridge-Ansatz" in beschreibung.md).
Auto-angelegte Abhängigkeiten werden weiterhin über AUR aufgelöst (dort
liegt die Quelle, auch wenn daraus ein .deb statt eines Arch-Pakets gebaut
wird).

ACHTUNG (G-019, siehe projects/packages/grundsaetze.md): diese Datei ist
bewusst eine eigenstaendige 1:1-Kopie von archlinux/utils/dep_graph.py,
keine gemeinsame Utility. Bei Aenderungen hier IMMER auch das Schwester-
modul pruefen und die Aenderung dort nachziehen, falls sinnvoll -- gleiches
gilt fuer die zugehoerige Logik in jobs.py (_sync_pkgbuild_deps,
build_package_with_deps, mark_orphan_deps, Orphan-Cleanup in
delete_package) und dialogs/edit/modal.html (Abhaengigkeiten-Feld).
"""

from __future__ import annotations

import logging
from collections import deque

log = logging.getLogger(__name__)


class CyclicDependencyError(Exception):
    pass


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────


def parse_aur_deps(item: dict) -> list[str]:
    """Liest aur_deps aus einem Item-Dict und gibt bereinigte Namen zurück."""
    raw = (item.get("aur_deps") or "").strip()
    if not raw:
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


def is_up_to_date(item_id: str, repo_path) -> bool:
    """Prüft ob ein gebautes Paket bereits im Repo-Verzeichnis liegt."""
    import glob
    import os

    pattern = os.path.join(str(repo_path), f"{item_id}_*.deb")
    return bool(glob.glob(pattern))


# ── Graph-Auflösung ────────────────────────────────────────────────────────────


def resolve_build_order(start_ids: list[str], store) -> list[str]:
    """Gibt die Build-Reihenfolge zurück (Blätter zuerst, Hauptpaket zuletzt).

    Ignoriert Deps die nicht im Store vorhanden sind.

    Raises:
        CyclicDependencyError: wenn ein Zyklus erkannt wird.
    """
    all_items = store.list()

    # Phase 1: Graph aufbauen (BFS, nur Store-bekannte Knoten)
    graph: dict[str, set[str]] = {}
    visited: set[str] = set()
    queue: deque[str] = deque(start_ids)

    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        item = all_items.get(node)
        if item is None:
            continue
        deps_in_store = {d for d in parse_aur_deps(item) if d in all_items}
        graph[node] = deps_in_store
        for dep in deps_in_store:
            if dep not in visited:
                queue.append(dep)

    # Phase 2: Topologische Sortierung via Kahn
    in_degree: dict[str, int] = {n: len(graph.get(n, set())) for n in visited}
    reverse: dict[str, set[str]] = {n: set() for n in visited}
    for node, deps in graph.items():
        for dep in deps:
            if dep in reverse:
                reverse[dep].add(node)

    kahn_queue: deque[str] = deque(n for n in visited if in_degree[n] == 0)
    order: list[str] = []

    while kahn_queue:
        node = kahn_queue.popleft()
        order.append(node)
        for dependent in reverse.get(node, set()):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                kahn_queue.append(dependent)

    if len(order) < len(visited):
        cycle_nodes = [n for n in visited if n not in set(order)]
        raise CyclicDependencyError(
            f"Zyklische Abhängigkeit erkannt zwischen: {', '.join(sorted(cycle_nodes))}"
        )

    return order  # Blätter (keine Abhängigen) zuerst, start_ids zuletzt


# ── Autocreate ─────────────────────────────────────────────────────────────────


def autocreate_deps(item_id: str, item: dict, store) -> list[str]:
    """Bewusstes No-Op (T-179-PACKAGES).

    1:1-Übernahme von archlinux/utils/dep_graph.py hätte hier fehlende
    `aur_deps`-Einträge automatisch als eigene, buildbare Paket-Einträge
    angelegt -- mit `source_url = f"https://aur.archlinux.org/{dep_name}.git"`.
    Bei archlinux korrekt (AUR-Pakete müssen selbst gebaut werden), bei
    debian schlicht falsch: `depends`/`makedepends` sind dort praktisch immer
    fertige apt-Pakete, kein AUR-Äquivalent für "existiert das, muss es aber
    trotzdem selbst gebaut werden" vorhanden. Ohne dieses No-Op würden neue
    PKGBUILD-Deps als kaputte Paket-Einträge mit AUR-Git-URLs angelegt.
    `aur_deps` selbst bleibt als reine Anzeige/Snapshot erhalten (siehe
    debian/jobs.py::_sync_pkgbuild_deps) -- fehlt eine selbstgebaute
    Abhängigkeit zwischen eigenen Debian-Paketen, wird sie weiterhin von
    Hand angelegt.
    """
    return []


# ── Orphan-Cleanup ─────────────────────────────────────────────────────────────


def find_all_orphan_deps(store) -> list[str]:
    """Gibt alle Dep-IDs zurück die von keinem Paket mehr referenziert werden.

    Nur Einträge mit pkg_type=='dependency' werden berücksichtigt –
    manuell angelegte Pakete werden nie als verwaist betrachtet.
    """
    all_items = store.list()

    referenced: set[str] = set()
    for pkg_data in all_items.values():
        for d in parse_aur_deps(pkg_data):
            referenced.add(d)

    return [
        item_id
        for item_id, item_data in all_items.items()
        if item_data.get("pkg_type") == "dependency" and item_id not in referenced
    ]


def find_orphan_deps(deleted_id: str, store) -> list[str]:
    """Gibt Dep-IDs zurück die nach dem Löschen von deleted_id verwaist wären.

    Nur Einträge mit pkg_type=='dependency' werden berücksichtigt –
    manuell angelegte Pakete werden nie automatisch gelöscht.
    """
    all_items = store.list()
    deleted_item = all_items.get(deleted_id, {})
    deps_of_deleted = set(parse_aur_deps(deleted_item))

    if not deps_of_deleted:
        return []

    still_needed: set[str] = set()
    for pkg_id, pkg_data in all_items.items():
        if pkg_id == deleted_id:
            continue
        for d in parse_aur_deps(pkg_data):
            still_needed.add(d)

    orphans = deps_of_deleted - still_needed
    return [o for o in orphans if all_items.get(o, {}).get("pkg_type") == "dependency"]

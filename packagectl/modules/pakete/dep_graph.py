"""app/modules/pakete/dep_graph.py – Dependency-Graph-Logik für AUR-Pakete."""

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


def is_up_to_date(item_id: str, repo_path: str) -> bool:
    """Prüft ob ein gebautes Paket bereits im Repo-Verzeichnis liegt."""
    import glob
    import os
    pattern = os.path.join(repo_path, f"{item_id}-*.pkg.tar.*")
    return bool(glob.glob(pattern))


# ── Graph-Auflösung ────────────────────────────────────────────────────────────

def resolve_build_order(start_ids: list[str], store) -> list[str]:
    """Gibt die Build-Reihenfolge zurück (Blätter zuerst, Hauptpaket zuletzt).

    Ignoriert Deps die nicht im Store vorhanden sind – diese werden von
    Pacman/yay direkt aufgelöst.

    Raises:
        CyclicDependencyError: wenn ein Zyklus erkannt wird.
    """
    all_items = store.list()

    # Phase 1: Graph aufbauen (BFS, nur Store-bekannte Knoten)
    graph: dict[str, set[str]] = {}  # node → {deps die auch im Store sind}
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
        deps_in_store = {
            d for d in parse_aur_deps(item) if d in all_items
        }
        graph[node] = deps_in_store
        for dep in deps_in_store:
            if dep not in visited:
                queue.append(dep)

    # Phase 2: Topologische Sortierung via Kahn
    # in_degree: wie viele Deps muss ein Knoten noch warten?
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

    # Zykluserkennung: nicht alle Knoten sortiert → Zyklus
    if len(order) < len(visited):
        cycle_nodes = [n for n in visited if n not in set(order)]
        raise CyclicDependencyError(
            f"Zyklische Abhängigkeit erkannt zwischen: {', '.join(sorted(cycle_nodes))}"
        )

    return order  # Blätter (keine Abhängigen) zuerst, start_ids zuletzt


# ── Autocreate ─────────────────────────────────────────────────────────────────

def autocreate_deps(item_id: str, item: dict, store) -> list[str]:
    """Legt fehlende Dep-Einträge automatisch im Store an.

    Bestehende Einträge werden nicht überschrieben.
    Gibt Liste der neu angelegten IDs zurück.
    """
    created: list[str] = []
    all_items = store.list()

    for dep_name in parse_aur_deps(item):
        if dep_name == item_id:
            continue  # Selbstreferenz ignorieren
        if dep_name in all_items:
            continue  # Bereits vorhanden, nicht überschreiben
        aur_url = f"https://aur.archlinux.org/{dep_name}.git"
        try:
            store.create(dep_name, {
                "source_url": aur_url,
                "pkg_type":   "dependency",
                "enabled":    True,
            })
            created.append(dep_name)
            log.info("dep_graph: Dep-Eintrag '%s' automatisch angelegt", dep_name)
        except KeyError:
            pass  # Race condition: zwischenzeitlich angelegt

    return created


# ── Orphan-Cleanup ─────────────────────────────────────────────────────────────

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

    # Welche Deps werden noch von anderen Paketen benötigt?
    still_needed: set[str] = set()
    for pkg_id, pkg_data in all_items.items():
        if pkg_id == deleted_id:
            continue
        for d in parse_aur_deps(pkg_data):
            still_needed.add(d)

    orphans = deps_of_deleted - still_needed
    # Nur auto-angelegte Dependencies löschen, keine manuellen Pakete
    return [
        o for o in orphans
        if all_items.get(o, {}).get("pkg_type") == "dependency"
    ]

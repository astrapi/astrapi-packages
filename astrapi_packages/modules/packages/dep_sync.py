"""astrapi_packages.modules.packages.dep_sync – Depends aus der PKGBUILD
übernehmen und fehlende Dep-Einträge automatisch anlegen.

Generalisiert aus dem vormaligen archlinux/jobs.py:_sync_pkgbuild_deps() --
nutzt jetzt os_types.depends_url_template statt hart codierter AUR-URL,
funktioniert für jeden OS-Typ mit Git-Quelle + Subdir.
"""

from __future__ import annotations

import logging

from astrapi_packages.utils import dep_graph, pkgbuild

from .storage import split_id

log = logging.getLogger(__name__)


def sync_pkgbuild_deps(item_id: str, store) -> None:
    """Liest depends/makedepends aus der Git-PKGBUILD und legt fehlende
    Dep-Einträge an (nur wenn der OS-Typ ein depends_url_template hat).

    Nur für Pakete mit source_type='git' und source_subdir. Aktualisiert
    außerdem upstream_version.
    """
    from astrapi_packages.modules.os_types import store as os_types_store

    item = store.get(item_id) or {}
    os_type, name = split_id(item_id)
    source_url = item.get("source_url", "")
    source_sub = item.get("source_subdir", "")
    if not (source_url and source_sub):
        return

    upstream_ver, pkgbuild_deps = pkgbuild.read_remote_pkgbuild(source_url, source_sub)
    if upstream_ver:
        store.update(item_id, {"upstream_version": upstream_ver})
    if not pkgbuild_deps:
        return

    current_deps = set(d.strip() for d in (item.get("depends") or "").split(",") if d.strip())
    pkgbuild_set = set(pkgbuild_deps)
    new_deps = [d for d in pkgbuild_deps if d not in current_deps]
    removed_deps = current_deps - pkgbuild_set

    url_template = (os_types_store.get(os_type) or {}).get("depends_url_template", "")
    updated_deps = current_deps
    if new_deps or removed_deps:
        updated_deps = (current_deps | set(new_deps)) - removed_deps
        store.update(item_id, {"depends": ", ".join(sorted(updated_deps))})
        if new_deps and url_template:
            dep_graph.autocreate_deps(
                item_id,
                {"depends": ", ".join(sorted(updated_deps)), "os_type": os_type},
                store,
                url_template=url_template,
            )
            log.info("dep_sync: '%s' – neue Deps: %s", item_id, ", ".join(new_deps))
        if removed_deps:
            log.info("dep_sync: '%s' – Deps entfernt: %s", item_id, ", ".join(removed_deps))

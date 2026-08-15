"""astrapi_packages.modules.packages.jobs – generische Build-/Update-Logik.

Ersetzt debian/jobs.py und archlinux/jobs.py: Build/Publish laufen jetzt
über astrapi_packages.utils.build_runner (Docker-Aufruf + DB-editierbare
build.sh/publish.sh je Builder-Image) statt über OS-spezifischen Python-Code,
siehe projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul".

Bekannte Einschränkung ggü. frueher: delete_package() entfernt nur den
DB-Eintrag, nicht mehr automatisch die zugehoerigen gebauten Dateien im Repo
(frueher `{name}_*.deb`/`{name}-*.pkg.tar.*`-Globs, OS-spezifisch hart
codiert) -- das Dateiformat kennt jetzt nur noch publish.sh, nicht mehr
Python. Repo-Aufraeumen bei Bedarf manuell oder ueber ein zukuenftiges,
ebenfalls DB-editierbares Aufraeum-Skript.
"""

from __future__ import annotations

import logging

from astrapi_core.system.format import fmt_now as _now

from astrapi_packages.api import status as _status
from astrapi_packages.utils import build_runner, dep_graph, pkgbuild

from .storage import split_id

log = logging.getLogger(__name__)


def _os_type_row(os_type: str) -> dict:
    from astrapi_packages.modules.os_types import store as os_types_store

    return os_types_store.get(os_type) or {}


def _default_image(os_type: str) -> str:
    from astrapi_core.ui.settings_registry import get_module as _get

    return _get("packages", f"default_image_{os_type}", "") or ""


def build_package(item_id: str, notify: bool = True, own_log_entry: bool = True) -> None:
    """Baut ein Paket im Docker-Container (build.sh) und veröffentlicht es
    (publish.sh), beides über build_runner.py -- OS-unabhängig.

    notify/own_log_entry: wie frueher bei debian/archlinux (siehe deren
    build_package()-Docstrings) -- own_log_entry=False fuer den manuellen
    Run-Router-Pfad (der schon einen eigenen activity_log-Kontext hat),
    notify=False fuer Sammel-Benachrichtigungen aus update_all_packages().
    """

    from . import store

    item = store.get(item_id)
    if not item:
        log.warning("packages.build: Eintrag '%s' nicht gefunden", item_id)
        return

    os_type, name = split_id(item_id)
    os_type_row = _os_type_row(os_type)
    image_id = (item.get("image") or "").strip() or _default_image(os_type)
    if not image_id:
        store.update(
            item_id,
            {
                "last_status": _status.ERROR,
                "last_run": _now(),
                "last_log": f"Kein Build-Image für OS-Typ '{os_type}' hinterlegt.",
            },
        )
        return

    from astrapi_packages.modules.builder import store as builder_store

    builder_item = builder_store.get(image_id)
    if builder_item is None:
        store.update(
            item_id,
            {
                "last_status": _status.ERROR,
                "last_run": _now(),
                "last_log": f"Builder-Image '{image_id}' nicht gefunden.",
            },
        )
        return
    image = f"ctl/{image_id}:{builder_item.get('tag', 'latest')}"

    source_url = (item.get("source_url") or "").strip()
    source_subdir = (item.get("source_subdir") or "").strip()
    source_type = (item.get("source_type") or "git").strip()

    try:
        src_dir, tmp_handle = build_runner.materialize_source(
            "packages", item_id, source_type, source_url, source_subdir, default_subdir=name
        )
    except build_runner.BuildRunnerError as e:
        store.update(
            item_id, {"last_status": _status.ERROR, "last_run": _now(), "last_log": str(e)}
        )
        return

    try:
        repo_dir = build_runner.repo_path(os_type_row.get("repo_subdir", ""))
    except build_runner.BuildRunnerError as e:
        store.update(
            item_id, {"last_status": _status.ERROR, "last_run": _now(), "last_log": str(e)}
        )
        if tmp_handle:
            tmp_handle.cleanup()
        return

    store.update(item_id, {"last_status": _status.BUILDING, "last_run": _now()})

    import time as _time

    _t0 = _time.time()
    _act_id = None
    if own_log_entry:
        try:
            from astrapi_core.system.activity_log import log_activity
            from astrapi_core.system.logger import set_active_log_id

            _act_id = log_activity(
                "job", "packages", f"Paket bauen: {item_id}", status="running", item_id=item_id
            )
            set_active_log_id(_act_id)
        except Exception:
            pass

    try:
        rc, output = build_runner.run_build(image, image_id, src_dir, repo_dir)
    finally:
        if tmp_handle:
            tmp_handle.cleanup()

    if rc == 0:
        pub_rc, pub_output = build_runner.run_publish(
            image,
            image_id,
            repo_dir,
            _gnupg_home(os_type_row),
            os_type_row.get("gpg_key_id", ""),
        )
        output = f"{output}\n\n--- publish.sh ---\n{pub_output}"
        if pub_rc != 0:
            rc = pub_rc

    if rc == 0:
        _trigger_mirror_sync(os_type)

    version = None
    if rc == 0 and source_type == "db":
        version, _ = pkgbuild.read_local_pkgbuild("packages", item_id)
    elif rc == 0:
        version, _ = pkgbuild.read_remote_pkgbuild(source_url, source_subdir or name)

    status = _status.OK if rc == 0 else _status.ERROR
    log.info("packages.build: %s → %s (rc=%d)", item_id, status, rc)

    update: dict = {"last_status": status, "last_run": _now(), "last_log": output[-20_000:]}
    if version:
        update["last_version"] = version
    store.update(item_id, update)

    if _act_id:
        try:
            from astrapi_core.system.activity_log import update_activity_log

            update_activity_log(
                log_id=_act_id,
                status=status,
                duration_s=int(_time.time() - _t0),
                error_message=output[-500:] if status == _status.ERROR else None,
            )
        except Exception:
            pass
        finally:
            try:
                from astrapi_core.system.logger import clear_active_log_id

                clear_active_log_id()
            except Exception:
                pass

    if notify:
        try:
            from astrapi_core.modules.notify import engine as _notify

            if status == _status.OK:
                ver_info = f" ({version})" if version else ""
                _notify.send(
                    title=f"Paket {item_id} erfolgreich gebaut{ver_info}",
                    message="Status: ok",
                    event=_notify.SUCCESS,
                    source="packages",
                )
            else:
                _notify.send(
                    title=f"Paket {item_id} – Fehler beim Bauen",
                    message=output[-400:].strip(),
                    event=_notify.ERROR,
                    source="packages",
                )
        except Exception:
            pass


def _gnupg_home(os_type_row: dict):
    """GPG-Homedir fuer publish.sh, nur falls im OS-Typ hinterlegt (z.B. Debian-Signierung)."""
    from pathlib import Path

    raw = (os_type_row.get("gnupg_home") or "").strip()
    return Path(raw).expanduser() if raw else None


def _trigger_mirror_sync(os_type: str) -> None:
    try:
        from astrapi_core.ui.settings_registry import get_module as _gm

        url = (_gm("packages", f"mirror_trigger_url_{os_type}", default="") or "").strip()
        if not url:
            return
        import urllib.request

        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5):
            pass
        log.info("packages.build: mirror-sync ausgelöst (%s) → %s", os_type, url)
    except Exception as e:
        log.warning("packages.build: mirror-sync fehlgeschlagen (%s): %s", os_type, e)


# ── Zentraler Run-Router: run_single ─────────────────────────────────────────


def run_single(item_id: str) -> None:
    """Löst den Dependency-Graph auf und baut alle fehlenden Deps vor dem
    Hauptpaket -- wie frueher archlinux/jobs.py:run_single(), jetzt generisch."""
    from astrapi_core.system.logger import log as _log

    from . import store
    from .dep_sync import sync_pkgbuild_deps

    item = store.get(item_id)
    if not item:
        _log("ERROR", f"Paket '{item_id}' nicht gefunden")
        return

    sync_pkgbuild_deps(item_id, store)

    try:
        build_order = dep_graph.resolve_build_order([item_id], store)
    except dep_graph.CyclicDependencyError as e:
        store.update(item_id, {"last_status": _status.ERROR, "last_run": _now()})
        _log("ERROR", str(e))
        return

    for dep_id in build_order:
        if dep_id == item_id:
            continue
        _log("INFO", f"Baue Abhängigkeit: {dep_id}")
        build_package(dep_id, notify=True, own_log_entry=False)
        dep_item = store.get(dep_id)
        if dep_item and dep_item.get("last_status") == _status.ERROR:
            store.update(item_id, {"last_status": _status.ERROR, "last_run": _now()})
            _log("ERROR", f"Abhängigkeit '{dep_id}' konnte nicht gebaut werden.")
            return

    _log("INFO", f"Baue: {item_id}")
    build_package(item_id, notify=True, own_log_entry=False)


# ── Cleanup beim Löschen ───────────────────────────────────────────────────────


def delete_package(item_id: str, item: dict) -> None:
    """Entfernt verwaiste Dependency-Einträge, die nur von diesem Paket
    benötigt wurden (rekursiv). Entfernt NICHT die gebauten Dateien im Repo,
    siehe Modul-Docstring."""
    from . import store

    orphans = dep_graph.find_orphan_deps(item_id, store)
    for orphan_id in orphans:
        orphan_item = store.get(orphan_id)
        if orphan_item is None:
            continue
        log.info("packages.delete: verwaiste Dep '%s' wird mitgelöscht", orphan_id)
        delete_package(orphan_id, orphan_item)
        store.delete(orphan_id)


# ── Orphan-Markierung ──────────────────────────────────────────────────────────


def mark_orphan_deps() -> None:
    from . import store

    all_items = store.list()
    orphan_ids = set(dep_graph.find_all_orphan_deps(store))

    newly_orphaned: list[str] = []
    newly_adopted: list[str] = []

    for item_id, item_data in all_items.items():
        if item_data.get("pkg_type") != "dependency":
            continue
        was_orphan = bool(item_data.get("orphaned"))
        is_orphan = item_id in orphan_ids
        if is_orphan and not was_orphan:
            store.update(item_id, {"orphaned": True})
            newly_orphaned.append(item_id)
        elif not is_orphan and was_orphan:
            store.update(item_id, {"orphaned": False})
            newly_adopted.append(item_id)

    log.info(
        "mark_orphan_deps: %d neu verwaist, %d wieder referenziert",
        len(newly_orphaned),
        len(newly_adopted),
    )


# ── Update-Job ─────────────────────────────────────────────────────────────────


def update_all_packages() -> None:
    """Prüft auf neue Versionen (generisch per PKGBUILD-Parsing, siehe
    utils/pkgbuild.py -- kein AUR-Batch-Call mehr, siehe "Virtuelles
    OS-Modul") und baut veraltete Pakete neu."""
    import time as _time

    from . import store
    from .dep_sync import sync_pkgbuild_deps

    _t0 = _time.time()
    _act_id = None
    try:
        from astrapi_core.system.activity_log import log_activity

        _act_id = log_activity("job", "packages", "Pakete: Aktualisieren", status="running")
    except Exception:
        pass

    def _finish(status: str, built: int = 0, error: str | None = None) -> None:
        if _act_id:
            try:
                from astrapi_core.system.activity_log import update_activity_log

                update_activity_log(
                    log_id=_act_id,
                    status=status,
                    duration_s=int(_time.time() - _t0),
                    changed_count=built,
                    error_message=error,
                )
            except Exception:
                pass

    all_items = store.list()
    built_ids = [k for k, v in all_items.items() if v.get("last_status") in _status.AUTO_UPDATE]

    nie_gebaut = [k for k, v in all_items.items() if _status.ist_nie_gebaut(v.get("last_status"))]
    fehlerhaft = [k for k, v in all_items.items() if v.get("last_status") == _status.ERROR]
    if nie_gebaut:
        log.info(
            "packages.update_all: %d Paket(e) noch nie gebaut, erster Bau von Hand (G-017): %s",
            len(nie_gebaut),
            ", ".join(sorted(nie_gebaut)),
        )
    if fehlerhaft:
        log.warning(
            "packages.update_all: %d Paket(e) im Fehlerzustand, nicht automatisch erneut gebaut: %s",
            len(fehlerhaft),
            ", ".join(sorted(fehlerhaft)),
        )

    if not built_ids:
        _finish("ok")
        return

    to_build: list[str] = []
    for item_id in built_ids:
        item = all_items[item_id]
        os_type, name = split_id(item_id)
        source_type = (item.get("source_type") or "git").strip()

        if source_type == "db":
            upstream, _ = pkgbuild.read_local_pkgbuild("packages", item_id)
        else:
            source_url = item.get("source_url", "").strip()
            source_subdir = item.get("source_subdir", "").strip()
            upstream = ""
            if source_url:
                upstream, _ = pkgbuild.read_remote_pkgbuild(source_url, source_subdir or name)
                sync_pkgbuild_deps(item_id, store)

        if not upstream:
            log.warning(
                "packages.update_all: %s uebersprungen - keine Versionsinfo (PKGBUILD)", item_id
            )
            continue

        store.update(item_id, {"upstream_version": upstream})
        current = (store.get(item_id) or {}).get("last_version", "")
        if upstream == current:
            log.info("packages.update_all: %s ist aktuell (%s)", item_id, current)
            continue

        log.info(
            "packages.update_all: %s veraltet (%s → %s), zum Bau vorgemerkt",
            item_id,
            current,
            upstream,
        )
        to_build.append(item_id)

    for item_id in to_build:
        store.update(item_id, {"last_status": _status.PENDING})

    built_count = 0
    errors: list[str] = []
    for item_id in to_build:
        try:
            build_package(item_id, notify=False)
            if (store.get(item_id) or {}).get("last_status") == _status.OK:
                built_count += 1
            else:
                errors.append(item_id)
        except Exception as e:
            log.error("packages.update_all: Fehler bei %s: %s", item_id, e)
            errors.append(item_id)

    _finish("error" if errors else "ok", built=built_count, error="\n".join(errors) or None)

    try:
        from astrapi_core.modules.notify import engine as _notify

        if errors:
            _notify.send(
                title="Pakete: Aktualisieren – Fehler",
                message=f"{built_count} gebaut, Fehler bei: {', '.join(errors)}",
                event=_notify.ERROR,
                source="packages",
            )
        elif built_count:
            _notify.send(
                title=f"Pakete: {built_count} Paket(e) aktualisiert",
                message=f"{built_count} von {len(built_ids)} geprüften Paketen wurden neu gebaut.",
                event=_notify.SUCCESS,
                source="packages",
            )
    except Exception:
        pass

"""app/modules/archlinux/jobs.py – Build-Logik für Arch-Pakete."""

import logging
import os
import re
import subprocess
from pathlib import Path

from astrapi_core.system.format import fmt_now as _now

from astrapi_packages.api import status as _status
from astrapi_packages.modules.archlinux.utils import pkg_cache

log = logging.getLogger(__name__)

_TIMEOUT = 3600


_ERR_KEYWORDS = ("error", "fehler", "not found", "failed", "command not found", "exception")

# Zeilen, die trotz eines Treffers in _ERR_KEYWORDS NICHT als ERROR getaggt
# werden -- harmlose Nebenwirkung von pacmans eigenem Mirror-Fallback beim
# Datenbank-Sync (pacman -Sy fürs lokale Repo): schlägt curl bei einem
# konfigurierten Mirror mit 404 fehl, weicht pacman selbst klaglos auf den
# nächsten aus (curls eigene Fehlermeldung enthält "error", ist aber kein
# Bau-Fehler). Der tatsächliche Bau-Erfolg hängt ohnehin am echten
# Exit-Code (siehe status = ... unten), nicht an dieser Zeilenfärbung --
# das hier betrifft nur, ob die Zeile in der Live-Log-Ansicht rot markiert
# wird (T-231-PACKAGES).
_HARMLESS_ERROR_PATTERNS = (
    re.compile(r"curl:\s*\(22\).*\b404\b"),
)


def _is_harmless_error_line(lower_line: str) -> bool:
    return any(p.search(lower_line) for p in _HARMLESS_ERROR_PATTERNS)


def _run(cmd: list[str], timeout: int = _TIMEOUT) -> tuple[int, str]:
    """Blockierender Subprocess-Aufruf ohne Live-Logging -- fuer Hilfskommandos
    (repo-add/repo-remove), die nicht Teil eines sichtbaren Bau-Vorgangs sind."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",  # makepkg/pacman-Ausgabe ist nicht garantiert UTF-8
            timeout=timeout,
        )
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired as e:
        return 1, f"Timeout nach {timeout}s\n{e.stdout or ''}"
    except FileNotFoundError:
        return 1, f"Kommando nicht gefunden: {cmd[0]!r} – ist Docker installiert?"
    except Exception as e:
        return 1, str(e)


def _run_streamed(cmd: list[str], timeout: int = _TIMEOUT) -> tuple[int, str]:
    """Führt einen Subprocess aus, schreibt jede Zeile sofort ins aktive activity_log
    (Live-Anzeige, egal ob manueller oder automatischer Bau) und gibt zusätzlich
    (rc, vollständige Ausgabe) zurück -- fürs last_log-Feld und Fehlermeldungen."""
    from astrapi_core.system.logger import log as _log

    lines: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",  # makepkg/pacman-Ausgabe ist nicht garantiert UTF-8
        )
        for line in proc.stdout:
            stripped = line.rstrip()
            lines.append(stripped)
            lower = stripped.strip().lower()
            is_err = lower and any(k in lower for k in _ERR_KEYWORDS) and not _is_harmless_error_line(lower)
            lvl = "ERROR" if is_err else "INFO"
            _log(lvl, stripped)
        proc.wait(timeout=timeout)
        rc = proc.returncode
        if rc != 0:
            _log("ERROR", f"Build fehlgeschlagen (Exit-Code {rc})")
        return rc, "\n".join(lines)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        msg = f"Timeout nach {timeout}s"
        _log("ERROR", msg)
        return 1, "\n".join([*lines, msg])
    except FileNotFoundError:
        msg = f"Kommando nicht gefunden: {cmd[0]!r} – ist Docker installiert?"
        _log("ERROR", msg)
        return 1, msg
    except Exception as e:
        _log("ERROR", str(e))
        return 1, str(e)


def _settings():
    from astrapi_core.ui.settings_registry import get_module as _get

    def s(key, default):
        return _get("archlinux", key, default)

    return s


def _arch_repo_path() -> str:
    """Gibt <repo_base>/arch/x86_64/ zurück und legt das Verzeichnis an."""
    from astrapi_packages._paths import _extra_disk, repo_dir as _repo_dir

    disk = _extra_disk()
    base = (Path(disk).resolve() / "arch") if disk else (_repo_dir().resolve() / "arch")
    path = base / "x86_64"
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o777)
    return str(path)


def build_package(item_id: str, notify: bool = False, own_log_entry: bool = True) -> None:
    """Baut ein einzelnes Arch-Paket im Docker-Container, mit Live-Output.

    own_log_entry=True (Default, automatischer Pfad via build_package_with_deps()
    -> update_all_packages()): öffnet einen eigenen log_activity()-Rahmen, damit
    jedes Paket in einem Scheduler-Lauf mit mehreren Paketen einen eigenen
    Eintrag bekommt statt alle Build-Zeilen in den äußeren Job-Eintrag zu
    schreiben (T-112). own_log_entry=False (manueller Pfad via run_single()):
    der Run-Router hat dafür bereits einen eigenen Kontext gesetzt
    (api/run.py) -- ein zweiter, verschachtelter Eintrag würde dessen eigene
    Status-Ermittlung leerlaufen lassen (history_finish() liest die Zeilen des
    Router-Eintrags, nicht die des verschachtelten).

    notify=True für den manuellen Bau-Weg (ein Klick auf ein einzelnes Paket) --
    da ist keine Sammel-Benachrichtigung im Spiel. Default False für den
    automatischen Pfad, dessen Sammel-Benachrichtigung am Ende von
    update_all_packages() bereits alle betroffenen Pakete nennt (T-117).
    """
    from astrapi_core.system.logger import log as _log

    from astrapi_packages.modules.archlinux import store

    item = store.get(item_id)
    if not item:
        log.warning("archlinux.build: Eintrag '%s' nicht gefunden", item_id)
        return

    s = _settings()
    image = (item.get("image") or "").strip() or s("default_image", "ctl/arch-builder:latest")
    repo_path = _arch_repo_path()
    repo_name = s("repo_name", "pkgctl")
    source_url = (item.get("source_url") or "").strip()
    source_subdir = (item.get("source_subdir") or "").strip()
    if not source_url:
        store.update(
            item_id,
            {
                "last_status": _status.ERROR,
                "last_run": _now(),
                "last_log": "Keine Git-URL angegeben.",
            },
        )
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
                "job",
                "archlinux",
                f"Arch-Linux-Paket bauen: {item_id}",
                status="running",
                item_id=item_id,
            )
            set_active_log_id(_act_id)
        except Exception:
            pass

    repo_vol = ["-v", f"{repo_path}:/home/makepkg/repo"]
    env_args = ["-e", f"REPO_NAME={repo_name}"]
    if source_subdir:
        env_args += ["-e", f"SOURCE_SUBDIR={source_subdir}"]

    cmd = [
        "docker",
        "run",
        "--rm",
        *repo_vol,
        *env_args,
        image,
        item_id,
        source_url,
    ]

    cmd_repr = f"$ {' '.join(cmd)}"
    log.info("archlinux.build: %s", " ".join(cmd))
    _log("INFO", cmd_repr)
    rc, raw_output = _run_streamed(cmd)
    output = f"{cmd_repr}\n\n{raw_output}"

    version = None
    repo_add_ok = True
    if rc == 0:
        version, repo_add_ok = _repo_add(repo_path, repo_name, item_id)
        if repo_add_ok:
            _trigger_mirror_sync(item_id)

    status = _status.OK if (rc == 0 and repo_add_ok) else _status.ERROR
    log.info("archlinux.build: %s → %s (rc=%d)", item_id, status, rc)

    update: dict = {
        "last_status": status,
        "last_run": _now(),
        "last_log": output[-20_000:],
    }
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
                    source="archlinux",
                )
            else:
                _notify.send(
                    title=f"Paket {item_id} – Fehler beim Bauen",
                    message=f"rc={rc}",
                    event=_notify.ERROR,
                    source="archlinux",
                )
        except Exception:
            pass


def _repo_add(repo_path: str, repo_name: str, item_id: str) -> tuple[str | None, bool]:
    """Fügt fertige Pakete zur Pacman-Repo-Datenbank hinzu.

    Gibt (erkannte Version "pkgver-pkgrel" oder None, ok) zurück. `ok=False`
    wenn kein Paket gefunden wurde oder `repo-add` es nicht lesen konnte --
    Letzteres passiert u.a. bei einer durch volle Festplatte abgeschnittenen
    Paketdatei: der Docker-Build selbst kann dabei trotzdem mit rc=0 enden,
    weil das Schreiben der (dann unvollstaendigen) Datei fuer den Container
    "erfolgreich" war. `repo-add` liest das Archiv zum Extrahieren der
    Metadaten tatsaechlich erneut ein und deckt eine solche Beschaedigung
    auf -- das ist deshalb hier die eigentliche Integritaetspruefung, nicht
    nur Datenbankpflege.
    """
    import glob as _glob

    pattern = os.path.join(repo_path, f"{item_id}-*.pkg.tar.*")
    pkgs = [
        p for p in _glob.glob(pattern) if not os.path.basename(p).startswith(f"{item_id}-debug-")
    ]
    if not pkgs:
        log.warning("archlinux.repo-add: keine Pakete gefunden für %s", item_id)
        return None, False
    db = os.path.join(repo_path, f"{repo_name}.db.tar.gz")
    rc, out = _run(["repo-add", db] + pkgs, timeout=60)
    if rc != 0:
        log.warning(
            "archlinux.repo-add fehlgeschlagen (Paketdatei evtl. unvollständig/beschädigt, "
            "z.B. durch volle Festplatte):\n%s",
            out,
        )
        return None, False
    # Symlink sicherstellen: pacman braucht <name>.db → <name>.db.tar.gz
    symlink = os.path.join(repo_path, f"{repo_name}.db")
    if not os.path.exists(symlink):
        os.symlink(f"{repo_name}.db.tar.gz", symlink)
    # Version aus Dateinamen extrahieren – von rechts parsen damit Split-Pakete
    # (z.B. ttf-ms-win11-auto-other-3:11.0.2-1-any.pkg.tar.zst) korrekt erkannt werden.
    # Format: {pkgname}-{pkgver}-{pkgrel}-{arch}.pkg.tar.{ext}
    # Von rechts: arch, pkgrel, pkgver (pkgver kann Epoch "N:" enthalten)
    try:
        import re as _re

        filename = os.path.basename(pkgs[0])
        # .pkg.tar.* Suffix entfernen
        stem = _re.sub(r"\.pkg\.tar\.\w+$", "", filename)
        parts = stem.rsplit("-", 3)  # maximal 3 Splits von rechts: pkgname, pkgver, pkgrel, arch
        # parts[-1]=arch, parts[-2]=pkgrel, parts[-3]=pkgver
        return f"{parts[-3]}-{parts[-2]}", True
    except Exception:
        return None, True


# ── Cleanup beim Löschen ───────────────────────────────────────────────────────


def delete_package(item_id: str, item: dict) -> None:
    """Entfernt Paketdateien und den Eintrag aus der Pacman-Repo-Datenbank.

    Löscht außerdem verwaiste Dependency-Einträge die nur von diesem Paket
    benötigt wurden.
    """
    import glob as _glob

    from astrapi_packages.modules.archlinux import store

    from .utils.dep_graph import find_orphan_deps

    s = _settings()
    repo_path = None
    repo_name = s("repo_name", "pkgctl")

    try:
        repo_path = _arch_repo_path()
    except OSError as e:
        log.warning("archlinux.delete: Repo-Pfad nicht erreichbar (%s)", e)

    # Verwaiste Deps ermitteln BEVOR der Eintrag gelöscht wird
    orphans = find_orphan_deps(item_id, store)

    # Pakete aus Pacman-DB entfernen
    db = os.path.join(repo_path, f"{repo_name}.db.tar.gz") if repo_path else None
    if db and os.path.exists(db):
        rc, out = _run(["repo-remove", db, item_id], timeout=60)
        if rc != 0:
            log.warning("archlinux.repo-remove fehlgeschlagen für %s:\n%s", item_id, out)

    # Paketdateien löschen (inkl. etwaiger Debug-Pakete)
    if repo_path:
        for pattern in [f"{item_id}-*.pkg.tar.*", f"{item_id}-debug-*.pkg.tar.*"]:
            for path in _glob.glob(os.path.join(repo_path, pattern)):
                try:
                    os.unlink(path)
                    log.info("archlinux.delete: %s gelöscht", path)
                except OSError as e:
                    log.warning("archlinux.delete: Konnte %s nicht löschen: %s", path, e)

    # Verwaiste Deps rekursiv bereinigen
    for orphan_id in orphans:
        orphan_item = store.get(orphan_id)
        if orphan_item is None:
            continue
        log.info("archlinux.delete: verwaiste Dep '%s' wird mitgelöscht", orphan_id)
        delete_package(orphan_id, orphan_item)
        store.delete(orphan_id)


# ── PKGBUILD-Dep-Sync ──────────────────────────────────────────────────────────


def _sync_pkgbuild_deps(item_id: str, store) -> None:
    """Liest depends/makedepends aus dem GitLab-PKGBUILD und legt fehlende AUR-Deps an.

    Nur für Pakete mit source_subdir (GitLab-Monorepo). Deps die nicht auf AUR
    existieren (z.B. offizielle Repo-Pakete) werden übersprungen.
    Aktualisiert außerdem upstream_version damit der Update-Badge nach einem
    manuellen Build korrekt verschwindet, sowie -- falls die PKGBUILD ein
    `_builder_image` vorgibt -- das Build-Image.
    """
    import json
    import urllib.request

    from astrapi_packages.modules.builder import sync_builder_image_from_pkgbuild

    from .ui.crud import _version_from_pkgbuild_url
    from .utils.dep_graph import autocreate_deps

    item = store.get(item_id) or {}
    source_url = item.get("source_url", "")
    source_sub = item.get("source_subdir", "")
    if not ("gitlab" in source_url and source_sub):
        return

    upstream_ver, pkgbuild_deps, builder_image = _version_from_pkgbuild_url(
        source_url, source_sub, item_id
    )
    if upstream_ver:
        store.update(item_id, {"upstream_version": upstream_ver})
    sync_builder_image_from_pkgbuild(item_id, item, store, builder_image, module="archlinux")
    if not pkgbuild_deps:
        return

    current_deps = set(d.strip() for d in (item.get("aur_deps") or "").split(",") if d.strip())
    pkgbuild_set = set(pkgbuild_deps)
    new_deps = [d for d in pkgbuild_deps if d not in current_deps]
    removed_deps = current_deps - pkgbuild_set  # in aur_deps aber nicht mehr im PKGBUILD

    # Neue Deps: nur anlegen wenn sie auf AUR existieren
    aur_new: list[str] = []
    if new_deps:
        aur_qs = "&".join(f"arg[]={d}" for d in new_deps)
        try:
            with urllib.request.urlopen(
                f"https://aur.archlinux.org/rpc/v5/info?{aur_qs}", timeout=8
            ) as r:
                aur_data = json.loads(r.read())
            aur_new = [res["Name"] for res in aur_data.get("results", [])]
        except Exception as e:
            log.warning("_sync_pkgbuild_deps: AUR-Check für '%s' fehlgeschlagen: %s", item_id, e)

    if aur_new or removed_deps:
        updated_deps = (current_deps | set(aur_new)) - removed_deps
        store.update(item_id, {"aur_deps": ", ".join(sorted(updated_deps))})
        if aur_new:
            autocreate_deps(item_id, {"aur_deps": ", ".join(sorted(updated_deps))}, store)
            log.info("_sync_pkgbuild_deps: '%s' – neue AUR-Deps: %s", item_id, ", ".join(aur_new))
        if removed_deps:
            log.info(
                "_sync_pkgbuild_deps: '%s' – Deps entfernt: %s", item_id, ", ".join(removed_deps)
            )


# ── Build mit Dep-Graph ────────────────────────────────────────────────────────


def build_package_with_deps(item_id: str) -> None:
    """Löst den Dependency-Graph auf und baut alle fehlenden Deps vor dem Hauptpaket."""
    from astrapi_packages.modules.archlinux import store

    from .utils.dep_graph import CyclicDependencyError, is_up_to_date, resolve_build_order

    _sync_pkgbuild_deps(item_id, store)

    repo_path = _arch_repo_path()

    try:
        build_order = resolve_build_order([item_id], store)
    except CyclicDependencyError as e:
        store.update(
            item_id,
            {
                "last_status": _status.ERROR,
                "last_run": _now(),
                "last_log": str(e),
            },
        )
        return

    # Pending-Status für alle noch zu bauenden Einträge setzen
    for pending_id in build_order:
        if not is_up_to_date(pending_id, repo_path):
            store.update(pending_id, {"last_status": _status.PENDING})

    # Deps zuerst bauen (alles außer dem Hauptpaket)
    for dep_id in build_order:
        if dep_id == item_id:
            continue
        if is_up_to_date(dep_id, repo_path):
            log.info("archlinux.build_with_deps: Dep '%s' bereits aktuell, übersprungen", dep_id)
            continue
        log.info("archlinux.build_with_deps: baue Dep '%s'", dep_id)
        build_package(dep_id)
        dep_item = store.get(dep_id)
        if dep_item and dep_item.get("last_status") == _status.ERROR:
            store.update(
                item_id,
                {
                    "last_status": _status.ERROR,
                    "last_run": _now(),
                    "last_log": f"Abhängigkeit '{dep_id}' konnte nicht gebaut werden.\n\n"
                    f"{dep_item.get('last_log', '')}",
                },
            )
            return

    build_package(item_id)


# ── Orphan-Markierung ──────────────────────────────────────────────────────────


def mark_orphan_deps() -> None:
    """Markiert verwaiste Dep-Einträge und hebt veraltete Markierungen auf.

    Ein Dep-Eintrag gilt als verwaist wenn er von keinem Paket mehr in
    aur_deps referenziert wird.  Das Feld 'orphaned' wird entsprechend gesetzt.
    """
    from astrapi_packages.modules.archlinux import store

    from .utils.dep_graph import find_all_orphan_deps

    all_items = store.list()
    orphan_ids = set(find_all_orphan_deps(store))

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
            log.info("mark_orphan_deps: '%s' als verwaist markiert", item_id)
        elif not is_orphan and was_orphan:
            store.update(item_id, {"orphaned": False})
            newly_adopted.append(item_id)
            log.info("mark_orphan_deps: '%s' ist nicht mehr verwaist", item_id)

    log.info(
        "mark_orphan_deps: %d neu verwaist, %d wieder referenziert",
        len(newly_orphaned),
        len(newly_adopted),
    )


# ── Update-Job ─────────────────────────────────────────────────────────────────


def update_all_packages() -> None:
    """Prüft auf neue Versionen und baut veraltete Pakete."""
    import json
    import time as _time
    import urllib.request
    from urllib.parse import quote

    from astrapi_packages.modules.archlinux import store

    _t0 = _time.time()
    _act_id = None
    try:
        from astrapi_core.system.activity_log import log_activity

        _act_id = log_activity("job", "archlinux", "Arch Linux: Aktualisieren", status="running")
    except Exception:
        pass

    def _finish(status: str, built: int = 0, error: str | None = None):
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
    if not all_items:
        _finish("ok")
        return

    built_ids = [k for k, v in all_items.items() if v.get("last_status") in _status.AUTO_UPDATE]

    # Wer nicht mitmacht, und warum -- frueher fiel beides stillschweigend
    # unter den Tisch (T-132).
    nie_gebaut = [k for k, v in all_items.items() if _status.ist_nie_gebaut(v.get("last_status"))]
    fehlerhaft = [k for k, v in all_items.items() if v.get("last_status") == _status.ERROR]
    if nie_gebaut:
        # G-017: der erste Bau wird von Hand angestossen und beobachtet.
        log.info(
            "update_all_packages: %d Paket(e) noch nie gebaut, erster Bau von Hand (G-017): %s",
            len(nie_gebaut), ", ".join(sorted(nie_gebaut)),
        )
    if fehlerhaft:
        log.warning(
            "update_all_packages: %d Paket(e) im Fehlerzustand, nicht automatisch erneut gebaut: %s",
            len(fehlerhaft), ", ".join(sorted(fehlerhaft)),
        )

    if not built_ids:
        _finish("ok")
        return

    # Pkg-Cache aktualisieren
    try:
        pkg_cache.refresh()
    except Exception as e:
        log.warning("update_all_packages: Cache-Refresh fehlgeschlagen: %s", e)

    # AUR: Batch-Abfrage für alle item_ids
    qs = "&".join(f"arg[]={quote(i)}" for i in built_ids)
    aur_versions: dict[str, str] = {}
    try:
        with urllib.request.urlopen(f"https://aur.archlinux.org/rpc/v5/info?{qs}", timeout=10) as r:
            data = json.loads(r.read())
        for result in data.get("results", []):
            aur_versions[result["Name"]] = result.get("Version", "")
    except Exception as e:
        log.warning("update_all_packages: AUR-Abfrage fehlgeschlagen: %s", e)

    # Repo-Versionen aus pkg_cache
    pkg_entries: dict[str, dict] = {}
    try:
        pkg_entries = {e.get("name"): e for e in pkg_cache.get_all() if e.get("name")}
    except Exception:
        pass

    # Phase 1: Versionen prüfen, tatsächliche Bau-Liste ermitteln -- welche
    # Kandidaten am Ende gebaut werden, steht erst nach dem Versionscheck fest.
    from .ui.crud import _version_from_pkgbuild_url

    to_build: list[str] = []
    for item_id in built_ids:
        upstream = ""
        if item_id in aur_versions:
            upstream = aur_versions[item_id]
        else:
            item = all_items[item_id]
            source_url = item.get("source_url", "")
            source_sub = item.get("source_subdir", "")
            if source_url and source_sub:
                upstream, _, _ = _version_from_pkgbuild_url(source_url, source_sub)
                _sync_pkgbuild_deps(item_id, store)

        if not upstream and item_id in pkg_entries:
            entry = pkg_entries[item_id]
            ver = entry.get("pkgver") or entry.get("version") or ""
            rel = entry.get("pkgrel", "")
            upstream = f"{ver}-{rel}" if rel else ver

        if upstream:
            store.update(item_id, {"upstream_version": upstream})

        current = (store.get(item_id) or {}).get("last_version", "")
        if upstream and upstream != current:
            log.info(
                "update_all_packages: %s ist veraltet (%s → %s), zum Bau vorgemerkt",
                item_id, current, upstream,
            )
            to_build.append(item_id)

    # Phase 2: die ganze Bau-Liste auf einmal als eingeplant markieren, bevor
    # das erste Paket drankommt -- statt dass jedes Paket erst beim eigenen
    # Bau-Start aus dem Nichts auftaucht.
    for item_id in to_build:
        store.update(item_id, {"last_status": _status.PENDING})

    # Phase 3: nacheinander bauen. build_package_with_deps() markiert für die
    # eigene Dependency-Kette weiterhin PENDING (s.o.) -- unverändert, hier
    # kommt nur die vorab gesetzte Markierung der Hauptpakete dazu.
    built_count = 0
    errors = []
    for item_id in to_build:
        build_package_with_deps(item_id)
        result_status = (store.get(item_id) or {}).get("last_status", "")
        if result_status == _status.OK:
            built_count += 1
        else:
            errors.append(item_id)

    final_status = "error" if errors else "ok"
    error_msg = f"Fehler bei: {', '.join(errors)}" if errors else None
    _finish(final_status, built=built_count, error=error_msg)

    try:
        from astrapi_core.modules.notify import engine as _notify

        if errors:
            _notify.send(
                title="Arch Linux: Aktualisieren – Fehler",
                message=f"{built_count} gebaut, Fehler bei: {', '.join(errors)}",
                event=_notify.ERROR,
                source="archlinux",
            )
        elif built_count:
            _notify.send(
                title=f"Arch Linux: {built_count} Paket(e) aktualisiert",
                message=f"{built_count} von {len(built_ids)} geprüften Paketen wurden neu gebaut.",
                event=_notify.SUCCESS,
                source="archlinux",
            )
    except Exception:
        pass


# ── Zentraler Run-Router: run_single ─────────────────────────────────────────


def run_single(item_id: str) -> None:
    """Wird vom zentralen Run-Router aufgerufen (der bereits einen eigenen
    activity_log-Kontext gesetzt hat, siehe api/run.py).

    Löst den Dependency-Graph auf und baut alle fehlenden Deps vor dem
    Hauptpaket. build_package() schreibt dabei direkt in den vom Router
    vorgegebenen Kontext (own_log_entry=False) statt einen eigenen zu öffnen.
    """
    from astrapi_core.system.logger import log as _log

    from astrapi_packages.modules.archlinux import store as _store

    from .utils.dep_graph import CyclicDependencyError, is_up_to_date, resolve_build_order

    item = _store.get(item_id)
    if not item:
        _log("ERROR", f"Paket '{item_id}' nicht gefunden")
        return

    _sync_pkgbuild_deps(item_id, _store)

    try:
        build_order = resolve_build_order([item_id], _store)
    except CyclicDependencyError as e:
        _store.update(item_id, {"last_status": _status.ERROR, "last_run": _now()})
        _log("ERROR", str(e))
        return

    repo_path = _arch_repo_path()

    # Pending-Status für alle noch zu bauenden Einträge setzen
    for pid in build_order:
        if not is_up_to_date(pid, repo_path):
            _store.update(pid, {"last_status": _status.PENDING})

    # Deps zuerst bauen
    for dep_id in build_order:
        if dep_id == item_id:
            continue
        if is_up_to_date(dep_id, repo_path):
            _log("INFO", f"Dep '{dep_id}' bereits aktuell, übersprungen")
            continue
        _log("INFO", f"Baue Abhängigkeit: {dep_id}")
        build_package(dep_id, notify=True, own_log_entry=False)
        dep_item = _store.get(dep_id)
        if dep_item and dep_item.get("last_status") == _status.ERROR:
            _store.update(item_id, {"last_status": _status.ERROR, "last_run": _now()})
            _log("ERROR", f"Abhängigkeit '{dep_id}' konnte nicht gebaut werden.")
            return

    _log("INFO", f"Baue: {item_id}")
    build_package(item_id, notify=True, own_log_entry=False)


def _trigger_mirror_sync(item_id: str) -> None:
    try:
        from astrapi_core.ui.settings_registry import get_module as _gm
        url = (_gm("archlinux", "mirror_trigger_url", default="") or "").strip()
        if not url:
            return
        import urllib.request
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5):
            pass
        log.info("archlinux.build: mirror-sync ausgelöst → %s", url)
    except Exception as e:
        log.warning("archlinux.build: mirror-sync fehlgeschlagen (%s): %s", item_id, e)

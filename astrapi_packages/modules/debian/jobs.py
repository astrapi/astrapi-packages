"""astrapi_packages.modules.debian.jobs – Build-Logik für Debian-Pakete."""

import logging
import subprocess
from pathlib import Path

from astrapi_core.system.format import fmt_now as _now

from astrapi_packages.api import status as _status
from astrapi_packages.modules.debian.utils import pkg_cache

log = logging.getLogger(__name__)

_TIMEOUT = 3600


_ERR_KEYWORDS = ("error", "fehler", "not found", "failed", "command not found", "exception")


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
            errors="replace",  # dpkg/apt-Ausgabe ist nicht garantiert UTF-8
        )
        for line in proc.stdout:
            stripped = line.rstrip()
            lines.append(stripped)
            lower = stripped.strip().lower()
            lvl = "ERROR" if lower and any(k in lower for k in _ERR_KEYWORDS) else "INFO"
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
        return _get("debian", key, default)

    return s


def _repo_path() -> Path:
    from astrapi_packages._paths import _extra_disk, repo_dir as _repo_dir

    disk = _extra_disk()
    base = (Path(disk).resolve() / "debian") if disk else (_repo_dir() / "debian").resolve()
    base.mkdir(parents=True, exist_ok=True)
    base.chmod(0o777)
    return base


def _build_cmd(
    item_id: str, source_url: str, source_subdir: str, image: str, repo_path: Path
) -> list[str]:
    """Baut das docker-run-Kommando für den Debian-Bau -- eigene Funktion, damit das
    lange Shell-Script nicht den Ablauf von build_package() verschluckt."""
    subdir = source_subdir or item_id

    # Shell-Script: PKGBUILD lesen → .deb bauen
    # Python-format-Platzhalter: {source_url}, {item_id}
    # Bash-Variablen: ${{...}} → ${...}
    build_script = """\
set -e

# Repository klonen
git clone --depth=1 '{source_url}' /build/src

# In das Paket-Unterverzeichnis wechseln
cd /build/src/{subdir}
[[ ! -f PKGBUILD ]] && {{ echo "FEHLER: PKGBUILD nicht gefunden in $(pwd)"; exit 1; }}

# Variablen-Stand vor dem Einlesen merken, um gleich alle von der PKGBUILD
# neu gesetzten Variablen zu erkennen -- auch eigene Hilfsvariablen
# (z.B. _url/_tarball/_sha256), nicht nur eine feste Standardliste.
_vars_before=$(compgen -v)

# PKGBUILD einlesen
source ./PKGBUILD

# Von der PKGBUILD neu gesetzte Variablen (Standardfelder + eigene) fuer die
# fakeroot-Subshell weiter unten merken -- die startet als neuer bash-Prozess
# und erbt nur exportierte Variablen, PKGBUILD-Variablen sind aber nicht
# exportiert.
_pkgbuild_vars=$(comm -13 <(echo "$_vars_before" | sort) <(compgen -v | sort) | tr '\n' ' ')

# Umgebungsvariablen analog zu makepkg
export srcdir="$(pwd)"
export startdir="$(pwd)"

# Architektur: PKGBUILD 'any' → Debian 'all'
DEB_ARCH="${{arch[0]:-all}}"
[[ "$DEB_ARCH" == "any" ]] && DEB_ARCH="all"
[[ "$DEB_ARCH" == "x86_64" ]] && DEB_ARCH="amd64"
[[ "$DEB_ARCH" == "aarch64" ]] && DEB_ARCH="arm64"

# Staging-Verzeichnis vorbereiten
STAGING=/build/staging
rm -rf "$STAGING"
mkdir -p "$STAGING/DEBIAN"
export pkgdir="$STAGING"

if declare -f prepare &>/dev/null; then
    echo "=== Starte prepare() ==="
    prepare
    echo "=== prepare() abgeschlossen ==="
fi

if declare -f build &>/dev/null; then
    echo "=== Starte build() ==="
    build
    echo "=== build() abgeschlossen ==="
fi

if declare -f check &>/dev/null; then
    echo "=== Starte check() ==="
    check
    echo "=== check() abgeschlossen ==="
fi

echo "=== Starte package() ==="
fakeroot -- bash -c "$(declare -p $_pkgbuild_vars pkgdir srcdir startdir 2>/dev/null || true); $(declare -f package); package"
echo "=== package() abgeschlossen ==="

# DEBIAN/control erzeugen
{{
  echo "Package: $pkgname"
  echo "Version: ${{pkgver}}-${{pkgrel}}"
  echo "Architecture: $DEB_ARCH"
  echo "Maintainer: ${{maintainer:-astrapi <astrapi@localhost>}}"
  echo "Description: ${{pkgdesc:-(no description)}}"
  if [[ ${{#depends[@]}} -gt 0 ]]; then
    deps=$(printf '%s, ' "${{depends[@]}}")
    echo "Depends: ${{deps%, }}"
  fi
}} > "$STAGING/DEBIAN/control"

echo "--- DEBIAN/control ---"
cat "$STAGING/DEBIAN/control"
echo "---"

# .deb paketieren
DEB_FILE="/repo/${{pkgname}}_${{pkgver}}-${{pkgrel}}_${{DEB_ARCH}}.deb"
fakeroot dpkg-deb --build "$STAGING" "$DEB_FILE"
echo "Gebaut: $DEB_FILE"
""".format(source_url=source_url, item_id=item_id, subdir=subdir)

    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{repo_path}:/repo",
        image,
        "bash",
        "-c",
        build_script,
    ]


def build_package(item_id: str, notify: bool = True, own_log_entry: bool = True) -> None:
    """Baut ein Debian-Paket im Docker-Container und legt die .deb-Datei ins Repository.

    notify=False fuer Aufrufer, die selbst eine Sammel-Benachrichtigung
    verschicken (update_all_packages(), T-117) -- sonst kaeme zusaetzlich zur
    Sammel-Nachricht noch eine Einzelnachricht je Paket, die dieselbe
    Information nur nochmal enthaelt. Der manuelle Bau-Weg (run_single(), ein
    Klick auf ein einzelnes Paket) behaelt den Default True.

    own_log_entry=True (Default, automatischer Pfad via update_all_packages()):
    oeffnet einen eigenen log_activity()-Rahmen, damit jedes Paket in einem
    Scheduler-Lauf mit mehreren Paketen einen eigenen Eintrag bekommt statt
    alle Build-Zeilen in den aeusseren Job-Eintrag zu schreiben (T-136).
    own_log_entry=False (manueller Pfad via run_single()): der Run-Router hat
    dafuer bereits einen eigenen Kontext gesetzt (api/run.py) -- ein zweiter,
    verschachtelter Eintrag wuerde dessen eigene Status-Ermittlung leerlaufen
    lassen (history_finish() liest die Zeilen des Router-Eintrags, nicht die
    des verschachtelten).
    """
    from astrapi_core.system.logger import log as _log

    from astrapi_packages.modules.debian import store

    item = store.get(item_id)
    if not item:
        log.warning("debian.build: Eintrag '%s' nicht gefunden", item_id)
        return

    s = _settings()
    image = (item.get("image") or "").strip() or s("default_image", "ctl/debian-builder:latest")
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

    repo_path = _repo_path()
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
                "debian",
                f"Debian-Paket bauen: {item_id}",
                status="running",
                item_id=item_id,
            )
            set_active_log_id(_act_id)
        except Exception:
            pass

    cmd = _build_cmd(item_id, source_url, source_subdir, image, repo_path)
    cmd_repr = f"$ docker run --rm -v {repo_path}:/repo {image} bash -c <build_script>"
    log.info("debian.build: %s", " ".join(cmd))
    _log("INFO", cmd_repr)
    rc, raw_output = _run_streamed(cmd)
    output = f"{cmd_repr}\n\n{raw_output}"

    if rc == 0:
        _cleanup_old_debs(repo_path, item_id)
        _update_packages_index(repo_path)
        _trigger_mirror_sync(item_id)

    version = _extract_version(repo_path, item_id) if rc == 0 else None
    status = _status.OK if rc == 0 else _status.ERROR
    log.info("debian.build: %s → %s (rc=%d)", item_id, status, rc)

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

    try:
        from astrapi_core.modules.notify import engine as _notify

        if not notify:
            pass
        elif status == _status.OK:
            ver_info = f" ({version})" if version else ""
            _notify.send(
                title=f"Debian: {item_id} erfolgreich gebaut{ver_info}",
                message="Status: ok",
                event=_notify.SUCCESS,
                source="debian",
            )
        else:
            _notify.send(
                title=f"Debian: {item_id} – Fehler beim Bauen",
                message=output[-400:].strip(),
                event=_notify.ERROR,
                source="debian",
            )
    except Exception:
        pass


def _write_release_file(repo_path: Path) -> None:
    """Erzeugt eine minimale Release-Datei mit MD5/SHA1/SHA256-Checksums (kein GPG)."""
    import datetime
    import hashlib

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S UTC")
    candidates = ["Packages", "Packages.gz"]

    def _sums(fname: str) -> tuple[str, str, str, int] | None:
        p = repo_path / fname
        if not p.exists():
            return None
        data = p.read_bytes()
        return (
            hashlib.md5(data).hexdigest(),
            hashlib.sha1(data).hexdigest(),
            hashlib.sha256(data).hexdigest(),
            len(data),
        )

    # Einmal hashen und wiederverwenden – _sums() liest die ganze Datei ein
    sums = {f: s for f in candidates if (s := _sums(f)) is not None}

    lines = [
        "Origin: Simpsons",
        "Label: Simpsons",
        "Suite: ./",
        f"Date: {now}",
        "Acquire-By-Hash: no",
    ]
    for algo, idx in [("MD5Sum", 0), ("SHA1", 1), ("SHA256", 2)]:
        lines.append(f"{algo}:")
        for fname, s in sums.items():
            lines.append(f" {s[idx]}  {s[3]}  {fname}")

    (repo_path / "Release").write_text("\n".join(lines) + "\n")
    log.info("debian: Release-Datei geschrieben")


def _sign_release(repo_path: Path) -> None:
    """Signiert Release → InRelease + Release.gpg, falls signing_key_id konfiguriert."""
    s = _settings()
    key_id = s("signing_key_id", "").strip()
    if not key_id:
        return
    release_file = repo_path / "Release"
    if not release_file.exists():
        return
    # InRelease (clearsigned – primär für apt)
    try:
        r = subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--clearsign",
                "-u",
                key_id,
                "--output",
                str(repo_path / "InRelease"),
                str(release_file),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            log.warning("debian: gpg --clearsign fehlgeschlagen (Key: %s):\n%s", key_id, r.stdout)
            return
        log.info("debian: InRelease signiert (Key: %s)", key_id)
    except FileNotFoundError:
        log.warning("debian: gpg nicht gefunden – Release-Signierung übersprungen")
        return
    except Exception as e:
        log.warning("debian: InRelease-Signierung fehlgeschlagen: %s", e)
        return
    # Release.gpg (detached – Kompatibilität mit älteren Clients)
    try:
        r = subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--armor",
                "--detach-sign",
                "-u",
                key_id,
                str(release_file),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            log.warning("debian: gpg --detach-sign fehlgeschlagen:\n%s", r.stdout)
    except Exception as e:
        log.warning("debian: Release.gpg fehlgeschlagen: %s", e)


def _update_packages_index(repo_path: Path) -> None:
    """Aktualisiert den APT-Packages-Index (läuft im debian-builder Container)."""
    s = _settings()
    image = s("default_image", "ctl/debian-builder:latest")
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{repo_path}:/repo",
        image,
        "bash",
        "-c",
        "cd /repo"
        " && dpkg-scanpackages --multiversion . > Packages 2>/dev/null"
        " && gzip -fk Packages"
        " && apt-ftparchive release . > Release"
        " && echo 'Index und Release aktualisiert'",
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120
        )
        if result.returncode == 0:
            log.info("debian: Packages-Index aktualisiert")
            _sign_release(repo_path)
        else:
            log.warning("debian: dpkg-scanpackages fehlgeschlagen:\n%s", result.stdout)
            # Fallback: Python-basierte Release-Datei
            _write_release_file(repo_path)
            _sign_release(repo_path)
    except Exception as e:
        log.warning("debian: Index-Aktualisierung fehlgeschlagen: %s", e)
        _write_release_file(repo_path)
        _sign_release(repo_path)


def _cleanup_old_debs(repo_path: Path, item_id: str) -> None:
    """Entfernt aeltere .deb-Dateien desselben Pakets, behaelt nur die zuletzt gebaute.

    Anders als beim Archlinux-Modul (repo-add --remove raeumt Alt-Dateien
    automatisch mit auf) baut der Debian-Build-Schritt jede Version unter
    eigenem Dateinamen (<pkgname>_<pkgver>-<pkgrel>_<arch>.deb) -- ohne
    dieses Aufraeumen blieben aeltere Versionen dauerhaft im Repo liegen.
    Sortierung nach mtime statt Versionsvergleich, weil die zuletzt gebaute
    Datei garantiert die juengste ist, unabhaengig vom Versionsschema.
    """
    debs = sorted(repo_path.glob(f"{item_id}_*.deb"), key=lambda p: p.stat().st_mtime)
    for old in debs[:-1]:
        try:
            old.unlink()
            log.info("debian.build: alte Paketdatei entfernt: %s", old.name)
        except Exception as e:
            log.warning("debian.build: konnte %s nicht entfernen: %s", old.name, e)


def _extract_version(repo_path: Path, item_id: str) -> str | None:
    """Liest die Version aus dem neuesten .deb-Dateinamen."""
    debs = sorted(repo_path.glob(f"{item_id}_*.deb"))
    if not debs:
        return None
    try:
        # Format: <name>_<version>_<arch>.deb
        stem = debs[-1].stem
        parts = stem.split("_", 2)
        return parts[1] if len(parts) >= 2 else None
    except Exception:
        return None


# ── Zentraler Run-Router: run_single ─────────────────────────────────────────


# ── PKGBUILD-Dep-Sync ──────────────────────────────────────────────────────────


def _sync_pkgbuild_deps(item_id: str, store) -> None:
    """Liest depends/makedepends aus dem GitLab-PKGBUILD und legt fehlende AUR-Deps an.

    Nur für Pakete mit source_subdir (GitLab-Monorepo). Deps die nicht auf AUR
    existieren (z.B. offizielle Repo-Pakete) werden übersprungen.
    Aktualisiert außerdem upstream_version damit der Update-Badge nach einem
    manuellen Build korrekt verschwindet.

    1:1 nach archlinux/jobs.py::_sync_pkgbuild_deps -- gleiches PKGBUILD-
    basiertes Abhängigkeitsmodell (Bridge-Ansatz).
    """
    import json
    import urllib.request

    from .ui.crud import _version_and_deps_from_pkgbuild_url
    from .utils.dep_graph import autocreate_deps

    item = store.get(item_id) or {}
    source_url = item.get("source_url", "")
    source_sub = item.get("source_subdir", "")
    if not ("gitlab" in source_url and source_sub):
        return

    upstream_ver, pkgbuild_deps = _version_and_deps_from_pkgbuild_url(source_url, source_sub)
    if upstream_ver:
        store.update(item_id, {"upstream_version": upstream_ver})
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
            log.warning("_sync_pkgbuild_deps(debian): AUR-Check für '%s' fehlgeschlagen: %s", item_id, e)

    if aur_new or removed_deps:
        updated_deps = (current_deps | set(aur_new)) - removed_deps
        store.update(item_id, {"aur_deps": ", ".join(sorted(updated_deps))})
        if aur_new:
            autocreate_deps(item_id, {"aur_deps": ", ".join(sorted(updated_deps))}, store)
            log.info("_sync_pkgbuild_deps(debian): '%s' – neue Deps: %s", item_id, ", ".join(aur_new))
        if removed_deps:
            log.info(
                "_sync_pkgbuild_deps(debian): '%s' – Deps entfernt: %s", item_id, ", ".join(removed_deps)
            )


# ── Build mit Dep-Graph ────────────────────────────────────────────────────────


def build_package_with_deps(item_id: str, notify: bool = True) -> None:
    """Löst den Dependency-Graph auf und baut alle fehlenden Deps vor dem
    Hauptpaket. 1:1 nach archlinux/jobs.py::build_package_with_deps."""
    from astrapi_packages.modules.debian import store

    from .utils.dep_graph import CyclicDependencyError, is_up_to_date, resolve_build_order

    _sync_pkgbuild_deps(item_id, store)

    repo_path = _repo_path()

    try:
        build_order = resolve_build_order([item_id], store)
    except CyclicDependencyError as e:
        store.update(
            item_id,
            {"last_status": _status.ERROR, "last_run": _now(), "last_log": str(e)},
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
            log.info("debian.build_with_deps: Dep '%s' bereits aktuell, übersprungen", dep_id)
            continue
        log.info("debian.build_with_deps: baue Dep '%s'", dep_id)
        build_package(dep_id, notify=notify)
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

    build_package(item_id, notify=notify)


# ── Orphan-Markierung ──────────────────────────────────────────────────────────


def mark_orphan_deps() -> None:
    """Markiert verwaiste Dep-Einträge und hebt veraltete Markierungen auf.

    1:1 nach archlinux/jobs.py::mark_orphan_deps.
    """
    from astrapi_packages.modules.debian import store

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
            log.info("mark_orphan_deps(debian): '%s' als verwaist markiert", item_id)
        elif not is_orphan and was_orphan:
            store.update(item_id, {"orphaned": False})
            newly_adopted.append(item_id)
            log.info("mark_orphan_deps(debian): '%s' ist nicht mehr verwaist", item_id)

    log.info(
        "mark_orphan_deps(debian): %d neu verwaist, %d wieder referenziert",
        len(newly_orphaned),
        len(newly_adopted),
    )


# ── Zentraler Run-Router: run_single ─────────────────────────────────────────


def run_single(item_id: str) -> None:
    """Einstiegspunkt für den zentralen Run-Router (der bereits einen eigenen
    activity_log-Kontext gesetzt hat, siehe api/run.py).

    Löst den Dependency-Graph auf und baut alle fehlenden Deps vor dem
    Hauptpaket. build_package() schreibt dabei direkt in den vom Router
    vorgegebenen Kontext (own_log_entry=False) statt einen eigenen zu öffnen.
    """
    from astrapi_core.system.logger import log as _log

    from astrapi_packages.modules.debian import store as _store

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

    repo_path = _repo_path()

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


def update_all_packages() -> None:
    """Prüft auf neue Versionen und baut veraltete Debian-Pakete neu."""
    import time as _time

    from astrapi_packages.modules.debian import store

    _t0 = _time.time()
    _act_id = None
    try:
        from astrapi_core.system.activity_log import log_activity

        _act_id = log_activity("job", "debian", "Debian: Aktualisieren", status="running")
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

    # Wer nicht mitmacht, und warum -- frueher fiel beides stillschweigend
    # unter den Tisch (T-132).
    nie_gebaut = [k for k, v in all_items.items() if _status.ist_nie_gebaut(v.get("last_status"))]
    fehlerhaft = [k for k, v in all_items.items() if v.get("last_status") == _status.ERROR]
    if nie_gebaut:
        # G-017: der erste Bau wird von Hand angestossen und beobachtet.
        log.info(
            "debian.update_all: %d Paket(e) noch nie gebaut, erster Bau von Hand (G-017): %s",
            len(nie_gebaut), ", ".join(sorted(nie_gebaut)),
        )
    if fehlerhaft:
        log.warning(
            "debian.update_all: %d Paket(e) im Fehlerzustand, nicht automatisch erneut gebaut: %s",
            len(fehlerhaft), ", ".join(sorted(fehlerhaft)),
        )

    if not built_ids:
        _finish("ok")
        return

    # pkg_cache aktualisieren
    try:
        pkg_cache.refresh()
    except Exception as e:
        log.warning("debian.update_all: pkg_cache-Refresh fehlgeschlagen: %s", e)

    cache_entries: dict[str, dict] = {}
    try:
        cache_entries = {e["name"]: e for e in pkg_cache.get_all() if e.get("name")}
    except Exception:
        pass

    from .ui.crud import _pkgbuild_info

    # Phase 1: Versionen prüfen, tatsächliche Bau-Liste ermitteln -- welche
    # Kandidaten am Ende gebaut werden, steht erst nach dem Versionscheck fest.
    to_build: list[str] = []
    for item_id in built_ids:
        entry = cache_entries.get(item_id, {})
        pkgver = entry.get("pkgver", "")
        pkgrel = entry.get("pkgrel", "")
        upstream = f"{pkgver}-{pkgrel}" if pkgver and pkgrel else pkgver

        if not upstream:
            source_url = all_items[item_id].get("source_url", "").strip()
            if source_url:
                upstream = _pkgbuild_info(source_url, item_id).get("version", "")

        if upstream:
            store.update(item_id, {"upstream_version": upstream})

        current = (store.get(item_id) or {}).get("last_version", "")
        if not upstream:
            # Weder pkg_cache noch PKGBUILD liefern eine Version. Ein Neubau
            # kann daran nichts aendern -- beim naechsten Lauf ist die Lage
            # identisch. Frueher fiel der Code hier durch und baute jedes Mal
            # neu. Das Paket ist wegen last_status == "ok" nachweislich schon
            # einmal gebaut worden; von Hand bauen bleibt moeglich.
            log.warning(
                "debian.update_all: %s uebersprungen - keine Versionsinfo "
                "(weder pkg_cache noch PKGBUILD)",
                item_id,
            )
            continue
        if upstream == current:
            log.info("debian.update_all: %s ist aktuell (%s)", item_id, current)
            continue

        log.info(
            "debian.update_all: %s veraltet (%s → %s), zum Bau vorgemerkt",
            item_id, current, upstream,
        )
        to_build.append(item_id)

    # Phase 2: die ganze Bau-Liste auf einmal als eingeplant markieren, bevor
    # das erste Paket drankommt -- analog zu archlinux (dort über
    # build_package_with_deps() bereits vorhanden; debian kannte PENDING
    # bisher gar nicht, da es keine eigene Dependency-Queue hat).
    for item_id in to_build:
        store.update(item_id, {"last_status": _status.PENDING})

    # Phase 3: nacheinander bauen. build_package_with_deps() loest dabei den
    # Dependency-Graph auf und baut fehlende/veraltete Deps zuerst.
    built_count = 0
    errors: list[str] = []
    for item_id in to_build:
        try:
            build_package_with_deps(item_id, notify=False)
            if (store.get(item_id) or {}).get("last_status") == _status.OK:
                built_count += 1
            else:
                errors.append(item_id)
        except Exception as e:
            log.error("debian.update_all: Fehler bei %s: %s", item_id, e)
            errors.append(item_id)

    _finish("error" if errors else "ok", built=built_count, error="\n".join(errors) or None)

    # Eine Sammel-Benachrichtigung statt einer je Paket (T-117): nennt bereits
    # alle betroffenen Pakete, redundante Einzelnachrichten aus build_package()
    # sind dafuer mit notify=False oben unterdrueckt.
    try:
        from astrapi_core.modules.notify import engine as _notify

        if errors:
            _notify.send(
                title="Debian: Aktualisieren – Fehler",
                message=f"{built_count} gebaut, Fehler bei: {', '.join(errors)}",
                event=_notify.ERROR,
                source="debian",
            )
        elif built_count:
            _notify.send(
                title=f"Debian: {built_count} Paket(e) aktualisiert",
                message=f"{built_count} von {len(built_ids)} geprüften Paketen wurden neu gebaut.",
                event=_notify.SUCCESS,
                source="debian",
            )
    except Exception:
        pass


def delete_package(item_id: str, item: dict) -> None:
    """Entfernt .deb-Dateien aus dem Repository-Verzeichnis und aktualisiert den Index.

    Löscht außerdem verwaiste Dependency-Einträge die nur von diesem Paket
    benötigt wurden (1:1 nach archlinux/jobs.py::delete_package).
    """
    from astrapi_packages.modules.debian import store

    from .utils.dep_graph import find_orphan_deps

    # Verwaiste Deps ermitteln BEVOR der Eintrag geloescht wird
    orphans = find_orphan_deps(item_id, store)

    try:
        repo_path = _repo_path()
        removed = 0
        for deb in list(repo_path.glob(f"{item_id}_*.deb")):
            try:
                deb.unlink()
                log.info("debian.delete: %s gelöscht", deb.name)
                removed += 1
            except OSError as e:
                log.warning("debian.delete: Konnte %s nicht löschen: %s", deb.name, e)
        if removed:
            _update_packages_index(repo_path)
    except Exception as e:
        log.warning("debian.delete: %s", e)

    for orphan_id in orphans:
        orphan_item = store.get(orphan_id)
        if orphan_item is None:
            continue
        log.info("debian.delete: verwaiste Dep '%s' wird mitgelöscht", orphan_id)
        delete_package(orphan_id, orphan_item)
        store.delete(orphan_id)


def _trigger_mirror_sync(item_id: str) -> None:
    try:
        from astrapi_core.ui.settings_registry import get_module as _gm
        url = (_gm("debian", "mirror_trigger_url", default="") or "").strip()
        if not url:
            return
        import urllib.request
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5):
            pass
        log.info("debian.build: mirror-sync ausgelöst → %s", url)
    except Exception as e:
        log.warning("debian.build: mirror-sync fehlgeschlagen (%s): %s", item_id, e)

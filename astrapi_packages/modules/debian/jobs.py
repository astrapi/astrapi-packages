"""astrapi_packages.modules.debian.jobs – Build-Logik für Debian-Pakete."""

import logging
import subprocess
from pathlib import Path

from astrapi_core.system.format import fmt_now as _now

log = logging.getLogger(__name__)

_TIMEOUT = 3600


_ERR_KEYWORDS = ("error", "fehler", "not found", "failed", "command not found", "exception")


def _pipe_to_activity_log(cmd_repr: str, raw_output: str, rc: int) -> None:
    """Schreibt Subprocess-Output ins aktive activity_log (für Log-Modal)."""
    try:
        from astrapi_core.system.logger import log as _alog

        _alog("INFO", cmd_repr)
        for line in raw_output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            lvl = "ERROR" if any(k in lower for k in _ERR_KEYWORDS) else "INFO"
            _alog(lvl, stripped)
        if rc != 0:
            _alog("ERROR", f"Build fehlgeschlagen (Exit-Code {rc})")
    except Exception:
        pass


def _run(cmd: list[str], timeout: int = _TIMEOUT) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",  # dpkg/apt-Ausgabe ist nicht garantiert UTF-8
            timeout=timeout,
        )
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired as e:
        return 1, f"Timeout nach {timeout}s\n{e.stdout or ''}"
    except FileNotFoundError:
        return 1, f"Kommando nicht gefunden: {cmd[0]!r} – ist Docker installiert?"
    except Exception as e:
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


def build_package(item_id: str) -> None:
    """Baut ein Debian-Paket im Docker-Container und legt die .deb-Datei ins Repository."""
    from astrapi_packages.modules.debian import store

    item = store.get(item_id)
    if not item:
        log.warning("debian.build: Eintrag '%s' nicht gefunden", item_id)
        return

    s = _settings()
    image = s("default_image", "ctl/debian-builder:latest")
    source_url = (item.get("source_url") or "").strip()
    source_subdir = (item.get("source_subdir") or "").strip()
    subdir = source_subdir or item_id

    if not source_url:
        store.update(
            item_id,
            {"last_status": "error", "last_run": _now(), "last_log": "Keine Git-URL angegeben."},
        )
        return

    repo_path = _repo_path()
    store.update(item_id, {"last_status": "building", "last_run": _now()})

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

# PKGBUILD einlesen
source ./PKGBUILD

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
fakeroot -- bash -c "$(declare -p pkgname pkgver pkgrel pkgdesc arch maintainer pkgdir srcdir startdir 2>/dev/null || true); $(declare -f package); package"
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

    cmd = [
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
    log.info("debian.build: %s", " ".join(cmd))
    rc, raw_output = _run(cmd)
    cmd_repr = f"$ docker run --rm -v {repo_path}:/repo {image} bash -c <build_script>"
    _pipe_to_activity_log(cmd_repr, raw_output, rc)
    output = f"{cmd_repr}\n\n{raw_output}"

    if rc == 0:
        _update_packages_index(repo_path)
        _trigger_mirror_sync(item_id)

    version = _extract_version(repo_path, item_id) if rc == 0 else None
    status = "ok" if rc == 0 else "error"
    log.info("debian.build: %s → %s (rc=%d)", item_id, status, rc)

    update: dict = {
        "last_status": status,
        "last_run": _now(),
        "last_log": output[-20_000:],
    }
    if version:
        update["last_version"] = version
    store.update(item_id, update)

    try:
        from astrapi_core.modules.notify import engine as _notify

        if status == "ok":
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


def run_single(item_id: str) -> None:
    """Einstiegspunkt für den zentralen Run-Router."""
    build_package(item_id)


def update_all_packages() -> None:
    """Prüft auf neue Versionen und baut veraltete Debian-Pakete neu."""
    import sys
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
    built_ids = [k for k, v in all_items.items() if v.get("last_status") == "ok"]
    if not built_ids:
        _finish("ok")
        return

    # pkg_cache aktualisieren
    pkg_cache = sys.modules.get("_debian_pkg_cache")
    try:
        if pkg_cache:
            pkg_cache.refresh()
    except Exception as e:
        log.warning("debian.update_all: pkg_cache-Refresh fehlgeschlagen: %s", e)

    cache_entries: dict[str, dict] = {}
    if pkg_cache:
        try:
            cache_entries = {e["name"]: e for e in pkg_cache.get_all() if e.get("name")}
        except Exception:
            pass

    from .ui.crud import _pkgbuild_info

    built_count = 0
    errors: list[str] = []
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
        if upstream and upstream == current:
            log.info("debian.update_all: %s ist aktuell (%s)", item_id, current)
            continue

        log.info("debian.update_all: %s veraltet (%s → %s), baue …", item_id, current, upstream)
        try:
            build_package(item_id)
            built_count += 1
        except Exception as e:
            log.error("debian.update_all: Fehler bei %s: %s", item_id, e)
            errors.append(str(e))

    _finish("error" if errors else "ok", built=built_count, error="\n".join(errors) or None)


def delete_package(item_id: str, item: dict) -> None:
    """Entfernt .deb-Dateien aus dem Repository-Verzeichnis und aktualisiert den Index."""
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

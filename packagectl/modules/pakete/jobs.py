"""app/modules/pakete/jobs.py – Build-Logik für Arch-Pakete."""

import logging
import os
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_TIMEOUT = 3600


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _run(cmd: list[str], timeout: int = _TIMEOUT) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
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
    from astrapi.core.ui.settings_registry import get_module as _get
    def s(key, default): return _get("pakete", key, default)
    return s


def build_package(item_id: str) -> None:
    from .storage import store

    item = store.get(item_id)
    if not item:
        log.warning("pakete.build: Eintrag '%s' nicht gefunden", item_id)
        return

    s           = _settings()
    image       = s("default_image", "ctl/arch-builder:latest")
    repo_path   = s("repo_path",     "/srv/pacman-repo")
    repo_name   = s("repo_name",     "pkgctl")
    typ         = item.get("typ", "aur")
    source_url  = (item.get("source_url") or "").strip()
    pkgbuild    = item.get("pkgbuild_content") or ""

    if typ == "aur" and not source_url:
        store.update(item_id, {"last_status": "error", "last_built": _now(),
                                "last_log": "Keine AUR Git-URL konfiguriert."})
        return
    if typ == "custom" and not pkgbuild.strip():
        store.update(item_id, {"last_status": "error", "last_built": _now(),
                                "last_log": "Kein PKGBUILD-Inhalt vorhanden."})
        return

    store.update(item_id, {"last_status": "building", "last_built": _now()})

    # Ausgabeverzeichnis sicherstellen
    Path(repo_path).mkdir(parents=True, exist_ok=True)

    tmpdir = None
    try:
        repo_vol = ["-v", f"{repo_path}:/home/makepkg/pkg",
                    "-v", f"{repo_path}:/home/makepkg/repo:ro"]

        if typ == "custom":
            # PKGBUILD in temporäres Verzeichnis schreiben und als Volume mounten
            tmpdir = tempfile.mkdtemp(prefix=f"pkgbuild-{item_id}-")
            with open(os.path.join(tmpdir, "PKGBUILD"), "w") as f:
                f.write(pkgbuild)
            cmd = [
                "docker", "run", "--rm",
                *repo_vol,
                "-v", f"{tmpdir}:/home/makepkg/source",
                image,
                item_id,
            ]
        else:
            cmd = [
                "docker", "run", "--rm",
                *repo_vol,
                image,
                item_id, source_url,
            ]

        log.info("pakete.build: %s", " ".join(cmd))
        rc, output = _run(cmd)
    finally:
        if tmpdir:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    if rc == 0:
        _repo_add(repo_path, repo_name, item_id)

    status = "ok" if rc == 0 else "error"
    log.info("pakete.build: %s → %s (rc=%d)", item_id, status, rc)

    store.update(item_id, {
        "last_status": status,
        "last_built":  _now(),
        "last_log":    output[-20_000:],
    })


def _repo_add(repo_path: str, repo_name: str, item_id: str) -> None:
    """Fügt fertige Pakete zur Pacman-Repo-Datenbank hinzu."""
    import glob as _glob
    pattern = os.path.join(repo_path, f"{item_id}-*.pkg.tar.*")
    pkgs = _glob.glob(pattern)
    if not pkgs:
        log.warning("pakete.repo-add: keine Pakete gefunden für %s", item_id)
        return
    db = os.path.join(repo_path, f"{repo_name}.db.tar.gz")
    rc, out = _run(["repo-add", db] + pkgs, timeout=60)
    if rc != 0:
        log.warning("pakete.repo-add fehlgeschlagen:\n%s", out)


# ── Async-Wrapper ──────────────────────────────────────────────────────────────

def build_package_async(item_id: str) -> None:
    threading.Thread(target=build_package, args=(item_id,), daemon=True).start()

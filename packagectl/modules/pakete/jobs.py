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

    from astrapi.core.system.paths import work_dir as _work_dir
    s           = _settings()
    image       = s("default_image", "ctl/arch-builder:latest")
    repo_path   = s("repo_path", "") or str(_work_dir() / "repo")
    repo_name   = s("repo_name",     "pkgctl")
    source_url    = (item.get("source_url") or "").strip()
    source_subdir = (item.get("source_subdir") or "").strip()
    pkgbuild    = item.get("pkgbuild_content") or ""

    if not source_url and not pkgbuild.strip():
        store.update(item_id, {"last_status": "error", "last_built": _now(),
                                "last_log": "Keine Git-URL und kein PKGBUILD-Inhalt vorhanden."})
        return

    store.update(item_id, {"last_status": "building", "last_built": _now()})

    # Ausgabeverzeichnis sicherstellen
    Path(repo_path).mkdir(parents=True, exist_ok=True)

    tmpdir = None
    try:
        repo_vol = ["-v", f"{repo_path}:/home/makepkg/pkg",
                    "-v", f"{repo_path}:/home/makepkg/repo:ro"]
        env_args = []
        if source_subdir:
            env_args += ["-e", f"SOURCE_SUBDIR={source_subdir}"]

        if source_url:
            cmd = [
                "docker", "run", "--rm",
                *repo_vol,
                *env_args,
                image,
                item_id, source_url,
            ]
        else:
            # Custom PKGBUILD als Volume mounten
            tmpdir = tempfile.mkdtemp(prefix=f"pkgbuild-{item_id}-")
            with open(os.path.join(tmpdir, "PKGBUILD"), "w") as f:
                f.write(pkgbuild)
            cmd = [
                "docker", "run", "--rm",
                *repo_vol,
                *env_args,
                "-v", f"{tmpdir}:/home/makepkg/source",
                image,
                item_id,
            ]

        log.info("pakete.build: %s", " ".join(cmd))
        rc, output = _run(cmd)
    finally:
        if tmpdir:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    version = None
    if rc == 0:
        version = _repo_add(repo_path, repo_name, item_id)

    status = "ok" if rc == 0 else "error"
    log.info("pakete.build: %s → %s (rc=%d)", item_id, status, rc)

    update: dict = {
        "last_status": status,
        "last_built":  _now(),
        "last_log":    output[-20_000:],
    }
    if version:
        update["last_version"] = version
    store.update(item_id, update)


def _repo_add(repo_path: str, repo_name: str, item_id: str) -> str | None:
    """Fügt fertige Pakete zur Pacman-Repo-Datenbank hinzu.

    Gibt die erkannte Version (pkgver-pkgrel) zurück, oder None falls kein Paket gefunden.
    """
    import glob as _glob
    pattern = os.path.join(repo_path, f"{item_id}-*.pkg.tar.*")
    pkgs = [p for p in _glob.glob(pattern)
            if not os.path.basename(p).startswith(f"{item_id}-debug-")]
    if not pkgs:
        log.warning("pakete.repo-add: keine Pakete gefunden für %s", item_id)
        return None
    db = os.path.join(repo_path, f"{repo_name}.db.tar.gz")
    rc, out = _run(["repo-add", db] + pkgs, timeout=60)
    if rc != 0:
        log.warning("pakete.repo-add fehlgeschlagen:\n%s", out)
    # Symlink sicherstellen: pacman braucht <name>.db → <name>.db.tar.gz
    symlink = os.path.join(repo_path, f"{repo_name}.db")
    if not os.path.exists(symlink):
        os.symlink(f"{repo_name}.db.tar.gz", symlink)
    # Version aus Dateinamen extrahieren: pkgname-pkgver-pkgrel-arch.pkg.tar.*
    # pkgver darf keine Bindestriche enthalten (makepkg-Einschränkung)
    try:
        filename = os.path.basename(pkgs[0])
        rest = filename[len(item_id) + 1:]          # "pkgver-pkgrel-arch.pkg.tar.*"
        parts = rest.split("-")
        return f"{parts[0]}-{parts[1]}"             # "pkgver-pkgrel"
    except Exception:
        return None


# ── Cleanup beim Löschen ───────────────────────────────────────────────────────

def delete_package(item_id: str, item: dict) -> None:
    """Entfernt Paketdateien und den Eintrag aus der Pacman-Repo-Datenbank."""
    from astrapi.core.system.paths import work_dir as _work_dir
    import glob as _glob
    import shutil

    s         = _settings()
    repo_path = s("repo_path", "") or str(_work_dir() / "repo")
    repo_name = s("repo_name", "pkgctl")

    # Pakete aus Pacman-DB entfernen
    db = os.path.join(repo_path, f"{repo_name}.db.tar.gz")
    if os.path.exists(db):
        rc, out = _run(["repo-remove", db, item_id], timeout=60)
        if rc != 0:
            log.warning("pakete.repo-remove fehlgeschlagen für %s:\n%s", item_id, out)

    # Paketdateien löschen (inkl. etwaiger Debug-Pakete)
    for pattern in [f"{item_id}-*.pkg.tar.*", f"{item_id}-debug-*.pkg.tar.*"]:
        for path in _glob.glob(os.path.join(repo_path, pattern)):
            try:
                os.unlink(path)
                log.info("pakete.delete: %s gelöscht", path)
            except OSError as e:
                log.warning("pakete.delete: Konnte %s nicht löschen: %s", path, e)


# ── Async-Wrapper ──────────────────────────────────────────────────────────────

def build_package_async(item_id: str) -> None:
    threading.Thread(target=build_package, args=(item_id,), daemon=True).start()

"""astrapi_packages.utils.build_runner – generischer, OS-unabhängiger Docker-Bau.

Ersetzt debian/jobs.py:_build_cmd() (Python-generiertes Bash-Skript) und
archlinux/jobs.py:_build_cmd()+arch-build.sh+host-seitiges repo-add (siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul").

Vertrag für build.sh/publish.sh (liegen als Dateien im Builder-Image-Eintrag,
owner_type='builder', wie das Dockerfile selbst -- Editor bereits generisch,
siehe file_editor_tab.html "+ Neue Datei"):

  build.sh   läuft mit /build/src (enthält PKGBUILD direkt im Root, egal ob
             source_type='git'/'db') read-only und /repo beschreibbar gemountet.
             Liest pkgname/pkgver etc. selbst aus der PKGBUILD (source ./PKGBUILD
             bzw. makepkg), legt das fertige Paket in /repo ab.
  publish.sh läuft nur nach einem erfolgreichen build.sh, mit /repo gemountet
             (und optional dem GPG-Homedir read-only) -- aktualisiert den
             Repo-Index (dpkg-scanpackages/repo-add/...).

Beide Skripte werden vor dem docker run zusammen mit dem restlichen
Builder-Image-Kontext materialisiert (file_store.materialize), nicht ins
Image gebacken -- Änderungen wirken sofort, ohne Image-Neubau.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_TIMEOUT = 3600
_ERR_KEYWORDS = ("error", "fehler", "not found", "failed", "command not found", "exception")


class BuildRunnerError(Exception):
    pass


def repo_path(repo_subdir: str) -> Path:
    """Repo-Basisverzeichnis + os_typ-spezifischem Unterordner, angelegt falls nötig.

    repo_subdir kommt aus os_types.repo_subdir (freie Nutzereingabe) -- gegen
    Pfad-Traversal geprüft, analog _safe_child() in api/repo.py.
    """
    from astrapi_packages._paths import _extra_disk
    from astrapi_packages._paths import repo_dir as _repo_dir

    disk = _extra_disk()
    base = Path(disk).resolve() if disk else _repo_dir().resolve()
    sub = (repo_subdir or "").strip().strip("/")
    path = (base / sub).resolve() if sub else base
    if path != base and base not in path.parents:
        raise BuildRunnerError(f"os_types.repo_subdir '{repo_subdir}' zeigt aus dem Repo heraus")
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o777)
    return path


def materialize_source(
    owner_type: str,
    owner_id: str,
    source_type: str,
    source_url: str,
    source_subdir: str,
    default_subdir: str = "",
) -> tuple[Path, "tempfile.TemporaryDirectory | None"]:
    """Bereitet das Quellverzeichnis vor -- enthält PKGBUILD immer direkt im Root,
    unabhängig von source_type (vereinheitlicht die bisher unterschiedliche
    Subdir-Behandlung von Debian/Archlinux).

    owner_type/owner_id: dieselben Werte wie bei file_store.py (z.B.
    owner_type='packages', owner_id=item_id) -- nur bei source_type='db' relevant.

    Gibt (src_dir, tmp_handle) zurück -- tmp_handle muss vom Aufrufer offen
    gehalten werden (nicht None bei source_type='git', räumt beim Verlassen
    des Scopes automatisch auf) und ist None bei 'db' (stabiler Pfad unter
    work_dir(), kein Aufräumen nötig).
    """
    if source_type == "db":
        from astrapi_packages._paths import work_dir
        from astrapi_packages.utils import file_store

        src_dir = work_dir() / "build-context" / owner_type / owner_id
        file_store.materialize(owner_type, owner_id, src_dir)
        return src_dir, None

    if not source_url:
        raise BuildRunnerError("Keine Git-URL angegeben.")

    tmp = tempfile.TemporaryDirectory(prefix="astrapi-build-src-")
    result = subprocess.run(
        ["git", "clone", "--depth=1", source_url, tmp.name],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        tmp.cleanup()
        raise BuildRunnerError(f"git clone fehlgeschlagen: {result.stderr.strip()[-500:]}")

    subdir = (source_subdir or default_subdir).strip("/")
    src_dir = Path(tmp.name) / subdir if subdir else Path(tmp.name)
    if not (src_dir / "PKGBUILD").exists():
        tmp.cleanup()
        raise BuildRunnerError(f"Keine PKGBUILD in '{subdir or '.'}' gefunden.")
    return src_dir, tmp


def _run_streamed(cmd: list[str], timeout: int = _TIMEOUT) -> tuple[int, str]:
    """Wie debian/jobs.py:_run_streamed (jetzt generisch) -- Live-Ausgabe ins
    aktive activity_log, zusätzlich (rc, gesamte Ausgabe) für last_log."""
    from astrapi_core.system.logger import log as _log

    lines: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
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
            _log("ERROR", f"Fehlgeschlagen (Exit-Code {rc})")
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


def _scripts_dir(image_id: str) -> Path:
    from astrapi_packages._paths import work_dir
    from astrapi_packages.utils import file_store

    scripts_dir = work_dir() / "build-context" / "builder" / image_id
    file_store.materialize("builder", image_id, scripts_dir)
    return scripts_dir


def run_build(image: str, image_id: str, src_dir: Path, repo_dir: Path) -> tuple[int, str]:
    scripts_dir = _scripts_dir(image_id)
    if not (scripts_dir / "build.sh").exists():
        return (
            1,
            f"Kein build.sh im Builder-Image '{image_id}' hinterlegt (im Datei-Editor anlegen).",
        )
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{src_dir}:/build/src:ro",
        "-v",
        f"{repo_dir}:/repo",
        "-v",
        f"{scripts_dir}:/build/scripts:ro",
        image,
        "bash",
        "/build/scripts/build.sh",
    ]
    log.info("build_runner.run_build: %s", " ".join(cmd))
    return _run_streamed(cmd)


def run_publish(
    image: str,
    image_id: str,
    repo_dir: Path,
    gnupg_home: "Path | None" = None,
    gpg_key_id: str = "",
) -> tuple[int, str]:
    scripts_dir = _scripts_dir(image_id)
    if not (scripts_dir / "publish.sh").exists():
        # Optional -- nicht jeder OS-Typ braucht einen eigenen Index-Schritt.
        return 0, "Kein publish.sh hinterlegt, Schritt übersprungen."
    volumes = ["-v", f"{repo_dir}:/repo", "-v", f"{scripts_dir}:/build/scripts:ro"]
    env_args = []
    if gnupg_home is not None:
        volumes += ["-v", f"{gnupg_home}:/root/.gnupg:ro"]
    if gpg_key_id:
        env_args += ["-e", f"GPG_KEY_ID={gpg_key_id}"]
    cmd = ["docker", "run", "--rm", *volumes, *env_args, image, "bash", "/build/scripts/publish.sh"]
    log.info("build_runner.run_publish: %s", " ".join(cmd))
    return _run_streamed(cmd)

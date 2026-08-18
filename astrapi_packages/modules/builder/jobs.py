"""app/modules/docker/jobs.py – Build- und Update-Logik für Docker-Images."""

import subprocess
import tempfile
import threading
import time
from pathlib import Path

from astrapi_core.system.format import fmt_now as _now
from astrapi_core.system.logger import log as _log

_TIMEOUT_BUILD = 3600  # 1 Stunde max. für docker build
_TIMEOUT_CLONE = 60


def _run(cmd: list[str], timeout: int) -> tuple[int, str]:
    """Führt ein Kommando aus, loggt jede Zeile via log() und gibt (returncode, output) zurück."""
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            # Build-Ausgabe ist nicht garantiert UTF-8: Docker reicht durch, was
            # die Tools im Container schreiben. Ein einzelnes ungültiges Byte
            # darf den Build nicht als fehlgeschlagen melden.
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        chunks: list[str] = []
        deadline = time.time() + timeout

        for line in proc.stdout:
            stripped = line.rstrip("\n")
            _log("INFO", stripped)
            chunks.append(line)
            if time.time() > deadline:
                _log("ERROR", f"Timeout nach {timeout}s")
                return 1, "".join(chunks)

        proc.wait()
        return proc.returncode, "".join(chunks)

    except FileNotFoundError:
        msg = f"Kommando nicht gefunden: {cmd[0]!r} – ist Docker installiert?"
        _log("ERROR", msg)
        return 1, msg
    except Exception as e:
        _log("ERROR", str(e))
        return 1, str(e)
    finally:
        # Bricht das Mitlesen ab (Timeout, Decode-Fehler, …), läuft der Build
        # sonst als verwaister Prozess weiter, während die UI "error" meldet.
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()


def run_single(item_id: str) -> None:
    """Baut ein Docker-Image: klont source_url frisch und baut daraus.

    Kein lokaler Dockerfile-Bestand mehr -- analog zum Git-basierten
    Build-Ablauf bei debian/archlinux-Paketen (jobs.py::_build_cmd).
    """
    from astrapi_packages.modules.builder import store

    item = store.get(item_id)
    if item is None:
        _log("ERROR", f"Image '{item_id}' nicht gefunden")
        return

    source_url = item.get("source_url", "")
    if not source_url:
        _log("ERROR", f"Keine Git-URL fuer '{item_id}' hinterlegt.")
        store.upsert(item_id, {"last_status": "error", "last_run": _now()})
        return

    image = f"ctl/{item_id}"
    tag = item.get("tag") or "latest"
    subdir = item.get("source_subdir", "")

    store.upsert(item_id, {"last_status": "building", "last_run": _now()})

    with tempfile.TemporaryDirectory(prefix="astrapi-builder-") as tmp:
        clone_cmd = ["git", "clone", "--depth=1", source_url, tmp]
        _log("INFO", f"$ {' '.join(clone_cmd)}")
        rc, _out = _run(clone_cmd, _TIMEOUT_CLONE)
        if rc != 0:
            store.upsert(item_id, {"last_status": "error", "last_run": _now()})
            return

        build_dir = (Path(tmp) / subdir) if subdir else Path(tmp)
        dockerfile = build_dir / f"{item_id}.dockerfile"
        if not dockerfile.exists():
            _log("ERROR", f"Datei '{item_id}.dockerfile' nicht in '{build_dir}' gefunden.")
            store.upsert(item_id, {"last_status": "error", "last_run": _now()})
            return

        cmd = ["docker", "build", "--no-cache", "-t", f"{image}:{tag}", "-f", str(dockerfile), str(build_dir)]
        _log("INFO", f"$ {' '.join(cmd)}")

        rc, _out = _run(cmd, _TIMEOUT_BUILD)

    if rc == 0:
        _run(["docker", "image", "prune", "-f"], timeout=60)

    status = "ok" if rc == 0 else "error"
    store.upsert(item_id, {"last_status": status, "last_run": _now()})
    _log("INFO" if status == "ok" else "ERROR", f"Build {status}: ctl/{item_id}:{tag}")

    try:
        from astrapi_core.modules.notify import engine as _notify

        if status == "ok":
            _notify.send(
                title=f"Builder: {item_id} erfolgreich gebaut",
                message=f"Image ctl/{item_id}:{tag} wurde aktualisiert.",
                event=_notify.SUCCESS,
                source="builder",
            )
        else:
            _notify.send(
                title=f"Builder: {item_id} – Fehler beim Bauen",
                message=f"Build fehlgeschlagen (rc={rc})",
                event=_notify.ERROR,
                source="builder",
            )
    except Exception:
        pass


def build_image(item_id: str) -> None:
    """Baut ein Image mit eigenem Activity-Log-Kontext (für Scheduler-Aufrufe)."""
    import time as _time

    from astrapi_core.system.activity_log import (
        get_log_lines,
        history_finish,
        history_start,
    )
    from astrapi_core.system.logger import (
        clear_active_log_id,
        clear_tee_context,
        set_active_log_id,
        set_tee_context,
    )

    hist_id = history_start("builder", item_id, f"Builder: {item_id} bauen", "run")
    t0 = _time.time()
    set_tee_context("builder", item_id)
    set_active_log_id(hist_id)
    status = "ok"
    try:
        run_single(item_id)
    except Exception:
        status = "error"
    finally:
        if status == "ok":
            levels = {r["level"] for r in get_log_lines(hist_id)}
            if "ERROR" in levels:
                status = "error"
            elif "WARNING" in levels:
                status = "warning"
        history_finish(hist_id, status, int(_time.time() - t0))
        clear_active_log_id()
        clear_tee_context()


# ── Async-Wrapper ──────────────────────────────────────────────────────────────


def build_image_async(item_id: str) -> None:
    threading.Thread(target=build_image, args=(item_id,), daemon=True).start()

"""app/modules/docker/jobs.py – Build- und Update-Logik für Docker-Images."""

import subprocess
import threading
from datetime import datetime
from pathlib import Path

from astrapi_core.system.logger import log as _log

_TIMEOUT_BUILD = 3600  # 1 Stunde max. für docker build
_DOCKERFILES = Path(__file__).parent / "dockerfiles"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _run(cmd: list[str], timeout: int) -> tuple[int, str]:
    """Führt ein Kommando aus, loggt jede Zeile via log() und gibt (returncode, output) zurück."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        chunks: list[str] = []
        deadline = __import__("time").time() + timeout

        for line in proc.stdout:
            stripped = line.rstrip("\n")
            _log("INFO", stripped)
            chunks.append(line)
            if __import__("time").time() > deadline:
                proc.kill()
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


def run_single(item_id: str) -> None:
    """Baut ein Docker-Image. Ausgabe via log() → Activity-Log (SSE-fähig)."""
    from astrapi_packages.modules.docker import IMAGES, store

    if item_id not in IMAGES:
        _log("ERROR", f"Image '{item_id}' nicht in IMAGES definiert")
        return

    image = f"ctl/{item_id}"
    tag = IMAGES[item_id].get("tag", "latest")
    dockerfile = _DOCKERFILES / f"{item_id}.dockerfile"

    store.upsert(item_id, {"last_status": "building", "last_run": _now()})

    cmd = ["docker", "build", "-t", f"{image}:{tag}", "-f", str(dockerfile), str(_DOCKERFILES)]
    _log("INFO", f"$ {' '.join(cmd)}")

    rc, _ = _run(cmd, _TIMEOUT_BUILD)

    status = "ok" if rc == 0 else "error"
    store.upsert(item_id, {"last_status": status, "last_run": _now()})
    _log("INFO" if status == "ok" else "ERROR", f"Build {status}: ctl/{item_id}:{tag}")

    try:
        from astrapi_core.modules.notify import engine as _notify

        if status == "ok":
            _notify.send(
                title=f"Docker: {item_id} erfolgreich gebaut",
                message=f"Image ctl/{item_id}:{tag} wurde aktualisiert.",
                event=_notify.SUCCESS,
                source="docker",
            )
        else:
            _notify.send(
                title=f"Docker: {item_id} – Fehler beim Bauen",
                message=f"Build fehlgeschlagen (rc={rc})",
                event=_notify.ERROR,
                source="docker",
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

    hist_id = history_start("docker", item_id, f"Docker: {item_id} bauen", "run")
    t0 = _time.time()
    set_tee_context("docker", item_id)
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

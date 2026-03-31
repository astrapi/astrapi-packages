"""app/modules/docker/jobs.py – Build- und Update-Logik für Docker-Images."""

import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_TIMEOUT_BUILD = 3600   # 1 Stunde max. für docker build
_DOCKERFILES   = Path(__file__).parent / "dockerfiles"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _run(cmd: list[str], timeout: int) -> tuple[int, str]:
    """Führt ein Kommando aus und gibt (returncode, output) zurück."""
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


def build_image(item_id: str) -> None:
    """Baut ein Docker-Image synchron. Aktualisiert last_status/last_built/last_log im Store."""
    from .storage import store
    from .images import IMAGES

    if item_id not in IMAGES:
        log.warning("docker.build: Image '%s' nicht in IMAGES definiert", item_id)
        return

    image      = f"ctl/{item_id}"
    tag        = IMAGES[item_id].get("tag", "latest")
    dockerfile = _DOCKERFILES / f"{item_id}.dockerfile"

    store.upsert(item_id, {"last_status": "building", "last_built": _now()})

    import time as _time
    _t0 = _time.time()
    _act_id = None
    try:
        from astrapi.core.system.activity_log import log_activity
        _act_id = log_activity("job", "docker", f"Docker: {item_id} bauen",
                               status="running", item_id=item_id)
    except Exception:
        pass

    cmd = ["docker", "build", "-t", f"{image}:{tag}", "-f", str(dockerfile), str(_DOCKERFILES)]
    log.info("docker.build: %s", " ".join(cmd))
    rc, output = _run(cmd, _TIMEOUT_BUILD)

    status = "ok" if rc == 0 else "error"
    log.info("docker.build: %s → %s (rc=%d)", item_id, status, rc)

    store.upsert(item_id, {
        "last_status": status,
        "last_built":  _now(),
        "last_log":    output[-20_000:],
    })

    if _act_id:
        try:
            from astrapi.core.system.activity_log import update_activity_log
            update_activity_log(
                log_id=_act_id,
                status=status,
                duration_s=int(_time.time() - _t0),
                full_log=output[-20_000:],
                error_message=output[-500:] if status == "error" else None,
            )
        except Exception:
            pass

    try:
        from astrapi.core.modules.notify import engine as _notify
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
                message=output[-400:].strip(),
                event=_notify.ERROR,
                source="docker",
            )
    except Exception:
        pass


# ── Async-Wrapper ──────────────────────────────────────────────────────────────

def build_image_async(item_id: str) -> None:
    threading.Thread(target=build_image, args=(item_id,), daemon=True).start()

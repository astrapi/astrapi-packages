"""app/modules/docker/jobs.py – Build- und Update-Logik für Docker-Images."""

import logging
import os
import subprocess
import tempfile
import threading
from datetime import datetime

log = logging.getLogger(__name__)

_TIMEOUT_BUILD = 3600   # 1 Stunde max. für docker build
_TIMEOUT_PULL  = 600    # 10 Minuten max. für docker pull


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
    """Baut ein Docker-Image synchron.  Aktualisiert last_status/last_built/last_log im Store."""
    from .storage import store

    item = store.get(item_id)
    if not item:
        log.warning("docker.build: Eintrag '%s' nicht gefunden", item_id)
        return

    image   = f"ctl/{item_id}"
    tag     = (item.get("tag") or "latest").strip() or "latest"
    content = item.get("dockerfile_content") or ""

    if not content.strip():
        store.update(item_id, {"last_status": "error", "last_built": _now(),
                                "last_log": "Kein Dockerfile-Inhalt vorhanden."})
        return

    store.update(item_id, {"last_status": "building", "last_built": _now()})

    with tempfile.NamedTemporaryFile(mode="w", suffix="Dockerfile", delete=False) as tf:
        tf.write(content)
        tf_path = tf.name

    try:
        cmd = ["docker", "build", "-t", f"{image}:{tag}", "-f", tf_path, "."]

        log.info("docker.build: %s", " ".join(cmd))
        rc, output = _run(cmd, _TIMEOUT_BUILD)
    finally:
        os.unlink(tf_path)

    status = "ok" if rc == 0 else "error"
    log.info("docker.build: %s → %s (rc=%d)", item_id, status, rc)

    store.update(item_id, {
        "last_status": status,
        "last_built":  _now(),
        "last_log":    output[-20_000:],
    })


def update_image(item_id: str) -> None:
    """Pullt das Basis-Image aus dem gespeicherten Dockerfile-Inhalt und baut neu."""
    from .storage import store

    item = store.get(item_id)
    if not item:
        return

    content = item.get("dockerfile_content") or ""
    base = _parse_from(content)
    if base and base.lower() != "scratch":
        log.info("docker.update: docker pull %s", base)
        rc, out = _run(["docker", "pull", base], _TIMEOUT_PULL)
        if rc != 0:
            log.warning("docker.update: pull fehlgeschlagen:\n%s", out)

    build_image(item_id)


def _parse_from(dockerfile_content: str) -> str | None:
    """Liest die erste FROM-Anweisung aus dem Dockerfile-Inhalt (String)."""
    for line in dockerfile_content.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            if len(parts) >= 2:
                return parts[1]
    return None


# ── Async-Wrapper ──────────────────────────────────────────────────────────────

def build_image_async(item_id: str) -> None:
    threading.Thread(target=build_image, args=(item_id,), daemon=True).start()


def update_image_async(item_id: str) -> None:
    threading.Thread(target=update_image, args=(item_id,), daemon=True).start()

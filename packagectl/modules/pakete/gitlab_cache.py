"""pakete/gitlab_cache.py – Cached GitLab packages.json für die Suchfunktion."""

import json
import logging
import threading
import time
from urllib.request import urlopen, Request

log = logging.getLogger(__name__)

_REFRESH_SEC = 300  # 5 Minuten

_cache: list[dict] = []
_lock  = threading.Lock()


# ── Fetch ─────────────────────────────────────────────────────────────────────

def _repo_paths() -> list[str]:
    try:
        from astrapi.core.ui.settings_registry import get_module
        raw = get_module("pakete", "gitlab_group", []) or []
        if isinstance(raw, str):
            lines = [raw]
        else:
            lines = raw
        result = []
        for val in lines:
            val = str(val).strip()
            for prefix in ("https://gitlab.com/", "http://gitlab.com/"):
                if val.startswith(prefix):
                    val = val[len(prefix):]
            val = val.strip("/")
            if val:
                result.append(val)
        return result
    except Exception:
        return []


def _fetch(repo: str) -> list[dict]:
    url = f"https://gitlab.com/{repo}/-/raw/main/packages.json"
    log.info("gitlab_cache: Lade %s", url)
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if not isinstance(data, list):
            log.warning("gitlab_cache: packages.json ist kein Array.")
            return []
        for entry in data:
            entry.setdefault("source", "gitlab")
        return data
    except Exception as e:
        log.warning("gitlab_cache: Fetch fehlgeschlagen (%s): %s", repo, e)
        return []


# ── Öffentliche API ───────────────────────────────────────────────────────────

def refresh() -> None:
    repos = _repo_paths()
    if not repos:
        return
    entries: list[dict] = []
    for repo in repos:
        entries.extend(_fetch(repo))
    with _lock:
        global _cache
        _cache = entries
    log.info("gitlab_cache: %d Pakete gecacht.", len(entries))


def get_all() -> list[dict]:
    with _lock:
        return list(_cache)


def search(term: str) -> list[dict]:
    t = term.lower()
    with _lock:
        return [
            e for e in _cache
            if t in e.get("name", "").lower() or t in e.get("pkgdesc", "").lower()
        ]


def start() -> None:
    """Startet initialen Fetch + periodischen Refresh im Hintergrund."""
    def _loop():
        time.sleep(3)
        refresh()
        while True:
            time.sleep(_REFRESH_SEC)
            refresh()

    threading.Thread(target=_loop, daemon=True, name="gitlab-cache").start()

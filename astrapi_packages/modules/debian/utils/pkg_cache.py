"""debian/utils/pkg_cache.py – Gecachte packages.json für die Suchfunktion."""

import json
import logging
import threading
import time
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

_REFRESH_SEC = 300  # 5 Minuten

_cache: list[dict] = []
_lock = threading.Lock()


# ── Fetch ─────────────────────────────────────────────────────────────────────


def _repo_paths() -> list[str]:
    try:
        from astrapi_core.ui.settings_registry import get_module

        raw = get_module("debian", "pkg_repos", []) or []
        if isinstance(raw, str):
            lines = [raw]
        else:
            lines = raw
        return [str(v).strip().rstrip("/") for v in lines if str(v).strip()]
    except Exception:
        return []


def _raw_url(entry: str) -> str:
    """Konvertiert eine Repo-URL oder einen Kurzpfad in die URL zur raw packages.json.

    Unterstützt GitHub, GitLab (auch self-hosted), Gitea/Forgejo/Codeberg
    sowie direkte .json-URLs.
    """
    from urllib.parse import urlparse

    if entry.endswith(".json"):
        return entry  # direkte URL → unverändert

    parsed = urlparse(entry)
    if parsed.scheme in ("http", "https"):
        host = parsed.netloc.lower()
        path = parsed.path.strip("/")
        if host == "github.com":
            return f"https://raw.githubusercontent.com/{path}/main/packages.json"
        if "gitlab" in host:
            return f"{parsed.scheme}://{host}/{path}/-/raw/main/packages.json"
        # Gitea / Forgejo / Codeberg und andere
        return f"{parsed.scheme}://{host}/{path}/raw/branch/main/packages.json"

    # Kurzer Pfad ohne Schema (owner/repo) → GitHub
    return f"https://raw.githubusercontent.com/{entry.strip('/')}/main/packages.json"


def _fetch(repo: str) -> list[dict]:
    url = _raw_url(repo)
    log.info("pkg_cache(debian): lade %s", url)
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if not isinstance(data, list):
            log.warning("pkg_cache(debian): packages.json ist kein Array.")
            return []
        for entry in data:
            entry.setdefault("source", "git")
        return data
    except Exception as e:
        log.warning("pkg_cache(debian): Fetch fehlgeschlagen (%s): %s", repo, e)
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
    log.info("pkg_cache(debian): %d Pakete gecacht.", len(entries))


def get_all() -> list[dict]:
    with _lock:
        return list(_cache)


def search(term: str) -> list[dict]:
    t = term.lower()
    with _lock:
        return [
            e for e in _cache if t in e.get("name", "").lower() or t in e.get("pkgdesc", "").lower()
        ]


def start() -> None:
    """Startet initialen Fetch + periodischen Refresh im Hintergrund."""

    def _loop():
        time.sleep(3)
        refresh()
        while True:
            time.sleep(_REFRESH_SEC)
            refresh()

    threading.Thread(target=_loop, daemon=True, name="pkg-cache-debian").start()

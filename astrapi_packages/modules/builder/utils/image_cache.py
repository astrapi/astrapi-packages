"""builder/utils/image_cache.py – Gecachte images.yaml für die Suchfunktion.

Muster identisch zu debian/utils/pkg_cache.py, aber Ziel-Manifest ist
images.yaml (YAML-Mapping id -> {tag, module, subdir}) statt packages.json.
"""

import logging
import threading
import time
from urllib.request import Request, urlopen

import yaml

log = logging.getLogger(__name__)

_REFRESH_SEC = 300  # 5 Minuten

_cache: list[dict] = []
_lock = threading.Lock()


# ── Fetch ─────────────────────────────────────────────────────────────────────


def _repo_paths() -> list[str]:
    try:
        from astrapi_core.ui.settings_registry import get_module

        raw = get_module("builder", "image_repos", []) or []
        if isinstance(raw, str):
            lines = [raw]
        else:
            lines = raw
        return [str(v).strip().rstrip("/") for v in lines if str(v).strip()]
    except Exception:
        return []


def _raw_url(entry: str) -> str:
    """Konvertiert eine Repo-URL oder einen Kurzpfad in die URL zur rohen images.yaml.

    Unterstützt GitHub, GitLab (auch self-hosted), Gitea/Forgejo/Codeberg
    sowie direkte .yaml/.yml-URLs.
    """
    from urllib.parse import urlparse

    if entry.endswith((".yaml", ".yml")):
        return entry  # direkte URL → unverändert

    parsed = urlparse(entry)
    if parsed.scheme in ("http", "https"):
        host = parsed.netloc.lower()
        path = parsed.path.strip("/").removesuffix(".git")
        if host == "github.com":
            return f"https://raw.githubusercontent.com/{path}/main/images.yaml"
        if "gitlab" in host:
            return f"{parsed.scheme}://{host}/{path}/-/raw/main/images.yaml"
        # Gitea / Forgejo / Codeberg und andere
        return f"{parsed.scheme}://{host}/{path}/raw/branch/main/images.yaml"

    # Kurzer Pfad ohne Schema (owner/repo) → GitHub
    return f"https://raw.githubusercontent.com/{entry.strip('/')}/main/images.yaml"


def _fetch(repo: str) -> list[dict]:
    url = _raw_url(repo)
    log.info("image_cache(builder): lade %s", url)
    try:
        req = Request(url, headers={"Accept": "text/plain"})
        with urlopen(req, timeout=10) as r:
            data = yaml.safe_load(r.read()) or {}
        if not isinstance(data, dict):
            log.warning("image_cache(builder): images.yaml ist kein Mapping.")
            return []
        entries = []
        for img_id, cfg in data.items():
            cfg = cfg or {}
            entries.append(
                {
                    "id": img_id,
                    "tag": cfg.get("tag", "latest"),
                    "module": cfg.get("module", ""),
                    "subdir": cfg.get("subdir", ""),
                    # Klonbare URL bleibt der eingetragene Repo-Pfad selbst,
                    # nicht die oben konstruierte raw-Content-URL.
                    "source_url": repo,
                }
            )
        return entries
    except Exception as e:
        log.warning("image_cache(builder): Fetch fehlgeschlagen (%s): %s", repo, e)
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
    log.info("image_cache(builder): %d Images gecacht.", len(entries))


def get_all() -> list[dict]:
    with _lock:
        return list(_cache)


def has_source() -> bool:
    """False, wenn keine Image-Quelle konfiguriert ist - unterscheidet das vom
    Zustand "Cache laedt noch", der sich sonst nie aufloest."""
    return bool(_repo_paths())


def search(term: str) -> list[dict]:
    t = term.lower()
    with _lock:
        return [e for e in _cache if t in e.get("id", "").lower()]


def start() -> None:
    """Startet initialen Fetch + periodischen Refresh im Hintergrund."""

    def _loop():
        time.sleep(3)
        refresh()
        while True:
            time.sleep(_REFRESH_SEC)
            refresh()

    threading.Thread(target=_loop, daemon=True, name="image-cache-builder").start()

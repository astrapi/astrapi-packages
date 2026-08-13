from pathlib import Path

import yaml
from astrapi_core.ui.controls import ContentTable, Header
from astrapi_core.ui.module_loader import load_modul
from astrapi_core.ui.storage import SqliteStorage
from fastapi import APIRouter

_KEY = Path(__file__).parent.name
_DIR = Path(__file__).parent

# ── Images aus YAML laden ─────────────────────────────────────────────────────


def _load_images() -> dict[str, dict]:
    meta = yaml.safe_load((_DIR / "config" / "images.yaml").read_text(encoding="utf-8")) or {}
    return {
        img_id: {
            "tag": cfg.get("tag", "latest"),
            "dockerfile_dir": cfg.get("dockerfile_dir", "dockerfiles"),
            "module": cfg.get("module", ""),
        }
        for img_id, cfg in meta.items()
    }


IMAGES: dict[str, dict] = _load_images()

# ── Store ─────────────────────────────────────────────────────────────────────

store = SqliteStorage(_KEY)

# ── Helper ────────────────────────────────────────────────────────────────────


def _docker_items() -> dict:
    return {
        img_id: {"tag": cfg["tag"], "enabled": True, **(store.get(img_id) or {})}
        for img_id, cfg in IMAGES.items()
    }


def images_for_module(module: str) -> list[dict]:
    """Für Dropdowns: registrierte Images eines Distro-Moduls (debian/archlinux)."""
    return [
        {"value": f"ctl/{img_id}:{cfg['tag']}", "label": img_id}
        for img_id, cfg in IMAGES.items()
        if cfg.get("module") == module
    ]


# ── Dynamische Dropdown-Optionen für options_endpoint (settings.yaml) ────────

from astrapi_core.ui.field_resolver import register_options_fetcher as _register_options_fetcher


def _images_options_fetcher(endpoint: str) -> list:
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(endpoint).query)
    module = qs.get("module", [None])[0]
    return images_for_module(module) if module else []


_register_options_fetcher("/api/builder/images/for-select", _images_options_fetcher)


from .ui import router as ui_router  # ui/ package

# ── Minimaler API-Router: nur JSON-Liste ──────────────────────────────────────

router = APIRouter()


@router.get("/", summary="List Builder Images")
def _list_images():
    return {"builder": _docker_items(), "total": len(IMAGES)}


# Docker-Images sind statisch (keine Edit/Delete/Create/Toggle-Buttons)
_ui_content = ContentTable(
    has_create=False,
    has_edit=False,
    has_delete=False,
    has_toggle=False,
    last_run_label="Letzter Build",
)

module = load_modul(_DIR, _KEY, router, ui_router, ui_header=Header([]), ui_content=_ui_content)

# Config-Loader registrieren
from astrapi_packages.api.run import register_config_loader

register_config_loader(_KEY, _docker_items)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    from .jobs import build_image

    register_action(
        f"{_KEY}.build_arch_builder",
        "arch-builder: Aktualisieren",
        lambda: build_image("arch-builder"),
        source=_KEY,
        source_label="Builder",
    )
    register_action(
        f"{_KEY}.build_debian_builder",
        "debian-builder: Aktualisieren",
        lambda: build_image("debian-builder"),
        source=_KEY,
        source_label="Builder",
    )
except Exception:
    pass

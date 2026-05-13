from pathlib import Path

import yaml
from astrapi_core.ui.controls import ContentTable
from astrapi_core.ui.module_loader import load_modul
from astrapi_core.ui.storage import YamlStorage
from fastapi import APIRouter

_KEY = Path(__file__).parent.name
_DIR = Path(__file__).parent

# ── Images aus YAML laden ─────────────────────────────────────────────────────


def _load_images() -> dict[str, dict]:
    meta = yaml.safe_load((_DIR / "config" / "images.yaml").read_text(encoding="utf-8")) or {}
    return {img_id: {"tag": cfg.get("tag", "latest")} for img_id, cfg in meta.items()}


IMAGES: dict[str, dict] = _load_images()

# ── Store ─────────────────────────────────────────────────────────────────────

store = YamlStorage(_KEY)

# ── Helper ────────────────────────────────────────────────────────────────────


def _docker_items() -> dict:
    return {
        img_id: {"tag": cfg["tag"], **(store.get(img_id) or {})} for img_id, cfg in IMAGES.items()
    }


from .ui import router as ui_router  # ui/ package

# ── Minimaler API-Router: nur JSON-Liste ──────────────────────────────────────

router = APIRouter()


@router.get("/", summary="List Docker Images")
def _list_images():
    return {"docker": _docker_items(), "total": len(IMAGES)}


# Docker-Images sind statisch (keine Edit/Delete/Create/Toggle-Buttons)
_ui_content = ContentTable(
    has_create=False,
    has_edit=False,
    has_delete=False,
    has_toggle=False,
)

module = load_modul(_DIR, _KEY, router, ui_router, ui_content=_ui_content)

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
        source_label="Docker",
    )
except Exception:
    pass

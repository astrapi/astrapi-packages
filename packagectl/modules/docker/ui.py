"""app/modules/docker/ui.py – Flask-Blueprint für das Docker-Modul."""

from pathlib import Path

from flask import Blueprint, render_template

from .images import IMAGES
from .storage import store

KEY = "docker"
bp = Blueprint(f"{KEY}_ui", __name__)


def _items() -> dict:
    """Liefert alle definierten Images mit aktuellem Runtime-Status."""
    return {
        img_id: {"tag": cfg["tag"], **(store.get(img_id) or {})}
        for img_id, cfg in IMAGES.items()
    }


def _ctx(**extra) -> dict:
    return dict(
        cfg=_items(),
        module=KEY,
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/list.html",
        running={},
        has_run_buttons=False,
        has_create=False,
        has_edit=False,
        has_delete=False,
        has_toggle=False,
        **extra,
    )


# ── Listen-Route (wird vom Framework für HTMX-Reloads genutzt) ───────────────

@bp.route(f"/ui/{KEY}/content")
def content():
    return render_template("partials/list_wrapper.html", **_ctx())


# ── Modulspezifische Routen ───────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/<item_id>/build", methods=["POST"])
def build_item(item_id: str):
    if item_id not in IMAGES:
        return "Nicht gefunden", 404
    from .jobs import build_image_async
    build_image_async(item_id)
    return render_template("partials/list_wrapper_inner.html", **_ctx())



@bp.route(f"/ui/{KEY}/<item_id>/log")
def log_item(item_id: str):
    item = store.get(item_id) or {}
    return render_template(
        f"{KEY}/partials/log_modal.html",
        item_id=item_id,
        item_data=item,
    )

"""app/modules/docker/ui.py – Flask-Blueprint für das Docker-Modul."""

from pathlib import Path

from flask import render_template, request

from core.ui.crud_blueprint import make_crud_blueprint
from core.ui.schema_loader import load_schema
from .storage import store, KEY

_DIR = Path(__file__).parent
_SCHEMA = load_schema(str(_DIR / "schema.yaml"))

bp = make_crud_blueprint(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    label="Docker Image",
    description_field="name",
    has_run_buttons=False,
)


# ── Kontext-Helper ────────────────────────────────────────────────────────────

def _ctx():
    return dict(
        cfg=store.list(),
        module=KEY,
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/list.html",
        running={},
        has_run_buttons=False,
    )


# ── Kombiniertes Edit-Modal (überschreibt Standard-Edit via before_request) ───

@bp.before_request
def _intercept_edit():
    endpoint = request.endpoint or ""

    # GET /ui/docker/{id}/edit → kombiniertes Modal zurückgeben
    if endpoint == f"{KEY}_ui.edit_modal":
        item_id = request.view_args.get("item_id")
        item = store.get(item_id)
        if item is None:
            return "Nicht gefunden", 404
        return render_template(
            f"{KEY}/partials/combined_edit_modal.html",
            item_id=item_id,
            item=item,
            schema=_SCHEMA["fields"],
        )

    # POST /ui/docker/{id}/update → dockerfile_content vorab in den Store schreiben,
    # dann den Standard-Handler (crud_blueprint) die Schema-Felder speichern lassen.
    if endpoint == f"{KEY}_ui.edit_apply":
        item_id = request.view_args.get("item_id")
        if store.get(item_id) is not None:
            store.update(item_id, {"dockerfile_content": request.form.get("dockerfile_content", "")})
        return None  # weiter zum Standard-Handler


# ── Modulspezifische Routen ───────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/<item_id>/build", methods=["POST"])
def build_item(item_id: str):
    if store.get(item_id) is None:
        return "Nicht gefunden", 404
    from .jobs import build_image_async
    build_image_async(item_id)
    return render_template("partials/list_wrapper_inner.html", **_ctx())


@bp.route(f"/ui/{KEY}/<item_id>/update", methods=["POST"])
def update_item(item_id: str):
    if store.get(item_id) is None:
        return "Nicht gefunden", 404
    from .jobs import update_image_async
    update_image_async(item_id)
    return render_template("partials/list_wrapper_inner.html", **_ctx())


@bp.route(f"/ui/{KEY}/<item_id>/log")
def log_item(item_id: str):
    item = store.get(item_id) or {}
    return render_template(
        f"{KEY}/partials/log_modal.html",
        item_id=item_id,
        item_data=item,
    )

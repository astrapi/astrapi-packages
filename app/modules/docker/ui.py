"""app/modules/docker/ui.py – Flask-Blueprint für das Docker-Modul."""

from pathlib import Path

from flask import render_template, request

from astrapi.core.ui.crud_blueprint import make_crud_blueprint
from astrapi.core.ui.schema_loader import load_schema
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
def _intercept():
    endpoint = request.endpoint or ""

    # GET /ui/docker/create → kombiniertes Modal (leer)
    if endpoint == f"{KEY}_ui.create_modal":
        return render_template(
            f"{KEY}/partials/combined_edit_modal.html",
            item_id=None,
            item=None,
            schema=_SCHEMA["fields"],
        )

    # POST /ui/docker/ → Anlegen inkl. dockerfile_content
    if endpoint == f"{KEY}_ui.create_apply":
        item_id = request.form.get("name", "").strip()
        if not item_id:
            return "Bezeichnung fehlt", 400
        data = {
            "tag":               request.form.get("tag", "latest").strip() or "latest",
            "enabled":           "enabled" in request.form,
            "dockerfile_content": request.form.get("dockerfile_content", ""),
        }
        try:
            store.create(item_id, data)
        except KeyError:
            return "Bereits vorhanden", 409
        return render_template("partials/list_wrapper.html", **_ctx())

    # GET /ui/docker/{id}/edit → kombiniertes Modal (befüllt)
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

    # POST /ui/docker/{id}/update → dockerfile_content vorab schreiben,
    # dann Standard-Handler (crud_blueprint) die Schema-Felder speichern lassen.
    if endpoint == f"{KEY}_ui.edit_apply":
        item_id = request.view_args.get("item_id")
        content = request.form.get("dockerfile_content", "").strip()
        if content and store.get(item_id) is not None:
            store.update(item_id, {"dockerfile_content": content})
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

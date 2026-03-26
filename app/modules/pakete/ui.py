"""app/modules/pakete/ui.py – Flask-Blueprint für das Pakete-Modul."""

from pathlib import Path

from flask import render_template, request

from astrapi.core.ui.crud_blueprint import make_crud_blueprint
from astrapi.core.ui.schema_loader import load_schema
from .storage import store, KEY

_DIR    = Path(__file__).parent
_SCHEMA = load_schema(str(_DIR / "schema.yaml"))

bp = make_crud_blueprint(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    label="Paket",
    description_field="name",
    has_run_buttons=False,
)


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


@bp.before_request
def _intercept():
    endpoint = request.endpoint or ""

    # GET /ui/pakete/create → kombiniertes Modal (leer)
    if endpoint == f"{KEY}_ui.create_modal":
        return render_template(
            f"{KEY}/partials/combined_edit_modal.html",
            item_id=None,
            item=None,
            schema=_SCHEMA["fields"],
        )

    # POST /ui/pakete/ → Anlegen inkl. pkgbuild_content
    if endpoint == f"{KEY}_ui.create_apply":
        item_id = request.form.get("name", "").strip()
        if not item_id:
            return "Paketname fehlt", 400
        data = {
            "typ":             request.form.get("typ", "aur"),
            "source_url":      request.form.get("source_url", "").strip(),
            "pkgbuild_content": request.form.get("pkgbuild_content", ""),
            "enabled":         "enabled" in request.form,
        }
        try:
            store.create(item_id, data)
        except KeyError:
            return "Bereits vorhanden", 409
        return render_template("partials/list_wrapper.html", **_ctx())

    # GET /ui/pakete/{id}/edit → kombiniertes Modal (befüllt)
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

    # POST /ui/pakete/{id}/update → pkgbuild_content vorab schreiben
    if endpoint == f"{KEY}_ui.edit_apply":
        item_id = request.view_args.get("item_id")
        if store.get(item_id) is not None:
            store.update(item_id, {"pkgbuild_content": request.form.get("pkgbuild_content", "")})
        return None  # weiter zum Standard-Handler


# ── Modulspezifische Routen ───────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/<item_id>/build", methods=["POST"])
def build_item(item_id: str):
    if store.get(item_id) is None:
        return "Nicht gefunden", 404
    from .jobs import build_package_async
    build_package_async(item_id)
    return render_template("partials/list_wrapper_inner.html", **_ctx())


@bp.route(f"/ui/{KEY}/<item_id>/log")
def log_item(item_id: str):
    item = store.get(item_id) or {}
    return render_template(
        f"{KEY}/partials/log_modal.html",
        item_id=item_id,
        item_data=item,
    )

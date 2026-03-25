"""
core/ui/crud_blueprint.py – Generischer Flask CRUD-Blueprint

Erzeugt einen Standard-CRUD-Blueprint mit folgenden Routen:
  GET  /ui/<key>/content              → Listenpartial (list_wrapper.html)
  GET  /ui/<key>/create               → Anlegen-Modal
  GET  /ui/<key>/<item_id>/edit       → Bearbeiten-Modal
  GET  /ui/<key>/<item_id>/delete     → Löschen-Bestätigung
  GET  /ui/<key>/<item_id>/toggle     → Toggle-Bestätigung
  POST /ui/<key>/                     → Anlegen durchführen
  POST /ui/<key>/<item_id>/update     → Bearbeiten durchführen

Verwendung:
    from core.ui.crud_blueprint import make_crud_blueprint
    from core.ui.store import SqliteTableStore
    from pathlib import Path

    KEY   = "remotes"
    store = SqliteTableStore(KEY)
    _DIR  = Path(__file__).parent
    bp    = make_crud_blueprint(store, KEY, schema_path=str(_DIR / "schema.yaml"))

    # Modulspezifische Extrarouten einfach hinzufügen:
    # @bp.route(f"/ui/{KEY}/<item_id>/run", methods=["POST"])
    # def run_item(item_id: str): ...
"""

from __future__ import annotations

from typing import Callable

from flask import Blueprint, render_template, request

from core.ui.schema_loader import load_schema


def make_crud_blueprint(
    store,
    key: str,
    schema_path: str,
    label: str | None = None,
    description_field: str = "description",
    has_run_buttons: bool = False,
    has_toggle: bool = True,
    resolve_fields_fn: Callable[[list], list] | None = None,
) -> Blueprint:
    """Erstellt einen generischen CRUD-Blueprint für Flask.

    Args:
        store:             ModuleStore-Instanz des Moduls (SqliteTableStore oder
                           SqliteStorage/YamlStorage)
        key:               Ressourcenname (z.B. "hosts", "remotes")
        schema_path:       Absoluter Pfad zur schema.yaml
        label:             Anzeigename (Standard: key.capitalize())
        description_field: Feld des Items für die Modal-Beschreibung
        has_run_buttons:   Ob die Liste Run-Buttons anzeigen soll
        has_toggle:        Ob Toggle-Aktion verfügbar sein soll
        resolve_fields_fn: Optionale Funktion zum Anreichern der Schema-Felder
                           (z.B. options_endpoint auflösen). Wird bei jedem
                           create_modal / edit_modal aufgerufen.

    Returns:
        Flask Blueprint mit allen Standard-UI-Routen

    ID-Handling:
        Wenn schema["id_field"] None ist (z.B. backupctl-Module mit
        'id_field: id'), wird beim Anlegen item_id=None übergeben →
        store.create(None, data) → auto-increment.
        Wenn schema["id_field"] ein Dict ist, liest das Formular die ID aus
        id_field["name"] → store.create(item_id, data).
    """
    _label  = label or key.capitalize()
    _c_id   = f"tab-{key}"
    _l_id   = f"{key}-loading"
    schema  = load_schema(schema_path)

    bp = Blueprint(f"{key}_ui", __name__)

    def _ctx(**extra):
        return dict(
            cfg=store.list(),
            module=key,
            container_id=_c_id,
            loading_id=_l_id,
            content_template=f"{key}/partials/list.html",
            running={},
            has_run_buttons=has_run_buttons,
            **extra,
        )

    def _resolved_fields() -> list:
        fields = schema["fields"]
        if resolve_fields_fn is not None:
            return resolve_fields_fn(fields)
        return fields

    def _form_data() -> dict:
        data = {}
        for field in schema["fields"]:
            if field.get("type") == "section" or not field.get("name"):
                continue
            name = field["name"]
            if field.get("type") == "boolean":
                data[name] = name in request.form
            else:
                data[name] = request.form.get(name, "")
        return data

    @bp.route(f"/ui/{key}/content")
    def content():
        return render_template("partials/list_wrapper.html", **_ctx())

    @bp.route(f"/ui/{key}/create")
    def create_modal():
        return render_template(
            "partials/create_edit/create_edit_modal.html",
            schema=_resolved_fields(),
            id_field=schema["id_field"],
            modal_width=schema["modal_width"],
            item=None,
            item_id=None,
            submit_url=f"/ui/{key}/",
            method="post",
            title=f"Neuer {_label}",
            reload_url=f"/ui/{key}/content",
            container_id=request.args.get("container_id", _c_id),
            loading_id=request.args.get("loading_id", _l_id),
        )

    @bp.route(f"/ui/{key}/<item_id>/edit")
    def edit_modal(item_id: str):
        item = store.get(item_id)
        if item is None:
            return f"{_label} nicht gefunden", 404
        return render_template(
            "partials/create_edit/create_edit_modal.html",
            schema=_resolved_fields(),
            id_field=schema["id_field"],
            modal_width=schema["modal_width"],
            item=item,
            item_id=item_id,
            submit_url=f"/ui/{key}/{item_id}/update",
            method="post",
            title=f"{_label} bearbeiten – {item_id}",
            reload_url=f"/ui/{key}/content",
            container_id=request.args.get("container_id", _c_id),
            loading_id=request.args.get("loading_id", _l_id),
        )

    @bp.route(f"/ui/{key}/<item_id>/delete")
    def delete_modal(item_id: str):
        item = store.get(item_id) or {}
        return render_template(
            "partials/confirm_modal.html",
            description=item.get(description_field, item_id),
            verb="löschen",
            confirm_url=f"/api/{key}/{item_id}",
            method="delete",
            reload_url=f"/ui/{key}/content",
            container_id=request.args.get("container_id", _c_id),
            loading_id=request.args.get("loading_id", _l_id),
        )

    @bp.route(f"/ui/{key}/<item_id>/toggle")
    def toggle_modal(item_id: str):
        item    = store.get(item_id) or {}
        enabled = request.args.get("enabled", "True")
        verb    = "deaktivieren" if enabled == "True" else "aktivieren"
        return render_template(
            "partials/confirm_modal.html",
            description=item.get(description_field, item_id),
            verb=verb,
            confirm_url=f"/api/{key}/{item_id}/toggle",
            method="patch",
            reload_url=f"/ui/{key}/content",
            container_id=request.args.get("container_id", _c_id),
            loading_id=request.args.get("loading_id", _l_id),
        )

    @bp.route(f"/ui/{key}/", methods=["POST"])
    def create_apply():
        id_field = schema["id_field"]
        if id_field is not None:
            # Explizite ID aus Formular lesen (astrapi-Stil)
            item_id = request.form.get(id_field["name"], "").strip()
            if not item_id:
                return "ID fehlt", 400
        else:
            # Auto-increment (backupctl-Stil: id_field: id oder fehlt)
            item_id = None
        try:
            store.create(item_id, _form_data())
        except KeyError:
            return "Bereits vorhanden", 409
        return render_template("partials/list_wrapper.html", **_ctx())

    @bp.route(f"/ui/{key}/<item_id>/update", methods=["POST"])
    def edit_apply(item_id: str):
        try:
            store.update(item_id, _form_data())
        except KeyError:
            return "Nicht gefunden", 404
        return render_template("partials/list_wrapper.html", **_ctx())

    return bp

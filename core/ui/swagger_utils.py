# core/ui/swagger_utils.py
#
# Generiert eine OpenAPI-Spec aus den registrierten Flask-Routen.
#
# Tags:    automatisch aus URL-Segment  → /ui/hosts/* → "hosts"
# Summary: automatisch aus URL-Muster   → /ui/hosts/<id>/edit → "Edit Host Modal"
# Methoden: exakt aus Flask-Rule, keine Extrapolation
#
# Manueller Override per Decorator:
#   from core.ui.swagger_utils import ui_meta
#   @ui_meta(tag="hosts", summary="Load Hosts Tab", description="...")
#   def hosts_tab(): ...

from pathlib import Path
import re


# ── Decorator ─────────────────────────────────────────────────────────────────

def ui_meta(tag: str = None, summary: str = None, description: str = None):
    """Setzt Tag, Summary und/oder Description für eine Flask-View manuell."""
    def decorator(func):
        if tag:        setattr(func, "_ui_tag",         tag)
        if summary:    setattr(func, "_ui_summary",     summary)
        if description:setattr(func, "_ui_description", description)
        return func
    return decorator


# Rückwärtskompatibel
def ui_tag(tag_name: str):
    """Decorator: setzt nur den Tag (Kurzform von ui_meta)."""
    def decorator(func):
        setattr(func, "_ui_tag", tag_name)
        return func
    return decorator


# ── Tag aus URL ───────────────────────────────────────────────────────────────

def _tag_from_url(rule: str) -> str:
    """/ui/<key>/... → key  |  /<key> → key  |  / → navigation"""
    m = re.match(r"^/ui/([^/<]+)", rule)
    if m:
        return m.group(1)
    m = re.match(r"^/([^/<]+)$", rule)
    if m:
        return m.group(1)
    return "navigation"


# ── Summary aus URL ───────────────────────────────────────────────────────────

# Bekannte URL-Segmente → lesbarer Begriff
_SEGMENT_LABELS = {
    "content": "Content",
    "list":   "List",
    "create": "Create",
    "edit":   "Edit",
    "delete": "Delete",
    "toggle": "Toggle",
    "save":   "Save",
    "docs":   "Swagger UI",
}

def _to_singular(word: str) -> str:
    """Plural-URL-Segment → lesbarer Singular-Name: 'hosts' → 'Host'."""
    return (word[:-1] if word.endswith("s") else word).title()


def _summary_from_url(rule: str, method: str) -> str:
    """Leitet einen sprechenden Summary-Text aus URL-Muster + HTTP-Methode ab.

    Beispiele:
      GET  /ui/hosts/tab              → "Load Hosts Tab"
      GET  /ui/hosts/<host_id>/edit   → "Edit Host Modal"
      GET  /ui/hosts/<host_id>/delete → "Delete Host Confirmation"
      GET  /ui/hosts/create           → "Create Host Modal"
      POST /ui/settings/save/global   → "Save Global Settings"
      GET  /hosts                     → "Hosts Page"
      GET  /                          → "Root Redirect"
    """
    # Root
    if rule == "/":
        return "Root Redirect"

    parts = [p for p in rule.split("/") if p]

    # /<key>  → "<Key> Page"
    if len(parts) == 1 and not parts[0].startswith("<"):
        label = _to_singular(parts[0])
        return f"{label} Page"

    # /ui/<resource>/...
    if parts and parts[0] == "ui" and len(parts) >= 2:
        resource = parts[1]
        resource_label = _to_singular(resource)
        remaining = parts[2:]

        # /ui/<resource>/create
        if len(remaining) == 1 and remaining[0] == "create":
            return f"Create {resource_label} Modal"

        # /ui/<resource>/tab|list
        if len(remaining) == 1 and remaining[0] in _SEGMENT_LABELS:
            action = _SEGMENT_LABELS[remaining[0]]
            return f"Load {resource_label} {action}"

        # /ui/<resource>/<id>/edit|delete|toggle
        if len(remaining) == 2 and remaining[0].startswith("<"):
            action = _SEGMENT_LABELS.get(remaining[1], remaining[1].title())
            suffix = {
                "edit":   "Modal",
                "delete": "Confirmation",
                "toggle": "Confirmation",
                "create": "Modal",
            }.get(remaining[1], "")
            return f"{action} {resource_label} {suffix}".strip()

        # /ui/<resource>/save/<scope>  → "Save <scope> Settings"
        if len(remaining) >= 2 and remaining[0] == "save":
            scope = remaining[1]
            if scope.startswith("<"):
                scope = "Module"
            return f"Save {scope.title()} Settings"

    # Fallback: Segmente zusammensetzen
    readable = " ".join(
        _SEGMENT_LABELS.get(p, p.title())
        for p in parts
        if not p.startswith("<") and p != "ui"
    )
    return readable or rule


# ── Spec aufbauen ─────────────────────────────────────────────────────────────

def add_ui_routes_to_spec(app, project_root: Path) -> None:
    """Liest alle Flask-Routen aus und trägt sie in app.apispec ein."""
    skip = {"/ui/docs", "/ui/openapi.json", "/static/<path:filename>"}

    with app.test_request_context():
        for rule in app.url_map.iter_rules():
            if rule.rule in skip:
                continue

            # Exakt die Methoden nehmen die Flask kennt — keine Extrapolation
            methods = [
                m.lower() for m in rule.methods
                if m in ("GET", "POST", "PUT", "DELETE", "PATCH")
            ]
            if not methods:
                continue

            view = app.view_functions.get(rule.endpoint)

            tag         = getattr(view, "_ui_tag",         None) or _tag_from_url(rule.rule)
            summary_tpl = getattr(view, "_ui_summary",     None)
            description = getattr(view, "_ui_description", None)

            # Quelldatei relativ zum Projekt-Root
            source_file = getattr(getattr(view, "__code__", None), "co_filename", None)
            if source_file and not description:
                try:
                    description = "Defined in: " + str(
                        Path(source_file).resolve().relative_to(project_root)
                    )
                except ValueError:
                    description = source_file

            # Path-Parameter
            params = [
                {"in": "path", "name": arg, "required": True, "schema": {"type": "string"}}
                for arg in rule.arguments
            ]

            operations = {}
            for method in methods:
                summary = summary_tpl or _summary_from_url(rule.rule, method)
                op = {
                    "summary":     summary,
                    "description": description or "",
                    "tags":        [tag],
                    "responses":   {"200": {"description": "HTML partial / redirect"}},
                }
                if params:
                    op["parameters"] = params
                operations[method] = op

            app.apispec.path(path=rule.rule, operations=operations)


# ── Endpunkte registrieren ────────────────────────────────────────────────────

def register_ui_docs(app, project_root: Path, swagger_html_path: Path) -> None:
    """Registriert /ui/docs und /ui/openapi.json an der Flask-App."""
    from apispec import APISpec
    from flask import jsonify, Response

    app_name = app.config.get("APP_NAME", "AstrapiFlaskUi")

    app.apispec = APISpec(
        title=f"{app_name} UI-Routen",
        version="1.0.0",
        openapi_version="3.0.2",
        info={"description": "Flask UI-Routen: HTMX-Partials, Modals, Seiten"},
    )

    @app.route("/ui/docs")
    def ui_docs():
        html = swagger_html_path.read_text(encoding="utf-8")
        html = html.replace("{{OPENAPI_URL}}", "/ui/openapi.json")
        html = html.replace("{{TITLE}}", f"{app_name} – UI Docs")
        return Response(html, mimetype="text/html")

    @app.route("/ui/openapi.json")
    def ui_openapi_json():
        return jsonify(app.apispec.to_dict())

    add_ui_routes_to_spec(app, project_root)

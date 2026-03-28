"""app/modules/pakete/ui.py – Flask-Blueprint für das Pakete-Modul."""

from pathlib import Path

from flask import render_template, request

from astrapi.core.ui.crud_blueprint import make_crud_blueprint
from astrapi.core.ui.schema_loader import load_schema
from .storage import store, KEY

_DIR    = Path(__file__).parent


def _pkgname(pkgbuild: str) -> str:
    """Liest pkgname= aus einem PKGBUILD-String."""
    import re
    for line in pkgbuild.splitlines():
        m = re.match(r'^\s*pkgname\s*=\s*["\']?([A-Za-z0-9@_+.-]+)', line)
        if m:
            return m.group(1)
    return ""


def _deps_from_pkgbuild(pkgbuild: str) -> list[str]:
    """Liest depends=(...) aus einem PKGBUILD und gibt bereinigte Namen zurück."""
    import re
    deps, in_block = [], False
    for line in pkgbuild.splitlines():
        stripped = line.strip()
        if re.match(r'^depends\s*=\s*\(', stripped):
            in_block = True
        if in_block:
            for d in re.findall(r"['\"]([^'\"]+)['\"]|(\b[A-Za-z0-9@_+.-]+\b)", stripped):
                val = d[0] or d[1]
                if val and val not in ('depends', '(', ')'):
                    deps.append(re.sub(r'[<>=].*', '', val))
            if ')' in stripped:
                in_block = False
    return list(dict.fromkeys(deps))  # dedupliziert, Reihenfolge erhalten


def _deps_from_aur(pkgname: str) -> list[str]:
    """Holt Runtime-Deps aus der AUR RPC API."""
    import re, json, urllib.request
    try:
        url = f"https://aur.archlinux.org/rpc/v5/info?arg[]={pkgname}"
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        if results:
            return [re.sub(r'[<>=].*', '', d) for d in results[0].get("Depends", [])]
    except Exception:
        pass
    return []


def _classify_deps(deps: list[str], existing: set[str]) -> list[dict]:
    """Klassifiziert Abhängigkeiten: packagectl | official | aur."""
    import json, urllib.request
    from concurrent.futures import ThreadPoolExecutor

    def _is_official(name: str) -> bool:
        try:
            url = f"https://archlinux.org/packages/search/json/?name={name}"
            with urllib.request.urlopen(url, timeout=4) as r:
                data = json.loads(r.read())
            return len(data.get("results", [])) > 0
        except Exception:
            return False

    def classify(name: str) -> dict:
        if name in existing:
            return {"name": name, "status": "packagectl"}
        if _is_official(name):
            return {"name": name, "status": "official"}
        return {"name": name, "status": "aur"}

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = dict(zip(deps, ex.map(classify, deps)))

    return [results[d] for d in deps]
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

    # POST /ui/pakete/ → Anlegen
    if endpoint == f"{KEY}_ui.create_apply":
        typ        = request.form.get("typ", "aur")
        source_url = request.form.get("source_url", "").strip()

        if typ == "aur":
            # Name aus URL ableiten: https://aur.archlinux.org/yay-bin.git → yay-bin
            item_id = source_url.rstrip("/").split("/")[-1].removesuffix(".git")
        else:
            # pkgname= aus PKGBUILD lesen
            item_id = _pkgname(request.form.get("pkgbuild_content", ""))

        if not item_id:
            return "Paketname fehlt", 400

        data = {
            "typ":              typ,
            "source_url":       source_url,
            "pkgbuild_content": request.form.get("pkgbuild_content", ""),
            "enabled":          "enabled" in request.form,
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

    # POST /ui/pakete/{id}/update → pkgbuild_content vorab schreiben, dann Liste neu rendern
    if endpoint == f"{KEY}_ui.edit_apply":
        item_id = request.view_args.get("item_id")
        if store.get(item_id) is not None:
            store.update(item_id, {"pkgbuild_content": request.form.get("pkgbuild_content", "")})
            store.update(item_id, {
                "typ":        request.form.get("typ", "aur"),
                "source_url": request.form.get("source_url", "").strip(),
                "enabled":    "enabled" in request.form,
            })
        return render_template("partials/list_wrapper.html", **_ctx())


# ── Modulspezifische Routen ───────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/deps", methods=["POST"])
def deps_preview():
    """Gibt Runtime-Abhängigkeiten als HTML-Partial zurück."""
    source_url = request.form.get("source_url", "").strip()
    pkgbuild   = request.form.get("pkgbuild_content", "").strip()

    if source_url:
        pkgname = source_url.rstrip("/").split("/")[-1].removesuffix(".git")
        deps = _deps_from_aur(pkgname)
    elif pkgbuild:
        deps = _deps_from_pkgbuild(pkgbuild)
    else:
        return ""

    existing = set(store.list().keys())
    classified = _classify_deps(deps, existing)
    return render_template(
        f"{KEY}/partials/deps_preview.html",
        deps=classified,
    )

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

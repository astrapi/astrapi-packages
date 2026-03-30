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

# GitLab-Cache: direkt per importlib laden (app.modules.* Namespace umgehen)
import importlib.util as _ilu, sys as _sys

def _get_gitlab_cache():
    _key = "_pakete_gitlab_cache"
    if _key not in _sys.modules:
        _spec = _ilu.spec_from_file_location(_key, _DIR / "gitlab_cache.py")
        _mod  = _ilu.module_from_spec(_spec)
        _sys.modules[_key] = _mod
        _spec.loader.exec_module(_mod)
        _mod.start()
    return _sys.modules[_key]

_get_gitlab_cache()  # beim Modulstart anwerfen


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
        source_url = request.form.get("source_url", "").strip()
        pkg_name   = request.form.get("pkg_name", "").strip()
        item_id    = pkg_name or source_url.rstrip("/").split("/")[-1].removesuffix(".git")

        if not item_id:
            return "Paketname fehlt", 400

        data = {
            "source_url":    source_url,
            "source_subdir": request.form.get("source_subdir", "").strip(),
            "enabled":       "enabled" in request.form,
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

    # POST /ui/pakete/{id}/update → Felder aktualisieren, dann Liste neu rendern
    if endpoint == f"{KEY}_ui.edit_apply":
        item_id = request.view_args.get("item_id")
        if store.get(item_id) is not None:
            store.update(item_id, {
                "source_url":    request.form.get("source_url", "").strip(),
                "source_subdir": request.form.get("source_subdir", "").strip(),
                "enabled":       "enabled" in request.form,
            })
        return render_template("partials/list_wrapper.html", **_ctx())


# ── Modulspezifische Routen ───────────────────────────────────────────────────

def _search_aur(term: str) -> list[dict]:
    import json, urllib.request, re
    try:
        url = f"https://aur.archlinux.org/rpc/v5/search?arg={term}&by=name-desc"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        return [
            {
                "name":    p["Name"],
                "pkgver":  p.get("Version", ""),
                "pkgdesc": p.get("Description", "") or "",
                "git_url": f"https://aur.archlinux.org/{p['Name']}.git",
                "source":  "aur",
            }
            for p in data.get("results", [])[:12]
        ]
    except Exception:
        return []


@bp.route(f"/ui/{KEY}/search")
def search_packages():
    import threading
    gitlab_cache = _get_gitlab_cache()
    term = request.args.get("q", "").strip()
    if len(term) < 2:
        return ""
    # Cache leer (z.B. Gruppe erst nach Start konfiguriert) → Refresh anstoßen
    if not gitlab_cache.get_all():
        threading.Thread(target=gitlab_cache.refresh, daemon=True).start()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_gl  = ex.submit(gitlab_cache.search, term)
        f_aur = ex.submit(_search_aur, term)
        gl_results  = f_gl.result()
        aur_results = f_aur.result()
    return render_template(
        f"{KEY}/partials/search_results.html",
        gitlab_results=gl_results,
        aur_results=aur_results,
        term=term,
        cache_empty=not gitlab_cache.get_all(),
    )


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

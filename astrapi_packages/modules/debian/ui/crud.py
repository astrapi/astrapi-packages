"""astrapi_packages.modules.debian.ui.crud – FastAPI-UI-Router für das Debian-Modul."""

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.render import render
from astrapi_core.ui.schema_loader import load_schema
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from astrapi_packages.api import status as _status
from astrapi_packages.modules.debian import KEY, store
from astrapi_packages.modules.debian.utils import pkg_cache
from astrapi_packages.utils import file_store
from astrapi_packages.utils.export_import import build_export_import_routes
from astrapi_packages.utils.file_routes import build_file_routes
from astrapi_packages.utils.git_import import GitImportError, import_package_from_git

_DIR = Path(__file__).parent.parent  # modules/debian/
_SCHEMA = load_schema(str(_DIR / "config" / "schema.yaml"))
_EXPORT_FIELDS = ["source_url", "source_subdir", "image", "pkg_type", "enabled", "source_type"]

_PKGBUILD_TEMPLATE = """\
pkgname={name}
pkgver=0.0.1
pkgrel=1
pkgdesc=""
arch=(x86_64)
depends=()

package() {{
  echo "TODO: package() implementieren"
}}
"""

# Hintergrund-Cache starten
pkg_cache.start()


def _running_fn() -> dict:
    return {
        f"{KEY}:{k}": v["last_status"]
        for k, v in store.list().items()
        if v.get("last_status") in _status.LAEUFT
    }


_crud = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Paket",
    description_field="name",
    has_run_buttons=True,
    has_toggle=False,
    running_fn=_running_fn,
)

router = APIRouter()


def _image_options() -> list[dict]:
    from astrapi_core.ui.settings_registry import get_module as _get_setting

    from astrapi_packages.modules.builder import images_for_module

    default_value = _get_setting(KEY, "default_image", "ctl/debian-builder:latest")
    opts = [o for o in images_for_module(KEY) if o["value"] != default_value]
    return [{"value": "", "label": "Standardimage"}, *opts]


def _ctx():
    cfg = store.list()
    return dict(
        cfg=cfg,
        module=KEY,
        container_id=f"mod-{KEY}",
        loading_id=f"{KEY}-loading",
        running=_running_fn(),
    )


# ── Status-Route (HTMX-Polling) ───────────────────────────────────────────────


@router.get(f"/ui/{KEY}/status", response_class=HTMLResponse)
def status(request: Request):
    return render(request, "partials/oob/status_oob.html", _ctx())


# ── Create/Edit-Modals ────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(
            item_id=None,
            item=None,
            error=None,
            image_options=_image_options(),
            no_source=not pkg_cache.has_source(),
        ),
    )


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def create_apply(request: Request):
    form = await request.form()
    item_id = form.get("name", "").strip()

    if not item_id:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(item_id=None, item=dict(form), error="Paketname ist erforderlich."),
        )

    if store.get(item_id) is not None:
        import json as _json

        return Response(
            content="",
            status_code=200,
            headers={
                "HX-Reswap": "none",
                "HX-Trigger": _json.dumps(
                    {"debianModalError": f'"{item_id}" ist bereits vorhanden.'}
                ),
            },
        )

    data = {
        "source_url": form.get("source_url", "").strip(),
        "source_subdir": form.get("source_subdir", "").strip(),
        "image": form.get("image", "").strip(),
        "pkg_type": form.get("pkg_type", "package").strip() or "package",
        "enabled": "enabled" in form,
        # Explizit statt ueber den DDL-Default: auf bestehenden Tabellen steht
        # dort noch '' (T-134), SQLite aendert den Default nicht nachtraeglich.
        "last_status": _status.NEU,
    }
    upstream_version = form.get("upstream_version", "").strip()
    if upstream_version:
        data["upstream_version"] = upstream_version
    store.create(item_id, data)
    return render(request, "content.html", _ctx())


@router.get(f"/ui/{KEY}/{{item_id}}/edit", response_class=HTMLResponse)
def edit_modal(item_id: str, request: Request):
    item = store.get(item_id)
    if item is None:
        return HTMLResponse("Nicht gefunden", status_code=404)
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(item_id=item_id, item=item, error=None, image_options=_image_options()),
    )


@router.post(f"/ui/{KEY}/{{item_id}}/update", response_class=HTMLResponse)
async def edit_apply(item_id: str, request: Request):
    form = await request.form()
    if store.get(item_id) is not None:
        data = {
            "source_url": form.get("source_url", "").strip(),
            "source_subdir": form.get("source_subdir", "").strip(),
            "image": form.get("image", "").strip(),
            "pkg_type": form.get("pkg_type", "package").strip() or "package",
            "enabled": "enabled" in form,
        }
        store.update(item_id, data)
    return render(request, "content.html", _ctx())


@router.post(f"/ui/{KEY}/{{item_id}}/import-from-git", response_class=HTMLResponse)
def import_from_git(item_id: str, request: Request):
    item = store.get(item_id)
    if item is None:
        return HTMLResponse("Nicht gefunden", status_code=404)
    error = None
    try:
        import_package_from_git(
            KEY, item_id, item.get("source_url", ""), item.get("source_subdir", "")
        )
        store.update(item_id, {"source_type": "db"})
    except GitImportError as e:
        error = str(e)
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(item_id=item_id, item=store.get(item_id), error=error, image_options=_image_options()),
    )


@router.get(f"/ui/{KEY}/new-in-db", response_class=HTMLResponse)
def new_in_db_dialog(request: Request):
    return render(request, "dialog_new_in_db.html", dict(module=KEY, error=None))


@router.post(f"/ui/{KEY}/new-in-db", response_class=HTMLResponse)
async def new_in_db_apply(request: Request):
    form = await request.form()
    item_id = form.get("name", "").strip()
    if not item_id:
        return render(
            request,
            "dialog_new_in_db.html",
            dict(module=KEY, error="Paketname ist erforderlich."),
        )
    if store.get(item_id) is not None:
        return render(
            request,
            "dialog_new_in_db.html",
            dict(module=KEY, error=f"'{item_id}' ist bereits vorhanden."),
        )
    store.create(
        item_id,
        {
            "pkg_type": "package",
            "enabled": True,
            "last_status": _status.NEU,
            "source_type": "db",
        },
    )
    file_store.save(
        KEY, item_id, "PKGBUILD", _PKGBUILD_TEMPLATE.format(name=item_id), message="Neu erstellt"
    )
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(item_id=item_id, item=store.get(item_id), error=None, image_options=_image_options()),
    )


@router.get(f"/ui/{KEY}/search", response_class=HTMLResponse)
def search_packages(request: Request):
    term = request.query_params.get("q", "").strip()
    if len(term) < 2:
        return HTMLResponse("")
    if not pkg_cache.get_all():
        import threading

        threading.Thread(target=pkg_cache.refresh, daemon=True).start()
    results = pkg_cache.search(term)
    return render(
        request,
        f"{KEY}/dialogs/edit/search_results.html",
        dict(
            results=results,
            term=term,
            cache_empty=not pkg_cache.get_all(),
            no_source=not pkg_cache.has_source(),
        ),
    )


@router.post(f"/ui/{KEY}/pkg-cache/refresh", response_class=HTMLResponse)
async def refresh_pkg_cache(request: Request):
    """Laedt packages.json sofort neu statt bis zu 5 Min. auf den
    Hintergrund-Refresh zu warten (T-156-PACKAGES) - z.B. direkt nach dem
    Veroeffentlichen eines neuen Pakets im Repo."""
    pkg_cache.refresh()
    form = await request.form()
    term = (form.get("q") or "").strip()
    if len(term) < 2:
        return HTMLResponse("")
    results = pkg_cache.search(term)
    return render(
        request,
        f"{KEY}/dialogs/edit/search_results.html",
        dict(
            results=results,
            term=term,
            cache_empty=not pkg_cache.get_all(),
            no_source=not pkg_cache.has_source(),
        ),
    )


# ── PKGBUILD-Info (Version + Distribution) ───────────────────────────────────


def _pkgbuild_raw_url(base_url: str, branch: str, subdir: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(base_url)
    path = p.path.strip("/")
    if p.netloc == "github.com":
        return f"https://raw.githubusercontent.com/{path}/{branch}/{subdir}/PKGBUILD"
    if "gitlab" in p.netloc:
        return f"{p.scheme}://{p.netloc}/{path}/-/raw/{branch}/{subdir}/PKGBUILD"
    return f"{p.scheme}://{p.netloc}/{path}/raw/branch/{branch}/{subdir}/PKGBUILD"


def _pkgbuild_info(source_url: str, pkg_name: str) -> dict:
    """Liest Version aus dem PKGBUILD."""
    import re
    import urllib.request

    base = source_url.rstrip("/").removesuffix(".git")
    for branch in ("main", "master"):
        url = _pkgbuild_raw_url(base, branch, pkg_name)
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                text = r.read().decode("utf-8", errors="replace")
            m_ver = re.search(r"^pkgver\s*=\s*(.+)", text, re.MULTILINE)
            m_rel = re.search(r"^pkgrel\s*=\s*(.+)", text, re.MULTILINE)
            version = ""
            if m_ver:
                ver = m_ver.group(1).strip().strip("'\"")
                rel = m_rel.group(1).strip().strip("'\"") if m_rel else ""
                version = f"{ver}-{rel}" if rel else ver
            return {"version": version}
        except Exception:
            continue
    return {"version": ""}


@router.get(f"/ui/{KEY}/pkgbuild-info")
def pkgbuild_info(request: Request):
    """Liest Version und Distribution aus dem PKGBUILD der angegebenen URL."""
    from fastapi.responses import JSONResponse

    url = request.query_params.get("url", "").strip()
    pkg = request.query_params.get("pkg", "").strip()
    if not url or not pkg:
        return JSONResponse({"version": ""})
    return JSONResponse(_pkgbuild_info(url, pkg))


# ── Auf Updates prüfen ───────────────────────────────────────────────────────


@router.post(f"/ui/{KEY}/check-updates", response_class=HTMLResponse)
def check_updates(request: Request):
    """Prüft für alle Pakete ob eine neue Version verfügbar ist."""
    import re
    import urllib.request

    try:
        pkg_cache.refresh()
    except Exception:
        pass

    all_items = store.list()
    if not all_items:
        return render(request, "content.html", _ctx())

    for k, v in all_items.items():
        if v.get("last_status") not in _status.AUTO_UPDATE and v.get("upstream_version"):
            store.update(k, {"upstream_version": ""})

    cache_entries = {
        e["name"]: e for e in (pkg_cache.get_all() if pkg_cache else []) if e.get("name")
    }

    def _version_from_pkgbuild(source_url: str, subdir: str) -> str:
        base = source_url.rstrip("/").removesuffix(".git")
        for branch in ("main", "master"):
            url = _pkgbuild_raw_url(base, branch, subdir)
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    text = r.read().decode("utf-8", errors="replace")
                m_ver = re.search(r"^pkgver\s*=\s*(.+)", text, re.MULTILINE)
                m_rel = re.search(r"^pkgrel\s*=\s*(.+)", text, re.MULTILINE)
                if m_ver:
                    ver = m_ver.group(1).strip().strip("'\"")
                    rel = m_rel.group(1).strip().strip("'\"") if m_rel else ""
                    return f"{ver}-{rel}" if rel else ver
            except Exception:
                continue
        return ""

    for item_id, item in all_items.items():
        _entry = cache_entries.get(item_id, {})
        _ver = _entry.get("pkgver", "")
        _rel = _entry.get("pkgrel", "")
        upstream = f"{_ver}-{_rel}" if _ver and _rel else _ver
        if not upstream:
            source_url = item.get("source_url", "").strip()
            if source_url:
                upstream = _version_from_pkgbuild(source_url, item_id)
        if upstream:
            store.update(item_id, {"upstream_version": upstream})

    return render(request, "content.html", _ctx())


# ── CRUD-Router einbinden ─────────────────────────────────────────────────────

router.include_router(_crud)
router.include_router(build_file_routes(KEY))
router.include_router(build_export_import_routes(KEY, store, _EXPORT_FIELDS))

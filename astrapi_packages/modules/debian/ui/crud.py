"""astrapi_packages.modules.debian.ui.crud – FastAPI-UI-Router für das Debian-Modul."""

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.render import render
from astrapi_core.ui.schema_loader import load_schema
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from astrapi_packages.modules.debian import KEY, store

_DIR = Path(__file__).parent.parent  # modules/debian/
_SCHEMA = load_schema(str(_DIR / "config" / "schema.yaml"))

# Hintergrund-Cache starten
import importlib.util as _ilu
import sys as _sys

_cache_key = "_debian_pkg_cache"
if _cache_key not in _sys.modules:
    _spec = _ilu.spec_from_file_location(_cache_key, _DIR / "utils" / "pkg_cache.py")
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules[_cache_key] = _mod
    _spec.loader.exec_module(_mod)
    _mod.start()


def _running_fn() -> dict:
    return {
        f"{KEY}:{k}": v["last_status"]
        for k, v in store.list().items()
        if v.get("last_status") in ("building", "pending")
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
        dict(item_id=None, item=None, error=None),
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
        "distribution": form.get("distribution", "bookworm").strip() or "bookworm",
        "component": form.get("component", "main").strip() or "main",
        "pkg_type": form.get("pkg_type", "package").strip() or "package",
        "enabled": "enabled" in form,
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
        dict(item_id=item_id, item=item, error=None),
    )


@router.post(f"/ui/{KEY}/{{item_id}}/update", response_class=HTMLResponse)
async def edit_apply(item_id: str, request: Request):
    form = await request.form()
    if store.get(item_id) is not None:
        data = {
            "source_url": form.get("source_url", "").strip(),
            "source_subdir": form.get("source_subdir", "").strip(),
            "distribution": form.get("distribution", "bookworm").strip() or "bookworm",
            "component": form.get("component", "main").strip() or "main",
            "pkg_type": form.get("pkg_type", "package").strip() or "package",
            "enabled": "enabled" in form,
        }
        store.update(item_id, data)
    return render(request, "content.html", _ctx())


@router.get(f"/ui/{KEY}/search", response_class=HTMLResponse)
def search_packages(request: Request):
    term = request.query_params.get("q", "").strip()
    if len(term) < 2:
        return HTMLResponse("")
    pkg_cache = _sys.modules.get(_cache_key)
    if pkg_cache and not pkg_cache.get_all():
        import threading

        threading.Thread(target=pkg_cache.refresh, daemon=True).start()
    results = pkg_cache.search(term) if pkg_cache else []
    return render(
        request,
        f"{KEY}/dialogs/edit/search_results.html",
        dict(results=results, term=term, cache_empty=pkg_cache and not pkg_cache.get_all()),
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
    """Liest Version und optionale _distribution-Variable aus dem PKGBUILD."""
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
            m_dist = re.search(r"^_?distribution\s*=\s*['\"]?([a-zA-Z0-9]+)", text, re.MULTILINE)
            version = ""
            if m_ver:
                ver = m_ver.group(1).strip().strip("'\"")
                rel = m_rel.group(1).strip().strip("'\"") if m_rel else ""
                version = f"{ver}-{rel}" if rel else ver
            return {
                "version": version,
                "distribution": m_dist.group(1).strip() if m_dist else "",
            }
        except Exception:
            continue
    return {"version": "", "distribution": ""}


@router.get(f"/ui/{KEY}/pkgbuild-info")
def pkgbuild_info(request: Request):
    """Liest Version und Distribution aus dem PKGBUILD der angegebenen URL."""
    from fastapi.responses import JSONResponse

    url = request.query_params.get("url", "").strip()
    pkg = request.query_params.get("pkg", "").strip()
    if not url or not pkg:
        return JSONResponse({"version": "", "distribution": ""})
    return JSONResponse(_pkgbuild_info(url, pkg))


# ── Auf Updates prüfen ───────────────────────────────────────────────────────


@router.post(f"/ui/{KEY}/check-updates", response_class=HTMLResponse)
def check_updates(request: Request):
    """Prüft für alle Pakete ob eine neue Version verfügbar ist."""
    import re
    import urllib.request

    pkg_cache = _sys.modules.get(_cache_key)
    try:
        if pkg_cache:
            pkg_cache.refresh()
    except Exception:
        pass

    all_items = store.list()
    if not all_items:
        return render(request, "content.html", _ctx())

    for k, v in all_items.items():
        if v.get("last_status") != "ok" and v.get("upstream_version"):
            store.update(k, {"upstream_version": ""})

    cache_entries = {e["name"]: e for e in (pkg_cache.get_all() if pkg_cache else []) if e.get("name")}

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

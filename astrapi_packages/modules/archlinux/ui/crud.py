"""app/modules/archlinux/ui/crud.py – FastAPI-Router für das Arch-Linux-Modul."""

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.render import render
from astrapi_core.ui.schema_loader import load_schema
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from astrapi_packages.modules.archlinux import KEY, store

_DIR = Path(__file__).parent.parent  # modules/archlinux/
_SCHEMA = load_schema(str(_DIR / "config" / "schema.yaml"))


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
        if re.match(r"^depends\s*=\s*\(", stripped):
            in_block = True
        if in_block:
            for d in re.findall(r"['\"]([^'\"]+)['\"]|(\b[A-Za-z0-9@_+.-]+\b)", stripped):
                val = d[0] or d[1]
                if val and val not in ("depends", "(", ")"):
                    deps.append(re.sub(r"[<>=].*", "", val))
            if ")" in stripped:
                in_block = False
    return list(dict.fromkeys(deps))


def _deps_from_aur(pkgname: str) -> list[str]:
    """Holt Runtime-Deps aus der AUR RPC API."""
    import json
    import re
    import urllib.request

    try:
        url = f"https://aur.archlinux.org/rpc/v5/info?arg[]={pkgname}"
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        if results:
            r0 = results[0]
            all_deps = r0.get("Depends", []) + r0.get("MakeDepends", [])
            return list(dict.fromkeys(re.sub(r"[<>=].*", "", d) for d in all_deps))
    except Exception:
        pass
    return []


def _classify_deps(deps: list[str], existing: set[str]) -> list[dict]:
    """Klassifiziert Abhängigkeiten: astrapi-packages | official | aur."""
    import json
    import urllib.parse
    import urllib.request

    unknown = [d for d in deps if d not in existing]
    in_aur: set[str] = set()

    if unknown:
        qs = "&".join(f"arg[]={urllib.parse.quote(n)}" for n in unknown)
        try:
            url = f"https://aur.archlinux.org/rpc/v5/info?{qs}"
            with urllib.request.urlopen(url, timeout=8) as r:
                data = json.loads(r.read())
            in_aur = {p["Name"] for p in data.get("results", [])}
        except Exception:
            pass

    result = []
    for name in deps:
        if name in existing:
            result.append({"name": name, "status": "astrapi-packages"})
        elif name in in_aur:
            result.append({"name": name, "status": "aur"})
        else:
            result.append({"name": name, "status": "official"})
    return result


import importlib.util as _ilu
import sys as _sys


def _get_pkg_cache():
    _key = "_archlinux_pkg_cache"
    if _key not in _sys.modules:
        _spec = _ilu.spec_from_file_location(_key, _DIR / "utils" / "pkg_cache.py")
        _mod = _ilu.module_from_spec(_spec)
        _sys.modules[_key] = _mod
        _spec.loader.exec_module(_mod)
        _mod.start()
    return _sys.modules[_key]


_get_pkg_cache()


# ── CRUD-Router für delete + toggle (Standard-Verhalten) ─────────────────────
# content, create, edit, create_apply, edit_apply werden unten manuell definiert
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

# Eigene Routen werden ZUERST auf diesem Router registriert,
# danach wird der CRUD-Router eingebunden (FastAPI: first-match).
# So gewinnen unsere Overrides für create/edit/create_apply/edit_apply.
router = APIRouter()


def _ctx():
    cfg = store.list()
    running = {
        f"{KEY}:{k}": v["last_status"]
        for k, v in cfg.items()
        if v.get("last_status") in ("building", "pending")
    }
    return dict(
        cfg=cfg,
        module=KEY,
        container_id=f"mod-{KEY}",
        loading_id=f"{KEY}-loading",
        running=running,
    )


# ── Überschreibende Routen ────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/status", response_class=HTMLResponse)
def status(request: Request):
    return render(request, "partials/status_oob.html", _ctx())


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(
            item_id=None,
            item=None,
            schema=_SCHEMA["fields"],
        ),
    )


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def create_apply(request: Request):
    form = await request.form()
    source_url = form.get("source_url", "").strip()
    pkg_name = form.get("pkg_name", "").strip()
    item_id = pkg_name or source_url.rstrip("/").split("/")[-1].removesuffix(".git")

    if not item_id:
        return HTMLResponse("Paketname fehlt", status_code=400)

    if store.get(item_id) is not None:
        import json as _json

        return Response(
            content="",
            status_code=200,
            headers={
                "HX-Reswap": "none",
                "HX-Trigger": _json.dumps(
                    {"archlinuxModalError": f'"{item_id}" ist bereits vorhanden.'}
                ),
            },
        )

    data = {
        "source_url": source_url,
        "source_subdir": form.get("source_subdir", "").strip(),
        "aur_deps": form.get("aur_deps", "").strip(),
        "pkg_type": form.get("pkg_type", "package").strip() or "package",
        "enabled": "enabled" in form,
    }
    upstream_version = form.get("upstream_version", "").strip()
    if upstream_version:
        data["upstream_version"] = upstream_version
    store.create(item_id, data)

    from ..utils.dep_graph import autocreate_deps

    autocreate_deps(item_id, data, store)

    return render(request, "content.html", _ctx())


@router.get(f"/ui/{KEY}/{{item_id}}/edit", response_class=HTMLResponse)
def edit_modal(item_id: str, request: Request):
    item = store.get(item_id)
    if item is None:
        return HTMLResponse("Nicht gefunden", status_code=404)
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(
            item_id=item_id,
            item=item,
            schema=_SCHEMA["fields"],
        ),
    )


@router.post(f"/ui/{KEY}/{{item_id}}/update", response_class=HTMLResponse)
async def edit_apply(item_id: str, request: Request):
    form = await request.form()
    if store.get(item_id) is not None:
        data = {
            "source_url": form.get("source_url", "").strip(),
            "source_subdir": form.get("source_subdir", "").strip(),
            "aur_deps": form.get("aur_deps", "").strip(),
            "pkg_type": form.get("pkg_type", "package").strip() or "package",
            "enabled": "enabled" in form,
        }
        store.update(item_id, data)
        from ..utils.dep_graph import autocreate_deps

        autocreate_deps(item_id, data, store)
    return render(request, "content.html", _ctx())


# ── Modulspezifische Routen ───────────────────────────────────────────────────


def _parse_pkgbuild_deps(text: str) -> list[str]:
    import re

    deps: list[str] = []
    for key in ("depends", "makedepends"):
        m = re.search(rf"^{key}\s*=\s*\((.*?)\)", text, re.MULTILINE | re.DOTALL)
        if not m:
            continue
        for token in re.findall(r"'([^']+)'|\"([^\"]+)\"|(\S+)", m.group(1)):
            name = (token[0] or token[1] or token[2]).strip()
            name = re.sub(r"[><=!].*", "", name).strip()
            if name:
                deps.append(name)
    seen: set[str] = set()
    return [d for d in deps if not (d in seen or seen.add(d))]  # type: ignore[func-returns-value]


def _pkgbuild_raw_url(base_url: str, branch: str, subdir: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(base_url)
    path = p.path.strip("/")
    if p.netloc == "github.com":
        return f"https://raw.githubusercontent.com/{path}/{branch}/{subdir}/PKGBUILD"
    if "gitlab" in p.netloc:
        return f"{p.scheme}://{p.netloc}/{path}/-/raw/{branch}/{subdir}/PKGBUILD"
    return f"{p.scheme}://{p.netloc}/{path}/raw/branch/{branch}/{subdir}/PKGBUILD"


def _version_from_pkgbuild_url(source_url: str, source_subdir: str) -> tuple[str, list[str]]:
    import re
    import urllib.request

    base = source_url.rstrip("/").removesuffix(".git")
    for branch in ("main", "master"):
        url = _pkgbuild_raw_url(base, branch, source_subdir)
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
            return version, _parse_pkgbuild_deps(text)
        except Exception:
            continue
    return "", []


def _search_aur(term: str) -> list[dict]:
    import json
    import urllib.request

    try:
        url = f"https://aur.archlinux.org/rpc/v5/search?arg={term}&by=name-desc"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        return [
            {
                "name": p["Name"],
                "pkgver": p.get("Version", ""),
                "pkgdesc": p.get("Description", "") or "",
                "git_url": f"https://aur.archlinux.org/{p['Name']}.git",
                "source": "aur",
            }
            for p in data.get("results", [])[:12]
        ]
    except Exception:
        return []


@router.get(f"/ui/{KEY}/search", response_class=HTMLResponse)
def search_packages(request: Request):
    import threading

    pkg_cache = _get_pkg_cache()
    term = request.query_params.get("q", "").strip()
    if len(term) < 2:
        return HTMLResponse("")
    if not pkg_cache.get_all():
        threading.Thread(target=pkg_cache.refresh, daemon=True).start()
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_pkg = ex.submit(pkg_cache.search, term)
        f_aur = ex.submit(_search_aur, term)
        pkg_results = f_pkg.result()
        aur_results = f_aur.result()
    return render(
        request,
        f"{KEY}/dialogs/edit/search_results.html",
        dict(
            pkg_results=pkg_results,
            aur_results=aur_results,
            term=term,
            cache_empty=not pkg_cache.get_all(),
        ),
    )


@router.get(f"/ui/{KEY}/aur-deps", response_class=HTMLResponse)
def aur_deps_for_pkg(request: Request):
    """Gibt die AUR-Abhängigkeiten eines Pakets als kommaseparierten String zurück."""
    pkgname = request.query_params.get("pkg", "").strip()
    if not pkgname:
        return HTMLResponse("")
    deps = _deps_from_aur(pkgname)
    if not deps:
        return HTMLResponse("")
    existing = set(store.list().keys())
    classified = _classify_deps(deps, existing)
    aur_only = [d["name"] for d in classified if d["status"] == "aur"]
    return HTMLResponse(", ".join(aur_only))


@router.post(f"/ui/{KEY}/deps", response_class=HTMLResponse)
async def deps_preview(request: Request):
    """Gibt Runtime-Abhängigkeiten als HTML-Partial zurück."""
    form = await request.form()
    source_url = form.get("source_url", "").strip()
    pkgbuild = form.get("pkgbuild_content", "").strip()

    if source_url:
        pkgname = source_url.rstrip("/").split("/")[-1].removesuffix(".git")
        deps = _deps_from_aur(pkgname)
    elif pkgbuild:
        deps = _deps_from_pkgbuild(pkgbuild)
    else:
        return HTMLResponse("")

    existing = set(store.list().keys())
    classified = _classify_deps(deps, existing)
    return render(request, f"{KEY}/dialogs/edit/deps_preview.html", {"deps": classified})


@router.get(f"/ui/{KEY}/exists", response_class=HTMLResponse)
def pkg_exists(request: Request):
    item_id = request.query_params.get("id", "").strip()
    if item_id and store.get(item_id) is not None:
        return HTMLResponse(
            f'<div id="modal-error-container" style="padding:8px 12px;border-radius:6px;'
            f'background:var(--error-dim,#3a0000);color:var(--error,#ff6b6b);font-size:13px;">'
            f'"{item_id}" ist bereits vorhanden.</div>'
        )
    return HTMLResponse('<div id="modal-error-container"></div>')


@router.get(f"/ui/{KEY}/pkgbuild-info")
def pkgbuild_info(request: Request):
    """Liest Version aus dem PKGBUILD der angegebenen URL."""
    from fastapi.responses import JSONResponse

    url = request.query_params.get("url", "").strip()
    subdir = request.query_params.get("subdir", "").strip()
    if not url:
        return JSONResponse({"version": ""})
    version, _ = _version_from_pkgbuild_url(url, subdir)
    return JSONResponse({"version": version})


@router.post(f"/ui/{KEY}/check-updates", response_class=HTMLResponse)
def check_updates(request: Request):
    """Prüft für alle Pakete ob eine neue Version verfügbar ist."""
    import json
    import urllib.request
    from urllib.parse import quote

    try:
        _get_pkg_cache().refresh()
    except Exception:
        pass

    all_items = store.list()
    if not all_items:
        return render(request, "partials/list_wrapper_inner.html", _ctx())

    for k, v in all_items.items():
        if v.get("last_status") != "ok" and v.get("upstream_version"):
            store.update(k, {"upstream_version": ""})

    all_ids = [k for k, v in all_items.items() if v.get("last_status") == "ok"]
    if not all_ids:
        return render(request, "partials/list_wrapper_inner.html", _ctx())

    qs = "&".join(f"arg[]={quote(i)}" for i in all_ids)
    aur_versions: dict[str, str] = {}
    try:
        with urllib.request.urlopen(f"https://aur.archlinux.org/rpc/v5/info?{qs}", timeout=10) as r:
            data = json.loads(r.read())
        for result in data.get("results", []):
            aur_versions[result["Name"]] = result.get("Version", "")
    except Exception:
        pass

    pkg_cache = _get_pkg_cache()
    pkg_entries = {e.get("name"): e for e in pkg_cache.get_all() if e.get("name")}

    for item_id in all_ids:
        if item_id in aur_versions:
            store.update(item_id, {"upstream_version": aur_versions[item_id]})
        else:
            item = all_items[item_id]
            source_url = item.get("source_url", "")
            source_sub = item.get("source_subdir", "")
            upstream = ""
            if source_url and source_sub:
                upstream, _ = _version_from_pkgbuild_url(source_url, source_sub)
            if not upstream and item_id in pkg_entries:
                entry = pkg_entries[item_id]
                ver = entry.get("pkgver") or entry.get("version") or ""
                rel = entry.get("pkgrel", "")
                upstream = f"{ver}-{rel}" if rel else ver
            if upstream:
                store.update(item_id, {"upstream_version": upstream})

    return render(request, "content.html", _ctx())


# CRUD-Router am Ende einbinden – eigene Routen oben haben Vorrang (first-match)
router.include_router(_crud)

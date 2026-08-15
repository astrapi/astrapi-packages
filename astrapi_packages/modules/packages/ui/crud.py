"""astrapi_packages.modules.packages.ui.crud – FastAPI-UI-Router für das
generische Pakete-Modul (ersetzt debian/archlinux ui/crud.py, siehe
projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul").

Bewusst nicht mehr enthalten: die AUR/pkg_cache-basierte "Suchen &
übernehmen"-Funktion (T-156) -- OS-spezifische externe API-Integration,
entfällt im generischen Kern (siehe Plan-Abschnitt "Bewusst gestrichen").
"""

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.render import render
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_packages.api import status as _status
from astrapi_packages.modules.packages import KEY, store
from astrapi_packages.modules.packages.storage import make_id
from astrapi_packages.utils import file_store, pkgbuild
from astrapi_packages.utils.export_import import build_export_import_routes
from astrapi_packages.utils.file_routes import build_file_routes
from astrapi_packages.utils.git_import import GitImportError, import_package_from_git

_DIR = Path(__file__).parent.parent
_EXPORT_FIELDS = [
    "name",
    "os_type",
    "source_url",
    "source_subdir",
    "depends",
    "image",
    "pkg_type",
    "enabled",
    "source_type",
]

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
    description_field="id",
    has_run_buttons=True,
    has_toggle=False,
    running_fn=_running_fn,
)

router = APIRouter()


def _os_type_options() -> list[dict]:
    from astrapi_packages.modules.os_types import store as os_types_store

    return [{"value": k, "label": v.get("label") or k} for k, v in os_types_store.list().items()]


def _image_options() -> list[dict]:
    from astrapi_packages.modules.builder import store as builder_store

    opts = [
        {"value": img_id, "label": f"{img_id}:{cfg.get('tag', 'latest')}"}
        for img_id, cfg in builder_store.list().items()
    ]
    return [{"value": "", "label": "(kein Image gewählt)"}, *opts]


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
            os_type_options=_os_type_options(),
            image_options=_image_options(),
        ),
    )


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def create_apply(request: Request):
    form = await request.form()
    name = form.get("name", "").strip()
    os_type = form.get("os_type", "").strip()

    if not name or not os_type:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(
                item_id=None,
                item=dict(form),
                error="OS-Typ und Paketname sind erforderlich.",
                os_type_options=_os_type_options(),
                image_options=_image_options(),
            ),
        )

    item_id = make_id(os_type, name)
    if store.get(item_id) is not None:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(
                item_id=None,
                item=dict(form),
                error=f"'{item_id}' ist bereits vorhanden.",
                os_type_options=_os_type_options(),
                image_options=_image_options(),
            ),
        )

    data = {
        "name": name,
        "os_type": os_type,
        "source_url": form.get("source_url", "").strip(),
        "source_subdir": form.get("source_subdir", "").strip(),
        "image": form.get("image", "").strip(),
        "pkg_type": form.get("pkg_type", "package").strip() or "package",
        "enabled": "enabled" in form,
        "last_status": _status.NEU,
    }
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
    return render(
        request,
        "dialog_new_in_db.html",
        dict(module=KEY, error=None, os_type_options=_os_type_options()),
    )


@router.post(f"/ui/{KEY}/new-in-db", response_class=HTMLResponse)
async def new_in_db_apply(request: Request):
    form = await request.form()
    name = form.get("name", "").strip()
    os_type = form.get("os_type", "").strip()
    os_type_opts = _os_type_options()

    if not name or not os_type:
        return render(
            request,
            "dialog_new_in_db.html",
            dict(
                module=KEY,
                error="OS-Typ und Paketname sind erforderlich.",
                os_type_options=os_type_opts,
            ),
        )
    item_id = make_id(os_type, name)
    if store.get(item_id) is not None:
        return render(
            request,
            "dialog_new_in_db.html",
            dict(
                module=KEY,
                error=f"'{item_id}' ist bereits vorhanden.",
                os_type_options=os_type_opts,
            ),
        )
    store.create(
        item_id,
        {
            "name": name,
            "os_type": os_type,
            "pkg_type": "package",
            "enabled": True,
            "last_status": _status.NEU,
            "source_type": "db",
        },
    )
    file_store.save(
        KEY, item_id, "PKGBUILD", _PKGBUILD_TEMPLATE.format(name=name), message="Neu erstellt"
    )
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(item_id=item_id, item=store.get(item_id), error=None, image_options=_image_options()),
    )


# ── Auf Updates prüfen ───────────────────────────────────────────────────────


@router.post(f"/ui/{KEY}/check-updates", response_class=HTMLResponse)
def check_updates(request: Request):
    """Prüft für alle Pakete ob eine neue Version verfügbar ist -- generisch
    per PKGBUILD-Parsing (utils/pkgbuild.py), kein AUR-Batch-Call mehr."""
    all_items = store.list()
    if not all_items:
        return render(request, "content.html", _ctx())

    for k, v in all_items.items():
        if v.get("last_status") not in _status.AUTO_UPDATE and v.get("upstream_version"):
            store.update(k, {"upstream_version": ""})

    for item_id, item in all_items.items():
        if item.get("last_status") not in _status.AUTO_UPDATE:
            continue
        source_type = (item.get("source_type") or "git").strip()
        if source_type == "db":
            upstream, _ = pkgbuild.read_local_pkgbuild(KEY, item_id)
        else:
            source_url = item.get("source_url", "").strip()
            if not source_url:
                continue
            upstream, _ = pkgbuild.read_remote_pkgbuild(
                source_url, item.get("source_subdir", "").strip() or item.get("name", "")
            )
        if upstream:
            store.update(item_id, {"upstream_version": upstream})

    return render(request, "content.html", _ctx())


# ── CRUD-Router einbinden ─────────────────────────────────────────────────────

router.include_router(_crud)
router.include_router(build_file_routes(KEY))
router.include_router(build_export_import_routes(KEY, store, _EXPORT_FIELDS))

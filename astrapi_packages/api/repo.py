"""astrapi_packages.api.repo – Pacman/APT-Repository HTTP-Server unter /."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from astrapi_core.ui.file_listing import (
    list_dir_entries,
    render_link_row,
    render_page as _page,
    render_row,
    safe_child as _safe_child,
)

router = APIRouter()

# Distros und Architektur-Unterordner (leere Liste = flaches Layout)
_DISTROS: dict[str, list[str]] = {
    "archlinux": ["x86_64"],
    "debian": [],
}
_FLAT_DISTROS = {"debian"}


def _arch_dir() -> Path:
    from astrapi_packages._paths import arch_repo_dir

    return arch_repo_dir() / "x86_64"


def _debian_dir() -> Path:
    from astrapi_packages._paths import debian_repo_dir

    return debian_repo_dir()


# ---------------------------------------------------------------------------
# /  –  Distro-Übersicht
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def files_index():
    rows = [render_link_row(d + "/", f"/{d}/") for d in _DISTROS]
    cg = '<colgroup><col class="c-name1"></colgroup>'
    return HTMLResponse(
        _page(
            "Packages",
            '<a href="/admin">Zum Dashboard →</a>',
            rows,
            col_headers=("Name",),
            colgroup=cg,
            empty_message="Keine Distributionen konfiguriert.",
        )
    )


# ---------------------------------------------------------------------------
# /{distro}  →  /{distro}/
# ---------------------------------------------------------------------------
@router.get("/{distro}", include_in_schema=False)
def distro_redirect(distro: str):
    if distro not in _DISTROS:
        raise HTTPException(404, "Unbekannte Distribution")
    return RedirectResponse(f"/{distro}/", status_code=301)


# ---------------------------------------------------------------------------
# /debian/  –  APT-Repository-Listing
# ---------------------------------------------------------------------------
@router.get("/debian/", response_class=HTMLResponse, include_in_schema=False)
def debian_listing():
    d = _debian_dir()

    if not d.exists():
        rows = []
        empty_message = "Repository-Verzeichnis noch nicht vorhanden."
    else:
        entries = [e for e in list_dir_entries(d, lambda name, _: f"/debian/{name}") if not e.is_dir]
        rows = [render_row(e) for e in entries]
        empty_message = "Keine Dateien vorhanden."

    return HTMLResponse(
        _page(
            "debian Packages", "", rows, back="/",
            col_headers=("Name", "Geändert", "Größe"), empty_message=empty_message,
        )
    )


# ---------------------------------------------------------------------------
# /debian/{path:path}  –  Datei-Download (APT normalisiert ./ → Dateiname)
# ---------------------------------------------------------------------------
@router.get("/debian/{path:path}", include_in_schema=False)
def debian_file(path: str):
    clean = path.removeprefix("./").lstrip("/")
    if not clean or "/" in clean:
        raise HTTPException(400, "Ungültiger Pfad")
    fp = _safe_child(_debian_dir(), clean)
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(str(fp))


# ---------------------------------------------------------------------------
# /{distro}/  –  Architektur-Übersicht (nicht-flache Distros)
# ---------------------------------------------------------------------------
@router.get("/{distro}/", response_class=HTMLResponse, include_in_schema=False)
def distro_index(distro: str):
    if distro not in _DISTROS or distro in _FLAT_DISTROS:
        raise HTTPException(404, "Unbekannte Distribution")

    arches = _DISTROS[distro]
    rows = [render_link_row(arch + "/", f"/{distro}/{arch}/") for arch in arches]
    cg = '<colgroup><col class="c-name1"></colgroup>'
    return HTMLResponse(
        _page(f"{distro} Packages", "", rows, back="/", col_headers=("Name",), colgroup=cg)
    )


# ---------------------------------------------------------------------------
# /{distro}/{arch}  →  /{distro}/{arch}/
# ---------------------------------------------------------------------------
@router.get("/{distro}/{arch}", include_in_schema=False)
def arch_redirect(distro: str, arch: str):
    if distro not in _DISTROS or arch not in _DISTROS.get(distro, []):
        raise HTTPException(404)
    return RedirectResponse(f"/{distro}/{arch}/", status_code=301)


# ---------------------------------------------------------------------------
# /{distro}/{arch}/  –  Datei-Listing
# ---------------------------------------------------------------------------
@router.get("/{distro}/{arch}/", response_class=HTMLResponse, include_in_schema=False)
def arch_listing(distro: str, arch: str):
    if distro not in _DISTROS or arch not in _DISTROS.get(distro, []):
        raise HTTPException(404)

    d = _arch_dir()

    if not d.exists():
        rows = []
        empty_message = "Repository-Verzeichnis noch nicht vorhanden."
    else:
        entries = [
            e for e in list_dir_entries(d, lambda name, _: f"/{distro}/{arch}/{name}")
            if not e.is_dir
        ]
        rows = [render_row(e) for e in entries]
        empty_message = "Keine Dateien vorhanden."

    return HTMLResponse(
        _page(
            f"{distro} Packages",
            "",
            rows,
            back=f"/{distro}/",
            col_headers=("Name", "Geändert", "Größe"),
            empty_message=empty_message,
        )
    )


# ---------------------------------------------------------------------------
# /{distro}/{arch}/{filename}  –  Datei-Download
# ---------------------------------------------------------------------------
@router.get("/{distro}/{arch}/{filename}", include_in_schema=False)
def arch_file(distro: str, arch: str, filename: str):
    if distro not in _DISTROS or arch not in _DISTROS.get(distro, []):
        raise HTTPException(404)
    fp = _safe_child(_arch_dir(), filename)
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(str(fp))

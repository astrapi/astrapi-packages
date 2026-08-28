"""astrapi_packages.api.repo – Pacman/APT-Repository HTTP-Server unter /files/."""

import html as _html
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from astrapi_core.ui.file_listing import (
    list_dir_entries,
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
# /files  →  /files/
# ---------------------------------------------------------------------------
@router.get("/files", include_in_schema=False)
def files_redirect():
    return RedirectResponse("/files/", status_code=301)


# ---------------------------------------------------------------------------
# /files/  –  Distro-Übersicht
# ---------------------------------------------------------------------------
@router.get("/files/", response_class=HTMLResponse, include_in_schema=False)
def files_index():
    rows = "\n".join(
        f'<tr><td><a href="/files/{d}/">{_html.escape(d)}/</a></td></tr>'
        for d in _DISTROS
    )
    cg = '<colgroup><col class="c-name1"></colgroup>'
    return HTMLResponse(
        _page(
            "Packages",
            "",
            rows or "<tr><td>Keine Distributionen konfiguriert.</td></tr>",
            col_headers=("Name",),
            colgroup=cg,
        )
    )


# ---------------------------------------------------------------------------
# /files/{distro}  →  /files/{distro}/
# ---------------------------------------------------------------------------
@router.get("/files/{distro}", include_in_schema=False)
def distro_redirect(distro: str):
    if distro not in _DISTROS:
        raise HTTPException(404, "Unbekannte Distribution")
    return RedirectResponse(f"/files/{distro}/", status_code=301)


# ---------------------------------------------------------------------------
# /files/debian/  –  APT-Repository-Listing
# ---------------------------------------------------------------------------
@router.get("/files/debian/", response_class=HTMLResponse, include_in_schema=False)
def debian_listing():
    d = _debian_dir()

    if not d.exists():
        rows = '<tr><td colspan="3">Repository-Verzeichnis noch nicht vorhanden.</td></tr>'
    else:
        entries = [e for e in list_dir_entries(d, lambda name, _: f"/files/debian/{name}") if not e.is_dir]
        rows = "\n".join(render_row(e) for e in entries) or '<tr><td colspan="3">Keine Dateien vorhanden.</td></tr>'

    return HTMLResponse(
        _page("debian Packages", "", rows, back="/files/", col_headers=("Name", "Geändert", "Größe"))
    )


# ---------------------------------------------------------------------------
# /files/debian/{path:path}  –  Datei-Download (APT normalisiert ./ → Dateiname)
# ---------------------------------------------------------------------------
@router.get("/files/debian/{path:path}", include_in_schema=False)
def debian_file(path: str):
    clean = path.removeprefix("./").lstrip("/")
    if not clean or "/" in clean:
        raise HTTPException(400, "Ungültiger Pfad")
    fp = _safe_child(_debian_dir(), clean)
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(str(fp))


# ---------------------------------------------------------------------------
# /files/{distro}/  –  Architektur-Übersicht (nicht-flache Distros)
# ---------------------------------------------------------------------------
@router.get("/files/{distro}/", response_class=HTMLResponse, include_in_schema=False)
def distro_index(distro: str):
    if distro not in _DISTROS or distro in _FLAT_DISTROS:
        raise HTTPException(404, "Unbekannte Distribution")

    arches = _DISTROS[distro]
    rows = "\n".join(
        f'<tr><td><a href="/files/{distro}/{arch}/">{arch}/</a></td></tr>'
        for arch in arches
    )
    cg = '<colgroup><col class="c-name1"></colgroup>'
    return HTMLResponse(
        _page(f"{distro} Packages", "", rows, back="/files/", col_headers=("Name",), colgroup=cg)
    )


# ---------------------------------------------------------------------------
# /files/{distro}/{arch}  →  /files/{distro}/{arch}/
# ---------------------------------------------------------------------------
@router.get("/files/{distro}/{arch}", include_in_schema=False)
def arch_redirect(distro: str, arch: str):
    if distro not in _DISTROS or arch not in _DISTROS.get(distro, []):
        raise HTTPException(404)
    return RedirectResponse(f"/files/{distro}/{arch}/", status_code=301)


# ---------------------------------------------------------------------------
# /files/{distro}/{arch}/  –  Datei-Listing
# ---------------------------------------------------------------------------
@router.get("/files/{distro}/{arch}/", response_class=HTMLResponse, include_in_schema=False)
def arch_listing(distro: str, arch: str):
    if distro not in _DISTROS or arch not in _DISTROS.get(distro, []):
        raise HTTPException(404)

    d = _arch_dir()

    if not d.exists():
        rows = '<tr><td colspan="3">Repository-Verzeichnis noch nicht vorhanden.</td></tr>'
    else:
        entries = [
            e for e in list_dir_entries(d, lambda name, _: f"/files/{distro}/{arch}/{name}")
            if not e.is_dir
        ]
        rows = "\n".join(render_row(e) for e in entries) or '<tr><td colspan="3">Keine Dateien vorhanden.</td></tr>'

    return HTMLResponse(
        _page(
            f"{distro} Packages",
            "",
            rows,
            back=f"/files/{distro}/",
            col_headers=("Name", "Geändert", "Größe"),
        )
    )


# ---------------------------------------------------------------------------
# /files/{distro}/{arch}/{filename}  –  Datei-Download
# ---------------------------------------------------------------------------
@router.get("/files/{distro}/{arch}/{filename}", include_in_schema=False)
def arch_file(distro: str, arch: str, filename: str):
    if distro not in _DISTROS or arch not in _DISTROS.get(distro, []):
        raise HTTPException(404)
    fp = _safe_child(_arch_dir(), filename)
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(str(fp))

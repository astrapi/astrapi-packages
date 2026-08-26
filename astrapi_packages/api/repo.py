"""astrapi_packages.api.repo – Pacman/APT-Repository HTTP-Server unter /files/."""

import html as _html
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

router = APIRouter()

_UNITS = [("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)]

# Distros und Architektur-Unterordner (leere Liste = flaches Layout)
_DISTROS: dict[str, list[str]] = {
    "archlinux": ["x86_64"],
    "debian": [],
}
_FLAT_DISTROS = {"debian"}

_CSS = """
    @font-face { font-family:'JetBrains Mono'; src:url('/static/fonts/mono.woff2') format('woff2'); }
    :root { --mono:'JetBrains Mono',ui-monospace,monospace; }
    body { font-family:var(--mono); font-size:.85rem; padding:2rem; background:#0d1117; color:#c9d1d9; }
    h1 { color:#58a6ff; margin-bottom:.25rem; }
    p.back { margin-bottom:1rem; font-size:.85rem; }
    table { border-collapse:collapse; width:100%; table-layout:fixed; }
    col.c-name { width:70%; }
    col.c-size { width:30%; }
    col.c-name1 { width:100%; }
    thead th { text-align:left; padding:.4rem 1rem; border-bottom:2px solid #30363d;
               color:#8b949e; font-size:.8rem; font-weight:600; letter-spacing:.04em; }
    thead th.r { text-align:right; }
    td { padding:.35rem 1rem; border-bottom:1px solid #21262d; vertical-align:middle; overflow:hidden; }
    td.num { text-align:right; color:#8b949e; white-space:nowrap; }
    a { text-decoration:none; color:#58a6ff; }
    a:hover { text-decoration:underline; }
"""


def _page(title: str, body_html: str, back: str | None = None) -> str:
    back_html = f'<p class="back"><a href="{back}">← Zurück</a></p>' if back else ""
    return (
        f'<!DOCTYPE html><html lang="de">'
        f'<head><meta charset="utf-8"><title>{_html.escape(title)}</title>'
        f'<style>{_CSS}</style></head>'
        f'<body>{back_html}<h1>{_html.escape(title)}</h1>{body_html}</body></html>'
    )


def _table(rows_html: str, headers: tuple[str, ...], colgroup: str = "") -> str:
    ths = "".join(
        f'<th class="r">{h}</th>' if h in ("Größe",) else f'<th>{h}</th>'
        for h in headers
    )
    return (
        f"<table>{colgroup}"
        f"<thead><tr>{ths}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table>"
    )


def _fmt_size(n: int) -> str:
    for unit, div in _UNITS:
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


def _safe_child(base: Path, *parts: str) -> Path:
    resolved = (base / Path(*parts)).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise HTTPException(400, "Ungültiger Pfad")
    return resolved


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
    body = _table(rows or "<tr><td>Keine Distributionen konfiguriert.</td></tr>", ("Name",), cg)
    return HTMLResponse(_page("Packages", body))


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
        rows = '<tr><td colspan="2">Repository-Verzeichnis noch nicht vorhanden.</td></tr>'
    else:
        files = sorted((f for f in d.iterdir() if f.is_file()), key=lambda f: f.name)
        rows = "\n".join(
            f'<tr><td><a href="/files/debian/{_html.escape(f.name)}">{_html.escape(f.name)}</a></td>'
            f'<td class="num">{_fmt_size(f.stat().st_size)}</td></tr>'
            for f in files
        ) or '<tr><td colspan="2">Keine Dateien vorhanden.</td></tr>'

    cg = '<colgroup><col class="c-name"><col class="c-size"></colgroup>'
    return HTMLResponse(_page("debian Packages", _table(rows, ("Name", "Größe"), cg), back="/files/"))


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
    body = _table(rows, ("Name",), cg)
    return HTMLResponse(_page(f"{distro} Packages", body, back="/files/"))


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
        rows = '<tr><td colspan="2">Repository-Verzeichnis noch nicht vorhanden.</td></tr>'
    else:
        files = sorted((f for f in d.iterdir() if f.is_file()), key=lambda f: f.name)
        rows = "\n".join(
            f'<tr><td><a href="/files/{distro}/{arch}/{_html.escape(f.name)}">{_html.escape(f.name)}</a></td>'
            f'<td class="num">{_fmt_size(f.stat().st_size)}</td></tr>'
            for f in files
        ) or '<tr><td colspan="2">Keine Dateien vorhanden.</td></tr>'

    cg = '<colgroup><col class="c-name"><col class="c-size"></colgroup>'
    body = _table(rows, ("Name", "Größe"), cg)
    return HTMLResponse(_page(f"{distro} Packages", body, back=f"/files/{distro}/"))


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

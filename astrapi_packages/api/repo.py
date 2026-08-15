"""astrapi_packages.api.repo – Pacman/APT-Repository HTTP-Server unter /files/.

Generisch seit dem "Virtuellen OS-Modul" (siehe
projects/packages/planung-datei-editor.md): statt eines hart codierten
_DISTROS-Dicts kommt die Liste der OS-Typen und ihr Repo-Unterordner
(repo_subdir) jetzt aus der os_types-Tabelle. Ein OS-Typ = ein Unterordner
unter /files/, dessen Inhalt rekursiv (repo_base/repo_subdir) ausgeliefert
wird -- keine Sonderbehandlung mehr für "hat Architektur-Unterordner" o.ä.,
das steckt im repo_subdir-Wert selbst (z.B. "arch/x86_64").

ACHTUNG Betriebs-Konsequenz: die URL-Struktur ändert sich dadurch ggü. den
bisherigen fest verdrahteten Pfaden (z.B. /files/archlinux/x86_64/... wird
zu /files/archlinux/... wenn repo_subdir="arch/x86_64" gesetzt wird) --
sources.list/pacman.conf auf anderen Maschinen müssen entsprechend
nachgezogen werden.
"""

import html as _html
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

router = APIRouter()

_UNITS = [("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)]

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


def _os_types() -> dict:
    from astrapi_packages.modules.os_types import store as os_types_store

    return os_types_store.list()


def _page(title: str, body_html: str, back: str | None = None) -> str:
    back_html = f'<p class="back"><a href="{back}">← Zurück</a></p>' if back else ""
    return (
        f'<!DOCTYPE html><html lang="de">'
        f'<head><meta charset="utf-8"><title>{_html.escape(title)}</title>'
        f"<style>{_CSS}</style></head>"
        f"<body>{back_html}<h1>{_html.escape(title)}</h1>{body_html}</body></html>"
    )


def _table(rows_html: str, headers: tuple[str, ...], colgroup: str = "") -> str:
    ths = "".join(
        f'<th class="r">{h}</th>' if h in ("Größe",) else f"<th>{h}</th>" for h in headers
    )
    return f"<table>{colgroup}<thead><tr>{ths}</tr></thead><tbody>{rows_html}</tbody></table>"


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


def _os_type_dir(os_type: str) -> Path:
    from astrapi_packages.utils.build_runner import repo_path

    row = _os_types().get(os_type)
    if row is None:
        raise HTTPException(404, "Unbekannter OS-Typ")
    try:
        return repo_path(row.get("repo_subdir", ""))
    except Exception as e:
        raise HTTPException(500, str(e)) from e


# ---------------------------------------------------------------------------
# /files  →  /files/
# ---------------------------------------------------------------------------
@router.get("/files", include_in_schema=False)
def files_redirect():
    return RedirectResponse("/files/", status_code=301)


# ---------------------------------------------------------------------------
# /files/  –  OS-Typ-Übersicht
# ---------------------------------------------------------------------------
@router.get("/files/", response_class=HTMLResponse, include_in_schema=False)
def files_index():
    rows = "\n".join(
        f'<tr><td><a href="/files/{_html.escape(k)}/">{_html.escape(k)}/</a></td></tr>'
        for k in _os_types()
    )
    cg = '<colgroup><col class="c-name1"></colgroup>'
    body = _table(rows or "<tr><td>Keine OS-Typen angelegt.</td></tr>", ("Name",), cg)
    return HTMLResponse(_page("Packages", body))


# ---------------------------------------------------------------------------
# /files/{os_type}  →  /files/{os_type}/
# ---------------------------------------------------------------------------
@router.get("/files/{os_type}", include_in_schema=False)
def os_type_redirect(os_type: str):
    if os_type not in _os_types():
        raise HTTPException(404, "Unbekannter OS-Typ")
    return RedirectResponse(f"/files/{os_type}/", status_code=301)


# ---------------------------------------------------------------------------
# /files/{os_type}/  –  Datei-Listing (rekursiv unter repo_subdir)
# ---------------------------------------------------------------------------
@router.get("/files/{os_type}/", response_class=HTMLResponse, include_in_schema=False)
def os_type_listing(os_type: str):
    d = _os_type_dir(os_type)

    if not d.exists():
        rows = '<tr><td colspan="2">Repository-Verzeichnis noch nicht vorhanden.</td></tr>'
    else:
        files = sorted((f for f in d.rglob("*") if f.is_file()), key=lambda f: str(f))
        rows = (
            "\n".join(
                f'<tr><td><a href="/files/{os_type}/{_html.escape(str(f.relative_to(d)))}">'
                f"{_html.escape(str(f.relative_to(d)))}</a></td>"
                f'<td class="num">{_fmt_size(f.stat().st_size)}</td></tr>'
                for f in files
            )
            or '<tr><td colspan="2">Keine Dateien vorhanden.</td></tr>'
        )

    cg = '<colgroup><col class="c-name"><col class="c-size"></colgroup>'
    return HTMLResponse(
        _page(f"{os_type} Packages", _table(rows, ("Name", "Größe"), cg), back="/files/")
    )


# ---------------------------------------------------------------------------
# /files/{os_type}/{path:path}  –  Datei-Download (APT normalisiert ./ → Dateiname)
# ---------------------------------------------------------------------------
@router.get("/files/{os_type}/{path:path}", include_in_schema=False)
def os_type_file(os_type: str, path: str):
    clean = path.removeprefix("./").lstrip("/")
    if not clean:
        raise HTTPException(400, "Ungültiger Pfad")
    fp = _safe_child(_os_type_dir(os_type), clean)
    if not fp.exists() or not fp.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(str(fp))

"""astrapi_packages.api.repo – Pacman/APT-Repository HTTP-Server."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from astrapi_packages._paths import repo_dir

router = APIRouter()

_UNITS = [("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)]

# Bekannte Distros → lokales Verzeichnis
_DISTROS: dict[str, str] = {
    "arch": "arch",  # work_dir/repo/arch  (aktuell: work_dir/repo als Fallback)
}


def _distro_dir(distro: str):
    """Gibt das Verzeichnis für eine Distro zurück."""
    base = repo_dir()
    # Wenn work_dir/repo/arch existiert, nutze das; sonst work_dir/repo direkt (Bestandskompatibilität)
    sub = base / distro
    return sub if sub.exists() else base


def _fmt_size(n: int) -> str:
    for unit, div in _UNITS:
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


_CSS = """
    body { font-family: monospace; padding: 2rem; background: #0d1117; color: #c9d1d9; }
    h1 { color: #58a6ff; margin-bottom: 0.25rem; }
    p.hint { color: #8b949e; font-size: 0.85rem; margin-bottom: 1.5rem; }
    table { border-collapse: collapse; width: 100%; }
    thead th { text-align: left; padding: 0.4rem 1rem; border-bottom: 2px solid #30363d; color: #8b949e; }
    td { padding: 0.3rem 1rem; border-bottom: 1px solid #21262d; }
    td.size { text-align: right; color: #8b949e; white-space: nowrap; }
    a { text-decoration: none; color: #58a6ff; }
    a:hover { text-decoration: underline; }
"""


def _page(title: str, hint: str, rows_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>{_CSS}</style>
</head>
<body>
  <h1>{title}</h1>
  <p class="hint">{hint}</p>
  <table>
    <thead><tr><th>Name</th><th>Größe</th></tr></thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# /repo  →  /repo/
# ---------------------------------------------------------------------------
@router.get("/repo", include_in_schema=False)
def repo_redirect():
    return RedirectResponse(url="/repo/", status_code=301)


# ---------------------------------------------------------------------------
# /repo/  –  Top-Level: Distro-Übersicht
# ---------------------------------------------------------------------------
@router.get("/repo/", response_class=HTMLResponse, include_in_schema=False)
def repo_index():
    rows = "\n".join(
        f'<tr><td><a href="/repo/{distro}/">{distro}/</a></td><td class="size">—</td></tr>'
        for distro in _DISTROS
    )
    return HTMLResponse(_page(
        title="Repository",
        hint="Verfügbare Distributionen",
        rows_html=rows or '<tr><td colspan="2">Keine Distributionen konfiguriert.</td></tr>',
    ))


# ---------------------------------------------------------------------------
# /repo/{distro}  →  /repo/{distro}/
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}", include_in_schema=False)
def distro_redirect(distro: str):
    if distro not in _DISTROS:
        raise HTTPException(status_code=404, detail="Unbekannte Distribution")
    return RedirectResponse(url=f"/repo/{distro}/", status_code=301)


# ---------------------------------------------------------------------------
# /repo/{distro}/  –  Datei-Listing
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}/", response_class=HTMLResponse, include_in_schema=False)
def distro_listing(distro: str):
    if distro not in _DISTROS:
        raise HTTPException(status_code=404, detail="Unbekannte Distribution")

    d = _distro_dir(distro)
    if not d.exists():
        return HTMLResponse(
            "<html><body><p>Repository-Verzeichnis nicht vorhanden.</p></body></html>",
            status_code=404,
        )

    files = sorted((f for f in d.iterdir() if f.is_file()), key=lambda f: f.name)
    rows = "\n".join(
        f'<tr><td><a href="/repo/{distro}/{f.name}">{f.name}</a></td>'
        f'<td class="size">{_fmt_size(f.stat().st_size)}</td></tr>'
        for f in files
    )
    return HTMLResponse(_page(
        title=f"Repository · {distro}",
        hint=f'pacman.conf: <code>Server = http://&lt;host&gt;/repo/{distro}</code>',
        rows_html=rows or '<tr><td colspan="2">Keine Dateien vorhanden.</td></tr>',
    ))


# ---------------------------------------------------------------------------
# /repo/{distro}/{filename}  –  Datei-Download
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}/{filename}", include_in_schema=False)
def distro_file(distro: str, filename: str):
    if distro not in _DISTROS:
        raise HTTPException(status_code=404, detail="Unbekannte Distribution")

    d = _distro_dir(distro)
    path = (d / filename).resolve()
    # Pfad-Traversal verhindern
    if not str(path).startswith(str(d.resolve())):
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(str(path))

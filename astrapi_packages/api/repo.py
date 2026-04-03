"""astrapi_packages.api.repo – Pacman/APT-Repository HTTP-Server."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from astrapi_packages._paths import repo_dir

router = APIRouter()

_UNITS = [("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)]

# Bekannte Distros → unterstützte Architekturen
_DISTROS: dict[str, list[str]] = {
    "arch": ["x86_64"],
}


def _configured_repo_base() -> Path:
    """Gibt den konfigurierten Repository-Pfad zurück (Einstellung 'repo_path' aus pakete-Modul)."""
    from astrapi.core.ui.settings_registry import get_module
    from astrapi_packages._paths import repo_dir as _repo_dir
    raw = get_module("pakete", "repo_path", default="")
    return Path(raw).resolve() if raw else _repo_dir().resolve()


def _arch_dir(distro: str, arch: str) -> Path:
    """Verzeichnis für distro/arch – mit Fallback auf flache Struktur."""
    base = _configured_repo_base()
    # Tiefe Struktur: base/arch/x86_64/
    deep = base / distro / arch
    if deep.exists():
        return deep
    # Flache Struktur: base/ (Bestandskompatibilität)
    return base


def _fmt_size(n: int) -> str:
    for unit, div in _UNITS:
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


_CSS = """
    body { font-family: monospace; padding: 2rem; background: #0d1117; color: #c9d1d9; }
    h1 { color: #58a6ff; margin-bottom: 0.25rem; }
    p.hint { color: #8b949e; font-size: 0.85rem; margin-bottom: 1.5rem; }
    p.back { margin-bottom: 1rem; font-size: 0.85rem; }
    table { border-collapse: collapse; width: 100%; }
    thead th { text-align: left; padding: 0.4rem 1rem; border-bottom: 2px solid #30363d; color: #8b949e; }
    td { padding: 0.3rem 1rem; border-bottom: 1px solid #21262d; }
    td.size { text-align: right; color: #8b949e; white-space: nowrap; }
    a { text-decoration: none; color: #58a6ff; }
    a:hover { text-decoration: underline; }
"""


def _page(title: str, hint: str, rows_html: str, back: str | None = None) -> str:
    back_html = f'<p class="back"><a href="{back}">← Zurück</a></p>' if back else ""
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>{_CSS}</style>
</head>
<body>
  {back_html}
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
# /repo/  –  Distro-Übersicht
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
# /repo/{distro}/  –  Architektur-Übersicht
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}/", response_class=HTMLResponse, include_in_schema=False)
def distro_index(request: Request, distro: str):
    if distro not in _DISTROS:
        raise HTTPException(status_code=404, detail="Unbekannte Distribution")

    base_url = str(request.base_url).rstrip("/")
    arches = _DISTROS[distro]
    rows = "\n".join(
        f'<tr><td><a href="/repo/{distro}/{arch}/">{arch}/</a></td><td class="size">—</td></tr>'
        for arch in arches
    )
    return HTMLResponse(_page(
        title=f"Repository · {distro}",
        hint=f'pacman.conf: <code>Server = {base_url}/repo/{distro}/$arch</code>',
        rows_html=rows,
        back="/repo/",
    ))


# ---------------------------------------------------------------------------
# /repo/{distro}/{arch}  →  /repo/{distro}/{arch}/
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}/{arch}", include_in_schema=False)
def arch_redirect(distro: str, arch: str):
    if distro not in _DISTROS or arch not in _DISTROS[distro]:
        raise HTTPException(status_code=404)
    return RedirectResponse(url=f"/repo/{distro}/{arch}/", status_code=301)


# ---------------------------------------------------------------------------
# /repo/{distro}/{arch}/  –  Datei-Listing
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}/{arch}/", response_class=HTMLResponse, include_in_schema=False)
def arch_listing(request: Request, distro: str, arch: str):
    if distro not in _DISTROS or arch not in _DISTROS[distro]:
        raise HTTPException(status_code=404)

    d = _arch_dir(distro, arch)
    if not d.exists():
        return HTMLResponse(
            "<html><body><p>Repository-Verzeichnis nicht vorhanden.</p></body></html>",
            status_code=404,
        )

    base_url = str(request.base_url).rstrip("/")
    files = sorted((f for f in d.iterdir() if f.is_file()), key=lambda f: f.name)
    rows = "\n".join(
        f'<tr><td><a href="/repo/{distro}/{arch}/{f.name}">{f.name}</a></td>'
        f'<td class="size">{_fmt_size(f.stat().st_size)}</td></tr>'
        for f in files
    )
    return HTMLResponse(_page(
        title=f"Repository · {distro} · {arch}",
        hint=f'pacman.conf: <code>Server = {base_url}/repo/{distro}/$arch</code>',
        rows_html=rows or '<tr><td colspan="2">Keine Dateien vorhanden.</td></tr>',
        back=f"/repo/{distro}/",
    ))


# ---------------------------------------------------------------------------
# /repo/{distro}/{arch}/{filename}  –  Datei-Download
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}/{arch}/{filename}", include_in_schema=False)
def arch_file(distro: str, arch: str, filename: str):
    if distro not in _DISTROS or arch not in _DISTROS[distro]:
        raise HTTPException(status_code=404)

    d = _arch_dir(distro, arch)
    path = (d / filename).resolve()
    if not str(path).startswith(str(d.resolve())):
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(str(path))

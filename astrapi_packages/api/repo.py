"""astrapi_packages.api.repo – Pacman/APT-Repository HTTP-Server."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

router = APIRouter()

_UNITS = [("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)]

# Bekannte Distros → unterstützte Architekturen (leere Liste = flaches Layout)
_DISTROS: dict[str, list[str]] = {
    "arch": ["x86_64"],
    "debian": [],  # flaches Layout: repo/debian/*.deb
}

# Flache Distros: kein Arch-Unterordner, Dateien direkt im Distro-Verzeichnis
_FLAT_DISTROS = {"debian"}


def _configured_repo_base() -> Path:
    """Gibt den konfigurierten Repository-Pfad zurück (Einstellung 'repo_path' aus dem archlinux-Modul)."""
    from astrapi_core.ui.settings_registry import get_module

    from astrapi_packages._paths import repo_dir as _repo_dir

    raw = get_module("archlinux", "repo_path", default="")
    return Path(raw).resolve() if raw else _repo_dir().resolve()


def _debian_repo_dir() -> Path:
    """Gibt das konfigurierte Debian-Repository-Verzeichnis zurück."""
    from astrapi_core.ui.settings_registry import get_module

    from astrapi_packages._paths import repo_dir as _repo_dir

    raw = get_module("debian", "repo_path", default="")
    if raw:
        return (Path(raw) / "debian").resolve()
    return (_repo_dir() / "debian").resolve()


def _arch_dir(distro: str, arch: str) -> Path:
    """Verzeichnis für distro/arch."""
    return _configured_repo_base() / distro / arch


def _fmt_size(n: int) -> str:
    for unit, div in _UNITS:
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


_CSS = """
    body { font-family: monospace; padding: 2rem; background: #0d1117; color: #c9d1d9; }
    h1 { color: #58a6ff; margin-bottom: 0.25rem; }
    h2 { color: #58a6ff; font-size: 1rem; margin: 1.5rem 0 0.5rem; }
    p.hint { color: #8b949e; font-size: 0.85rem; margin-bottom: 1.5rem; }
    p.back { margin-bottom: 1rem; font-size: 0.85rem; }
    table { border-collapse: collapse; width: 100%; }
    thead th { text-align: left; padding: 0.4rem 1rem; border-bottom: 2px solid #30363d; color: #8b949e; }
    td { padding: 0.3rem 1rem; border-bottom: 1px solid #21262d; }
    td.size { text-align: right; color: #8b949e; white-space: nowrap; }
    a { text-decoration: none; color: #58a6ff; }
    a:hover { text-decoration: underline; }
    .setup { background: #161b22; border: 1px solid #30363d; border-radius: 6px;
             padding: 1rem 1.25rem; margin-bottom: 1.5rem; }
    .setup p { margin: 0 0 0.4rem; color: #8b949e; font-size: 0.85rem; }
    pre { margin: 0 0 0.75rem; background: #0d1117; border: 1px solid #21262d;
          border-radius: 4px; padding: 0.6rem 1rem; overflow-x: auto;
          font-size: 0.85rem; line-height: 1.5; }
    pre:last-child { margin-bottom: 0; }
    .step { color: #8b949e; font-size: 0.8rem; margin-bottom: 0.25rem; }
    hr { border: none; border-top: 1px solid #21262d; margin: 1.5rem 0; }
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
    return HTMLResponse(
        _page(
            title="Repository",
            hint="Verfügbare Distributionen",
            rows_html=rows or '<tr><td colspan="2">Keine Distributionen konfiguriert.</td></tr>',
        )
    )


# ---------------------------------------------------------------------------
# /repo/{distro}  →  /repo/{distro}/
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}", include_in_schema=False)
def distro_redirect(distro: str):
    if distro not in _DISTROS:
        raise HTTPException(status_code=404, detail="Unbekannte Distribution")
    return RedirectResponse(url=f"/repo/{distro}/", status_code=301)


# ---------------------------------------------------------------------------
# /repo/debian/  –  Flaches Debian-Listing (vor dem generischen /{distro}/)
# ---------------------------------------------------------------------------
@router.get("/repo/debian/", response_class=HTMLResponse, include_in_schema=False)
def debian_listing(request: Request):
    d = _debian_repo_dir()
    base_url = str(request.base_url).rstrip("/")

    # Keyring-Datei suchen (neueste Version)
    keyring_deb = None
    if d.exists():
        candidates = sorted(d.glob("simpsons-keyring_*.deb"), key=lambda f: f.name, reverse=True)
        if candidates:
            keyring_deb = candidates[0].name

    dl_url = f"{base_url}/repo/debian/{keyring_deb or 'simpsons-keyring_1.0.0-1_all.deb'}"
    sources_url = f"{base_url}/repo/debian/"
    keyring_available = "✓ verfügbar" if keyring_deb else "⚠ noch nicht gebaut"

    setup_html = f"""<div class="setup">
  <h2>Einrichtung</h2>
  <p class="step">1 · CA-Zertifikat einmalig installieren (simpsons-keyring) {keyring_available}</p>
  <pre>curl -k {dl_url} -o /tmp/simpsons-keyring.deb
sudo dpkg -i /tmp/simpsons-keyring.deb</pre>
  <p class="step">2 · APT-Quelle einrichten</p>
  <pre>sudo tee /etc/apt/sources.list.d/simpsons.sources &lt;&lt;'EOF'
Types: deb
URIs: {sources_url}
Suites: ./
EOF</pre>
  <p class="step">3 · Pakete installieren</p>
  <pre>sudo apt update
sudo apt install &lt;paketname&gt;</pre>
</div>
<hr>"""

    if not d.exists():
        files_html = '<tr><td colspan="2">Repository-Verzeichnis noch nicht vorhanden.</td></tr>'
    else:
        files = sorted((f for f in d.iterdir() if f.is_file()), key=lambda f: f.name)
        files_html = (
            "\n".join(
                f'<tr><td><a href="/repo/debian/{f.name}">{f.name}</a></td>'
                f'<td class="size">{_fmt_size(f.stat().st_size)}</td></tr>'
                for f in files
            )
            or '<tr><td colspan="2">Keine Dateien vorhanden.</td></tr>'
        )

    back_html = '<p class="back"><a href="/repo/">← Zurück</a></p>'
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Repository · debian</title>
  <style>{_CSS}</style>
</head>
<body>
  {back_html}
  <h1>Repository · debian</h1>
  <p class="hint">APT-Repository – flaches Layout (Suites: ./)</p>
  {setup_html}
  <table>
    <thead><tr><th>Name</th><th>Größe</th></tr></thead>
    <tbody>
{files_html}
    </tbody>
  </table>
</body>
</html>"""
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# /repo/debian/{path:path}  –  Datei-Download
# Matcht auch ./Packages, ./InRelease usw. die APT bei Suites: ./ sendet
# ---------------------------------------------------------------------------
@router.get("/repo/debian/{path:path}", include_in_schema=False)
def debian_file(path: str):
    # APT schickt ./Packages → auf einfachen Dateinamen normalisieren
    clean = path.removeprefix("./").lstrip("/")
    if not clean or "/" in clean:
        raise HTTPException(status_code=400, detail="Ungültiger Pfad")
    d = _debian_repo_dir()
    fp = (d / clean).resolve()
    if not str(fp).startswith(str(d.resolve())):
        raise HTTPException(status_code=400, detail="Ungültiger Pfad")
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(str(fp))


# ---------------------------------------------------------------------------
# /repo/{distro}/  –  Architektur-Übersicht (nur für nicht-flache Distros)
# ---------------------------------------------------------------------------
@router.get("/repo/{distro}/", response_class=HTMLResponse, include_in_schema=False)
def distro_index(request: Request, distro: str):
    if distro not in _DISTROS or distro in _FLAT_DISTROS:
        raise HTTPException(status_code=404, detail="Unbekannte Distribution")

    base_url = str(request.base_url).rstrip("/")
    arches = _DISTROS[distro]
    rows = "\n".join(
        f'<tr><td><a href="/repo/{distro}/{arch}/">{arch}/</a></td><td class="size">—</td></tr>'
        for arch in arches
    )
    return HTMLResponse(
        _page(
            title=f"Repository · {distro}",
            hint=f"pacman.conf: <code>Server = {base_url}/repo/{distro}/$arch</code>",
            rows_html=rows,
            back="/repo/",
        )
    )


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
    return HTMLResponse(
        _page(
            title=f"Repository · {distro} · {arch}",
            hint=f"pacman.conf: <code>Server = {base_url}/repo/{distro}/$arch</code>",
            rows_html=rows or '<tr><td colspan="2">Keine Dateien vorhanden.</td></tr>',
            back=f"/repo/{distro}/",
        )
    )


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

"""astrapi_packages.utils.pkgbuild – generisches PKGBUILD-Parsing.

Konsolidiert den bisher zweimal fast identisch vorhandenen Code
(debian/ui/crud.py:_pkgbuild_info(), archlinux/ui/crud.py:
_version_from_pkgbuild_url()) zu einer Funktion, die fuer jeden OS-Typ
funktioniert -- beide Fach-Module nutzten schon einheitlich PKGBUILD-Syntax
("Bridge-Ansatz", siehe projects/packages/beschreibung.md).

Ersetzt zugleich die AUR-Batch-API als Versions-Check-Mechanismus (siehe
projects/packages/planung-datei-editor.md, Abschnitt "Virtuelles OS-Modul"):
bewusst langsamer bei vielen Paketen auf einmal, dafuer ohne jeden
OS-Sonderfall nutzbar.
"""

from __future__ import annotations

import re


def parse_deps(text: str) -> list[str]:
    """Liest depends/makedepends aus PKGBUILD-Inhalt, Versions-Constraints entfernt."""
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


def parse_version(text: str) -> str:
    """Liest pkgver(-pkgrel) aus PKGBUILD-Inhalt."""
    m_ver = re.search(r"^pkgver\s*=\s*(.+)", text, re.MULTILINE)
    if not m_ver:
        return ""
    m_rel = re.search(r"^pkgrel\s*=\s*(.+)", text, re.MULTILINE)
    ver = m_ver.group(1).strip().strip("'\"")
    rel = m_rel.group(1).strip().strip("'\"") if m_rel else ""
    return f"{ver}-{rel}" if rel else ver


def _raw_url(base_url: str, branch: str, subdir: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(base_url)
    path = p.path.strip("/")
    if p.netloc == "github.com":
        return f"https://raw.githubusercontent.com/{path}/{branch}/{subdir}/PKGBUILD"
    if "gitlab" in p.netloc:
        return f"{p.scheme}://{p.netloc}/{path}/-/raw/{branch}/{subdir}/PKGBUILD"
    return f"{p.scheme}://{p.netloc}/{path}/raw/branch/{branch}/{subdir}/PKGBUILD"


def read_remote_pkgbuild(source_url: str, subdir: str) -> tuple[str, list[str]]:
    """Liest Version + Depends aus einer PKGBUILD in einem Git-Repo (source_type='git').

    Probiert main/master-Branch, github/gitlab/gitea-URL-Formen (wie bisher).
    Gibt ("", []) zurueck wenn nichts erreichbar/parsebar ist.
    """
    import urllib.request

    base = source_url.rstrip("/").removesuffix(".git")
    for branch in ("main", "master"):
        url = _raw_url(base, branch, subdir)
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                text = r.read().decode("utf-8", errors="replace")
            return parse_version(text), parse_deps(text)
        except Exception:
            continue
    return "", []


def read_local_pkgbuild(owner_type: str, owner_id: str) -> tuple[str, list[str]]:
    """Liest Version + Depends aus einer DB-verwalteten PKGBUILD (source_type='db')."""
    from astrapi_packages.utils import file_store

    content = file_store.read(owner_type, owner_id, "PKGBUILD")
    if not content:
        return "", []
    return parse_version(content), parse_deps(content)

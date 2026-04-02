"""app/modules/pakete/ui.py – Flask-Blueprint für das Pakete-Modul."""

from pathlib import Path

from flask import render_template, request

from astrapi.core.ui.crud_blueprint import make_crud_blueprint
from astrapi.core.ui.schema_loader import load_schema
from .storage import store, KEY

_DIR    = Path(__file__).parent


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
        if re.match(r'^depends\s*=\s*\(', stripped):
            in_block = True
        if in_block:
            for d in re.findall(r"['\"]([^'\"]+)['\"]|(\b[A-Za-z0-9@_+.-]+\b)", stripped):
                val = d[0] or d[1]
                if val and val not in ('depends', '(', ')'):
                    deps.append(re.sub(r'[<>=].*', '', val))
            if ')' in stripped:
                in_block = False
    return list(dict.fromkeys(deps))  # dedupliziert, Reihenfolge erhalten


def _deps_from_aur(pkgname: str) -> list[str]:
    """Holt Runtime-Deps aus der AUR RPC API."""
    import re, json, urllib.request
    try:
        url = f"https://aur.archlinux.org/rpc/v5/info?arg[]={pkgname}"
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        if results:
            r0 = results[0]
            all_deps = r0.get("Depends", []) + r0.get("MakeDepends", [])
            return list(dict.fromkeys(re.sub(r'[<>=].*', '', d) for d in all_deps))
    except Exception:
        pass
    return []


def _classify_deps(deps: list[str], existing: set[str]) -> list[dict]:
    """Klassifiziert Abhängigkeiten: astrapi-packages | official | aur.

    Strategie: Batch-Abfrage gegen AUR-RPC – was dort gefunden wird ist AUR,
    alles andere kommt aus den Official Repos (oder existiert nicht).
    """
    import json, urllib.request
    from urllib.parse import urlencode

    unknown = [d for d in deps if d not in existing]
    in_aur: set[str] = set()

    if unknown:
        # AUR RPC erlaubt mehrere arg[]-Parameter in einem Request
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
_SCHEMA = load_schema(str(_DIR / "schema.yaml"))

# GitLab-Cache: direkt per importlib laden (app.modules.* Namespace umgehen)
import importlib.util as _ilu, sys as _sys

def _get_gitlab_cache():
    _key = "_pakete_gitlab_cache"
    if _key not in _sys.modules:
        _spec = _ilu.spec_from_file_location(_key, _DIR / "gitlab_cache.py")
        _mod  = _ilu.module_from_spec(_spec)
        _sys.modules[_key] = _mod
        _spec.loader.exec_module(_mod)
        _mod.start()
    return _sys.modules[_key]

_get_gitlab_cache()  # beim Modulstart anwerfen


bp = make_crud_blueprint(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    label="Paket",
    description_field="name",
    has_run_buttons=False,
    extra_page_actions_template=f"{KEY}/partials/page_actions.html",
)


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
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/list.html",
        extra_page_actions_template=f"{KEY}/partials/page_actions.html",
        running=running,
        has_run_buttons=False,
    )


@bp.route(f"/ui/{KEY}/status")
def status():
    return render_template("partials/list_wrapper_inner.html", **_ctx())


@bp.before_request
def _intercept():
    endpoint = request.endpoint or ""

    # GET /ui/pakete/create → kombiniertes Modal (leer)
    if endpoint == f"{KEY}_ui.create_modal":
        return render_template(
            f"{KEY}/partials/combined_edit_modal.html",
            item_id=None,
            item=None,
            schema=_SCHEMA["fields"],
        )

    # POST /ui/pakete/ → Anlegen
    if endpoint == f"{KEY}_ui.create_apply":
        source_url = request.form.get("source_url", "").strip()
        pkg_name   = request.form.get("pkg_name", "").strip()
        item_id    = pkg_name or source_url.rstrip("/").split("/")[-1].removesuffix(".git")

        if not item_id:
            return "Paketname fehlt", 400

        if store.get(item_id) is not None:
            import json as _json
            from flask import make_response
            resp = make_response("", 200)
            resp.headers["HX-Reswap"] = "none"
            resp.headers["HX-Trigger"]  = _json.dumps({
                "paketeModalError": f'"{item_id}" ist bereits vorhanden.'
            })
            return resp

        data = {
            "source_url":    source_url,
            "source_subdir": request.form.get("source_subdir", "").strip(),
            "aur_deps":      request.form.get("aur_deps", "").strip(),
            "pkg_type":      request.form.get("pkg_type", "package").strip() or "package",
            "enabled":       "enabled" in request.form,
        }
        store.create(item_id, data)

        from .dep_graph import autocreate_deps
        autocreate_deps(item_id, data, store)

        return render_template("partials/list_wrapper.html", **_ctx())

    # GET /ui/pakete/{id}/edit → kombiniertes Modal (befüllt)
    if endpoint == f"{KEY}_ui.edit_modal":
        item_id = request.view_args.get("item_id")
        item = store.get(item_id)
        if item is None:
            return "Nicht gefunden", 404
        return render_template(
            f"{KEY}/partials/combined_edit_modal.html",
            item_id=item_id,
            item=item,
            schema=_SCHEMA["fields"],
        )

    # POST /ui/pakete/{id}/update → Felder aktualisieren, dann Liste neu rendern
    if endpoint == f"{KEY}_ui.edit_apply":
        item_id = request.view_args.get("item_id")
        if store.get(item_id) is not None:
            data = {
                "source_url":    request.form.get("source_url", "").strip(),
                "source_subdir": request.form.get("source_subdir", "").strip(),
                "aur_deps":      request.form.get("aur_deps", "").strip(),
                "pkg_type":      request.form.get("pkg_type", "package").strip() or "package",
                "enabled":       "enabled" in request.form,
            }
            store.update(item_id, data)
            from .dep_graph import autocreate_deps
            autocreate_deps(item_id, data, store)
        return render_template("partials/list_wrapper.html", **_ctx())


# ── Modulspezifische Routen ───────────────────────────────────────────────────

def _parse_pkgbuild_deps(text: str) -> list[str]:
    """Liest depends + makedepends aus einem PKGBUILD-Text.

    Gibt bereinigte Paketnamen zurück (ohne Versionsconstraints wie >=1.0).
    """
    import re
    deps: list[str] = []
    for key in ("depends", "makedepends"):
        m = re.search(rf"^{key}\s*=\s*\((.*?)\)", text, re.MULTILINE | re.DOTALL)
        if not m:
            continue
        for token in re.findall(r"'([^']+)'|\"([^\"]+)\"|(\S+)", m.group(1)):
            name = (token[0] or token[1] or token[2]).strip()
            name = re.sub(r"[><=!].*", "", name).strip()  # Versionsconstraint entfernen
            if name:
                deps.append(name)
    # Deduplizieren, Reihenfolge erhalten
    seen: set[str] = set()
    return [d for d in deps if not (d in seen or seen.add(d))]  # type: ignore[func-returns-value]


def _version_from_pkgbuild_url(source_url: str, source_subdir: str) -> tuple[str, list[str]]:
    """Liest pkgver-pkgrel und depends/makedepends direkt aus dem PKGBUILD auf GitLab.

    Konstruiert die Raw-URL aus source_url + source_subdir und probiert
    main- und master-Branch. Gibt (version, deps) zurück; bei Fehler ('', []).
    """
    import re, urllib.request
    base = source_url.rstrip("/").removesuffix(".git")
    for branch in ("main", "master"):
        url = f"{base}/-/raw/{branch}/{source_subdir}/PKGBUILD"
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
    import json, urllib.request, re
    try:
        url = f"https://aur.archlinux.org/rpc/v5/search?arg={term}&by=name-desc"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        return [
            {
                "name":    p["Name"],
                "pkgver":  p.get("Version", ""),
                "pkgdesc": p.get("Description", "") or "",
                "git_url": f"https://aur.archlinux.org/{p['Name']}.git",
                "source":  "aur",
            }
            for p in data.get("results", [])[:12]
        ]
    except Exception:
        return []


@bp.route(f"/ui/{KEY}/search")
def search_packages():
    import threading
    gitlab_cache = _get_gitlab_cache()
    term = request.args.get("q", "").strip()
    if len(term) < 2:
        return ""
    # Cache leer (z.B. Gruppe erst nach Start konfiguriert) → Refresh anstoßen
    if not gitlab_cache.get_all():
        threading.Thread(target=gitlab_cache.refresh, daemon=True).start()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_gl  = ex.submit(gitlab_cache.search, term)
        f_aur = ex.submit(_search_aur, term)
        gl_results  = f_gl.result()
        aur_results = f_aur.result()
    return render_template(
        f"{KEY}/partials/search_results.html",
        gitlab_results=gl_results,
        aur_results=aur_results,
        term=term,
        cache_empty=not gitlab_cache.get_all(),
    )


@bp.route(f"/ui/{KEY}/aur-deps")
def aur_deps_for_pkg():
    """Gibt die AUR-Abhängigkeiten eines Pakets als kommaseparierten String zurück."""
    pkgname = request.args.get("pkg", "").strip()
    if not pkgname:
        return ""
    deps = _deps_from_aur(pkgname)
    if not deps:
        return ""
    existing = set(store.list().keys())
    classified = _classify_deps(deps, existing)
    aur_only = [d["name"] for d in classified if d["status"] == "aur"]
    return ", ".join(aur_only)


@bp.route(f"/ui/{KEY}/deps", methods=["POST"])
def deps_preview():
    """Gibt Runtime-Abhängigkeiten als HTML-Partial zurück."""
    source_url = request.form.get("source_url", "").strip()
    pkgbuild   = request.form.get("pkgbuild_content", "").strip()

    if source_url:
        pkgname = source_url.rstrip("/").split("/")[-1].removesuffix(".git")
        deps = _deps_from_aur(pkgname)
    elif pkgbuild:
        deps = _deps_from_pkgbuild(pkgbuild)
    else:
        return ""

    existing = set(store.list().keys())
    classified = _classify_deps(deps, existing)
    return render_template(
        f"{KEY}/partials/deps_preview.html",
        deps=classified,
    )

@bp.route(f"/ui/{KEY}/<item_id>/build", methods=["POST"])
def build_item(item_id: str):
    if store.get(item_id) is None:
        return "Nicht gefunden", 404
    store.update(item_id, {"last_status": "pending"})
    from .jobs import build_package_with_deps_async
    build_package_with_deps_async(item_id)
    ctx = _ctx()
    # Polling erzwingen: unabhängig vom running-Dict direkt einfügen
    ctx["running"] = ctx["running"] or {f"{KEY}:{item_id}": "pending"}
    return render_template("partials/list_wrapper_inner.html", **ctx)


@bp.route(f"/ui/{KEY}/<item_id>/log")
def log_item(item_id: str):
    item = store.get(item_id) or {}
    return render_template(
        f"{KEY}/partials/log_modal.html",
        item_id=item_id,
        item_data=item,
    )


@bp.route(f"/ui/{KEY}/exists")
def pkg_exists():
    item_id = request.args.get("id", "").strip()
    if item_id and store.get(item_id) is not None:
        return (f'<div id="modal-error-container" style="padding:8px 12px;border-radius:6px;'
                f'background:var(--error-dim,#3a0000);color:var(--error,#ff6b6b);font-size:13px;">'
                f'"{item_id}" ist bereits vorhanden.</div>')
    return '<div id="modal-error-container"></div>'


@bp.route(f"/ui/{KEY}/check-updates", methods=["POST"])
def check_updates():
    """Prüft für alle Pakete ob eine neue Version verfügbar ist."""
    import json, urllib.request
    from urllib.parse import quote

    # GitLab-Cache vor der Prüfung aktualisieren
    try:
        _get_gitlab_cache().refresh()
    except Exception:
        pass

    all_items = store.list()
    if not all_items:
        return render_template("partials/list_wrapper_inner.html", **_ctx())

    # ── Einmalige Bereinigung: upstream_version bei ungebauten Paketen löschen ─
    for k, v in all_items.items():
        if v.get("last_status") != "ok" and v.get("upstream_version"):
            store.update(k, {"upstream_version": ""})

    # ── Nur bereits gebaute Pakete berücksichtigen ────────────────────────────
    all_ids = [
        k for k, v in all_items.items() if v.get("last_status") == "ok"
    ]
    if not all_ids:
        return render_template("partials/list_wrapper_inner.html", **_ctx())

    # ── AUR: alle item_ids als Paketnamen probieren (Batch) ──────────────────
    qs = "&".join(f"arg[]={quote(i)}" for i in all_ids)
    aur_versions: dict[str, str] = {}  # Name → Version
    try:
        with urllib.request.urlopen(
            f"https://aur.archlinux.org/rpc/v5/info?{qs}", timeout=10
        ) as r:
            data = json.loads(r.read())
        for result in data.get("results", []):
            aur_versions[result["Name"]] = result.get("Version", "")
    except Exception as e:
        log.warning("check_updates: AUR-Abfrage fehlgeschlagen: %s", e)

    # ── GitLab: packages.json aus Cache ───────────────────────────────────────
    gitlab_cache = _get_gitlab_cache()
    gl_entries = {e.get("name"): e for e in gitlab_cache.get_all() if e.get("name")}

    # ── Ergebnisse schreiben ──────────────────────────────────────────────────
    for item_id in all_ids:
        if item_id in aur_versions:
            store.update(item_id, {"upstream_version": aur_versions[item_id]})
        else:
            # GitLab: PKGBUILD direkt lesen, packages.json als Fallback
            item        = all_items[item_id]
            source_url  = item.get("source_url", "")
            source_sub  = item.get("source_subdir", "")
            upstream    = ""
            if "gitlab" in source_url and source_sub:
                upstream, _ = _version_from_pkgbuild_url(source_url, source_sub)
            if not upstream and item_id in gl_entries:
                entry    = gl_entries[item_id]
                ver      = entry.get("pkgver") or entry.get("version") or ""
                rel      = entry.get("pkgrel", "")
                upstream = f"{ver}-{rel}" if rel else ver
            if upstream:
                store.update(item_id, {"upstream_version": upstream})

    return render_template("partials/list_wrapper_inner.html", **_ctx())

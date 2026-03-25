"""
core/ui/page_factory.py  –  Automatische Page- und Content-Routen

URL-Schema:
  GET /<key>              → App-Shell (index.html), lädt /ui/<key>/content per HTMX
  GET /ui/<key>/content   → Inhalt-Partial (Nav-Klick + Reload + Refresh)

/api/... bleibt ausschließlich FastAPI (JSON).
/ui/...  ist ausschließlich Flask (HTML-Partials, Modals).
/<key>   ist die sichtbare Browser-URL.
"""

from flask import Flask, render_template


def _label(key: str, nav_items: list[dict]) -> str:
    return next(
        (it["label"] for it in nav_items if not it.get("separator") and it["key"] == key),
        key.replace("_", " ").title(),
    )


def make_shell(resource_key: str, nav_items: list[dict]) -> callable:
    """App-Shell unter /<key> — komplette Seite, lädt Content per HTMX nach."""
    title       = _label(resource_key, nav_items)
    content_url = f"/ui/{resource_key}/content"

    def shell():
        return render_template(
            "index.html",
            active_tab=resource_key,
            initial_content_url=content_url,
            title=title,
        )

    shell.__name__ = f"shell_{resource_key}"
    return shell


def make_content(resource_key: str) -> callable:
    """Inhalt-Partial unter /ui/<key>/content — für Nav-Klick, Reload und Refresh."""
    list_partial = f"partials/lists/{resource_key}.html"

    def content():
        return render_template(list_partial)

    content.__name__ = f"content_{resource_key}"
    return content


def register_pages(
    app: Flask,
    nav_items: list[dict],
    shell_only_keys: set[str] | None = None,
) -> None:
    """Registriert Shell- und Content-Route für jeden Nav-Eintrag.

    shell_only_keys: Content kommt vom Modul-Blueprint selbst.
    """
    shell_only = shell_only_keys or set()

    for item in nav_items:
        if item.get("separator"):
            continue

        key = item["key"]

        # /<key>              → App-Shell
        app.add_url_rule(f"/{key}", endpoint=f"shell_{key}", view_func=make_shell(key, nav_items))

        if key not in shell_only:
            # /ui/<key>/content → Inhalt-Partial
            app.add_url_rule(f"/ui/{key}/content", endpoint=f"content_{key}", view_func=make_content(key))

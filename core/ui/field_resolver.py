"""Helpers for resolving dynamic field options before template rendering."""


def resolve_options_endpoint(fields: list) -> list:
    """Replaces options_endpoint with actual options fetched from the engine."""
    _cache = {}
    result = []
    for field in fields:
        endpoint = field.get("options_endpoint")
        if endpoint:
            if endpoint not in _cache:
                _cache[endpoint] = _fetch_options(endpoint)
            field = dict(field)
            field["options"] = _cache[endpoint]
            del field["options_endpoint"]
        result.append(field)
    return result


def _fetch_options(endpoint: str) -> list:
    if endpoint == "/api/remotes/for-select":
        from app.modules.remotes.engine import get_all_remotes_for_select
        return [{"value": r["id"], "label": r["label"]} for r in get_all_remotes_for_select()]
    return []

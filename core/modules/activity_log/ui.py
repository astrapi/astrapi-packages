# core/modules/activity_log/ui.py
from flask import Blueprint, render_template

from .engine import KEY, list_activity, enrich, registered_modules

bp = Blueprint(f"{KEY}_ui", __name__)


@bp.route("/ui/activity_log/clear-confirm")
def clear_confirm():
    return render_template(
        "partials/confirm_modal.html",
        description="Alle Activity-Log-Einträge",
        verb="löschen",
        confirm_url="/api/activity_log/clear",
        method="delete",
        container_id="tab-activity_log",
        loading_id="activity_log-loading",
    )


@bp.route("/ui/activity_log/content")
def content():
    entries = enrich(list_activity(limit=200))
    return render_template(
        "activity_log/partials/list.html",
        entries=entries,
        modules=registered_modules(),
    )

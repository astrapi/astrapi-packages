"""core/modules/sysinfo/ui.py – Flask-Blueprint für Sysinfo UI-Routen."""
from flask import Blueprint, render_template
from .engine import collect

KEY = "sysinfo"
bp  = Blueprint(f"{KEY}_ui", __name__)


@bp.route(f"/ui/{KEY}/content")
def sysinfo_content():
    return render_template(f"{KEY}/partials/tab.html", info=collect())


@bp.route(f"/ui/{KEY}/metrics")
def sysinfo_metrics():
    return render_template(f"{KEY}/partials/metrics.html", info=collect())

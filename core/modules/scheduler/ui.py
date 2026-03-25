"""core/modules/scheduler/ui.py – Flask-Blueprint für den Multi-Job Scheduler."""
import uuid

from flask import Blueprint, render_template, request

KEY   = "scheduler"
_C_ID = f"tab-{KEY}"
_L_ID = f"{KEY}-loading"

bp = Blueprint(f"{KEY}_ui", __name__)


def _list_ctx() -> dict:
    from core.modules.scheduler.engine import list_jobs, get_registered_actions
    return {
        "jobs":         list_jobs(),
        "actions":      get_registered_actions(),
        "key":          KEY,
        "container_id": _C_ID,
        "loading_id":   _L_ID,
    }


# ── Liste ──────────────────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/content")
def scheduler_content():
    return render_template(f"{KEY}/partials/tab.html", **_list_ctx())


# ── Modals ─────────────────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/job/new")
def scheduler_job_new():
    from core.modules.scheduler.engine import get_registered_actions
    return render_template(
        f"{KEY}/partials/job_modal.html",
        job=None,
        actions=get_registered_actions(),
        error=None,
        container_id=request.args.get("container_id", _C_ID),
        loading_id=request.args.get("loading_id", _L_ID),
    )


@bp.route(f"/ui/{KEY}/job/<job_id>/edit")
def scheduler_job_edit(job_id: str):
    from core.modules.scheduler.engine import get_job, get_registered_actions
    job = get_job(job_id)
    if job is None:
        return "", 404
    return render_template(
        f"{KEY}/partials/job_modal.html",
        job=job,
        actions=get_registered_actions(),
        error=None,
        container_id=request.args.get("container_id", _C_ID),
        loading_id=request.args.get("loading_id", _L_ID),
    )


@bp.route(f"/ui/{KEY}/job/<job_id>/delete")
def scheduler_job_delete_modal(job_id: str):
    from core.modules.scheduler.engine import get_job
    job = get_job(job_id)
    return render_template(
        "partials/confirm_modal.html",
        description=job["label"] if job else job_id,
        verb="löschen",
        confirm_url=f"/api/{KEY}/{job_id}",
        method="delete",
        reload_url=f"/ui/{KEY}/content",
        container_id=request.args.get("container_id", _C_ID),
        loading_id=request.args.get("loading_id", _L_ID),
    )


@bp.route(f"/ui/{KEY}/job/<job_id>/toggle")
def scheduler_job_toggle_modal(job_id: str):
    from core.modules.scheduler.engine import get_job
    job = get_job(job_id) or {}
    enabled = request.args.get("enabled", "True")
    verb = "deaktivieren" if enabled == "True" else "aktivieren"
    return render_template(
        "partials/confirm_modal.html",
        description=job.get("label", job_id),
        verb=verb,
        confirm_url=f"/api/{KEY}/{job_id}/toggle",
        method="patch",
        reload_url=f"/ui/{KEY}/content",
        container_id=request.args.get("container_id", _C_ID),
        loading_id=request.args.get("loading_id", _L_ID),
    )


# ── Apply-Routen (Form-Submit aus Modal) ───────────────────────────────────────

@bp.route(f"/ui/{KEY}/job", methods=["POST"])
def scheduler_job_create():
    from core.modules.scheduler.engine import create_job, get_registered_actions

    label         = request.form.get("label", "").strip()
    cron          = request.form.get("cron", "").strip()
    enabled       = "1" in request.form.getlist("enabled")
    steps         = request.form.getlist("steps")
    notify_start  = "1" in request.form.getlist("notify_start")
    notify_end    = "1" in request.form.getlist("notify_end")

    if not label or not cron:
        return render_template(
            f"{KEY}/partials/job_modal.html",
            job={"id": None, "label": label,
                 "cron": cron, "enabled": enabled, "steps": steps,
                 "notify_start": notify_start, "notify_end": notify_end},
            actions=get_registered_actions(),
            error="Name und Cron-Ausdruck sind Pflichtfelder.",
            container_id=_C_ID, loading_id=_L_ID,
        ), 422

    job_id = uuid.uuid4().hex[:12]
    create_job(job_id, label, cron, enabled, steps,
               notify_start=notify_start, notify_end=notify_end)
    return render_template(f"{KEY}/partials/tab.html", **_list_ctx())


@bp.route(f"/ui/{KEY}/job/<job_id>/update", methods=["POST"])
def scheduler_job_save(job_id: str):
    from core.modules.scheduler.engine import update_job, get_registered_actions

    label         = request.form.get("label", "").strip()
    cron          = request.form.get("cron", "").strip()
    enabled       = "1" in request.form.getlist("enabled")
    steps         = request.form.getlist("steps")
    notify_start  = "1" in request.form.getlist("notify_start")
    notify_end    = "1" in request.form.getlist("notify_end")

    if not label or not cron:
        from core.modules.scheduler.engine import get_job
        job = get_job(job_id) or {"id": job_id}
        job.update({"label": label, "cron": cron, "enabled": enabled, "steps": steps,
                    "notify_start": notify_start, "notify_end": notify_end})
        return render_template(
            f"{KEY}/partials/job_modal.html",
            job=job,
            actions=get_registered_actions(),
            error="Label und Cron-Ausdruck sind Pflichtfelder.",
            container_id=_C_ID, loading_id=_L_ID,
        ), 422

    update_job(job_id, label, cron, enabled, steps,
               notify_start=notify_start, notify_end=notify_end)
    return render_template(f"{KEY}/partials/tab.html", **_list_ctx())


# ── Trigger ────────────────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/job/<job_id>/trigger", methods=["POST"])
def scheduler_job_trigger(job_id: str):
    from core.modules.scheduler.engine import trigger_job
    trigger_job(job_id)
    return render_template(f"{KEY}/partials/list.html", **_list_ctx())

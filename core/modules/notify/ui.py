"""core/modules/notify/ui.py – Flask-Blueprint für Benachrichtigungs-Kanäle und -Jobs."""

import uuid

from flask import Blueprint, render_template, request

from .engine import (
    KEY,
    list_channels, get_channel, create_channel, update_channel,
    list_jobs, get_job, create_job, update_job,
    get_registered_backends, get_registered_sources,
    test_channel as _test_channel, test_job as _test_job,
)
from .schema import ALL_EVENTS

bp = Blueprint(f"{KEY}_ui", __name__)

_CONTAINER_ID = f"tab-{KEY}"
_LOADING_ID   = f"{KEY}-loading"

_BUILTIN_BACKENDS = [
    ("ntfy",  "ntfy",  "Push-Benachrichtigungen via ntfy.sh oder eigenem Server"),
    ("email", "E-Mail", "Benachrichtigungen per SMTP (Gmail, Outlook, eigener Server …)"),
]


# ── Kontext-Helfer ────────────────────────────────────────────────────────────

def _ctx(**extra) -> dict:
    return dict(
        key=KEY,
        label="Benachrichtigungen",
        channels=list_channels(),
        jobs=list_jobs(),
        container_id=_CONTAINER_ID,
        loading_id=_LOADING_ID,
        **extra,
    )


def _parse_channel_form() -> dict:
    """Liest und normalisiert alle Kanalformularfelder (nur Backend-Konfiguration)."""
    enabled = "1" in request.form.getlist("enabled")
    return {
        "label":               request.form.get("label", "").strip(),
        "backend":             request.form.get("backend", "ntfy"),
        "enabled":             enabled,
        # ntfy
        "ntfy_url":            request.form.get("ntfy_url", "https://ntfy.sh").strip(),
        "ntfy_topic":          request.form.get("ntfy_topic", "").strip(),
        "ntfy_token":          request.form.get("ntfy_token", "").strip(),
        "ntfy_verify_ssl":     "ntfy_verify_ssl" in request.form,
        # E-Mail
        "mail_smtp_host":      request.form.get("mail_smtp_host", "").strip(),
        "mail_smtp_port":      int(request.form.get("mail_smtp_port") or 587),
        "mail_smtp_user":      request.form.get("mail_smtp_user", "").strip(),
        "mail_smtp_password":  request.form.get("mail_smtp_password", "").strip(),
        "mail_smtp_tls":       "mail_smtp_tls" in request.form,
        "mail_from":           request.form.get("mail_from", "").strip(),
        "mail_to":             request.form.get("mail_to", "").strip(),
        "mail_subject_prefix": request.form.get("mail_subject_prefix", "[Notify]").strip(),
    }


def _parse_job_form() -> dict:
    """Liest und normalisiert alle Job-Formularfelder."""
    enabled = "1" in request.form.getlist("enabled")
    return {
        "label":      request.form.get("label", "").strip(),
        "channel_id": request.form.get("channel_id", "").strip(),
        "enabled":    enabled,
        "events":     request.form.getlist("events"),
        "sources":    request.form.getlist("sources"),
    }


def _split_sources() -> tuple[dict, dict]:
    """Trennt registrierte Quellen in Modul-Quellen und Scheduler-Jobs.

    Returns:
        (module_sources, scheduler_sources) – je {key: label}.
    """
    all_sources = get_registered_sources()
    try:
        from astrapi.core.modules.scheduler.engine import list_jobs as _sched_list
        sched_ids = {j["id"] for j in _sched_list()}
    except Exception:
        sched_ids = set()
    module_sources    = {k: v for k, v in all_sources.items() if k not in sched_ids}
    scheduler_sources = {k: v for k, v in all_sources.items() if k in sched_ids}
    return module_sources, scheduler_sources


# ── Gemeinsame Listen-View ────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/content")
def content():
    return render_template(f"{KEY}/partials/list.html", **_ctx())


# ── Kanal-Modale ──────────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/backend-select")
def backend_select_modal():
    return render_template(
        f"{KEY}/partials/backend_select_modal.html",
        builtin_backends=_BUILTIN_BACKENDS,
        custom_backends=get_registered_backends(),
    )


@bp.route(f"/ui/{KEY}/create/<backend>")
def create_modal(backend: str):
    return render_template(
        f"{KEY}/partials/channel_modal.html",
        channel=None,
        channel_id=None,
        selected_backend=backend,
        title="Neuer Benachrichtigungskanal",
        submit_url=f"/ui/{KEY}/",
    )


@bp.route(f"/ui/{KEY}/<channel_id>/edit")
def edit_modal(channel_id: str):
    channel = get_channel(channel_id)
    if channel is None:
        return "Kanal nicht gefunden", 404
    return render_template(
        f"{KEY}/partials/channel_modal.html",
        channel=channel,
        channel_id=channel_id,
        selected_backend=channel.get("backend", "ntfy"),
        title=f"Kanal bearbeiten ({channel.get('backend', 'ntfy')})",
        submit_url=f"/ui/{KEY}/{channel_id}/update",
    )


@bp.route(f"/ui/{KEY}/<channel_id>/delete")
def delete_modal(channel_id: str):
    channel = get_channel(channel_id) or {}
    return render_template(
        "partials/confirm_modal.html",
        description=channel.get("label", channel_id),
        verb="löschen",
        confirm_url=f"/api/{KEY}/{channel_id}",
        method="delete",
        reload_url=f"/ui/{KEY}/content",
        container_id=_CONTAINER_ID,
        loading_id=_LOADING_ID,
    )


@bp.route(f"/ui/{KEY}/<channel_id>/toggle")
def toggle_modal(channel_id: str):
    channel = get_channel(channel_id) or {}
    enabled = request.args.get("enabled", "True")
    verb    = "deaktivieren" if enabled == "True" else "aktivieren"
    return render_template(
        "partials/confirm_modal.html",
        description=channel.get("label", channel_id),
        verb=verb,
        confirm_url=f"/api/{KEY}/{channel_id}/toggle",
        method="patch",
        reload_url=f"/ui/{KEY}/content",
        container_id=_CONTAINER_ID,
        loading_id=_LOADING_ID,
    )


# ── Kanal CRUD-Aktionen ───────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/", methods=["POST"])
def create_apply():
    channel_id = f"ch-{uuid.uuid4().hex[:8]}"
    data = _parse_channel_form()
    try:
        create_channel(channel_id, data)
    except KeyError:
        return "ID bereits vergeben", 409
    return render_template(f"{KEY}/partials/list.html", **_ctx())


@bp.route(f"/ui/{KEY}/<channel_id>/update", methods=["POST"])
def edit_apply(channel_id: str):
    data = _parse_channel_form()
    try:
        update_channel(channel_id, data)
    except KeyError:
        return "Kanal nicht gefunden", 404
    return render_template(f"{KEY}/partials/list.html", **_ctx())


# ── Kanal-Test ────────────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/<channel_id>/test", methods=["POST"])
def test_channel_view(channel_id: str):
    ok, msg = _test_channel(channel_id)
    return _test_badge(ok, msg)


# ── Job-Modale ────────────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/jobs/create")
def create_job_modal():
    module_sources, scheduler_sources = _split_sources()
    return render_template(
        f"{KEY}/partials/job_modal.html",
        job=None,
        job_id=None,
        title="Neuer Notify-Job",
        submit_url=f"/ui/{KEY}/jobs/",
        all_events=ALL_EVENTS,
        all_sources=module_sources,
        scheduler_sources=scheduler_sources,
        all_channels=list_channels(),
    )


@bp.route(f"/ui/{KEY}/jobs/<job_id>/edit")
def edit_job_modal(job_id: str):
    job = get_job(job_id)
    if job is None:
        return "Job nicht gefunden", 404
    module_sources, scheduler_sources = _split_sources()
    return render_template(
        f"{KEY}/partials/job_modal.html",
        job=job,
        job_id=job_id,
        title="Job bearbeiten",
        submit_url=f"/ui/{KEY}/jobs/{job_id}/update",
        all_events=ALL_EVENTS,
        all_sources=module_sources,
        scheduler_sources=scheduler_sources,
        all_channels=list_channels(),
    )


@bp.route(f"/ui/{KEY}/jobs/<job_id>/delete")
def delete_job_modal(job_id: str):
    job = get_job(job_id) or {}
    return render_template(
        "partials/confirm_modal.html",
        description=job.get("label", job_id),
        verb="löschen",
        confirm_url=f"/api/{KEY}/jobs/{job_id}",
        method="delete",
        reload_url=f"/ui/{KEY}/content",
        container_id=_CONTAINER_ID,
        loading_id=_LOADING_ID,
    )


@bp.route(f"/ui/{KEY}/jobs/<job_id>/toggle")
def toggle_job_modal(job_id: str):
    job     = get_job(job_id) or {}
    enabled = request.args.get("enabled", "True")
    verb    = "deaktivieren" if enabled == "True" else "aktivieren"
    return render_template(
        "partials/confirm_modal.html",
        description=job.get("label", job_id),
        verb=verb,
        confirm_url=f"/api/{KEY}/jobs/{job_id}/toggle",
        method="patch",
        reload_url=f"/ui/{KEY}/content",
        container_id=_CONTAINER_ID,
        loading_id=_LOADING_ID,
    )


# ── Job CRUD-Aktionen ─────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/jobs/", methods=["POST"])
def create_job_apply():
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    data   = _parse_job_form()
    try:
        create_job(job_id, data)
    except KeyError:
        return "ID bereits vergeben", 409
    return render_template(f"{KEY}/partials/list.html", **_ctx())


@bp.route(f"/ui/{KEY}/jobs/<job_id>/update", methods=["POST"])
def edit_job_apply(job_id: str):
    data = _parse_job_form()
    try:
        update_job(job_id, data)
    except KeyError:
        return "Job nicht gefunden", 404
    return render_template(f"{KEY}/partials/list.html", **_ctx())


# ── Job-Test ──────────────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/jobs/<job_id>/test", methods=["POST"])
def test_job_view(job_id: str):
    ok, msg = _test_job(job_id)
    return _test_badge(ok, msg)


def _test_badge(ok: bool, msg: str) -> str:
    return render_template(f"{KEY}/partials/test_badge.html", ok=ok, msg=msg)

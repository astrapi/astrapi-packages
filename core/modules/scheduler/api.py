# core/modules/scheduler/api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class JobIn(BaseModel):
    label:        str
    cron:         str
    enabled:      bool = True
    steps:        list[str] = []
    notify_start: bool = True
    notify_end:   bool = True


@router.get("/", summary="List all jobs")
def list_jobs():
    from astrapi.core.modules.scheduler.engine import list_jobs as _list
    return {"jobs": _list()}


@router.get("/actions", summary="List registered actions")
def list_actions():
    from astrapi.core.modules.scheduler.engine import get_registered_actions
    return {"actions": get_registered_actions()}


@router.get("/{job_id}", summary="Get job")
def get_job(job_id: str):
    from astrapi.core.modules.scheduler.engine import get_job as _get
    job = _get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' nicht gefunden")
    return job


@router.post("/{job_id}", summary="Create job", status_code=201)
def create_job(job_id: str, data: JobIn):
    from astrapi.core.modules.scheduler.engine import create_job as _create
    try:
        return _create(job_id, data.label, data.cron, data.enabled, data.steps,
                       notify_start=data.notify_start, notify_end=data.notify_end)
    except KeyError as e:
        raise HTTPException(409, str(e))


@router.put("/{job_id}", summary="Update job")
def update_job(job_id: str, data: JobIn):
    from astrapi.core.modules.scheduler.engine import update_job as _update, get_job as _get
    if _get(job_id) is None:
        raise HTTPException(404, f"Job '{job_id}' nicht gefunden")
    return _update(job_id, data.label, data.cron, data.enabled, data.steps,
                   notify_start=data.notify_start, notify_end=data.notify_end)


@router.delete("/{job_id}", summary="Delete job", status_code=204)
def delete_job(job_id: str):
    from astrapi.core.modules.scheduler.engine import delete_job as _delete, get_job as _get
    if _get(job_id) is None:
        raise HTTPException(404, f"Job '{job_id}' nicht gefunden")
    _delete(job_id)


@router.post("/{job_id}/trigger", summary="Trigger job now")
def trigger_job(job_id: str):
    from astrapi.core.modules.scheduler.engine import trigger_job as _trigger, get_job as _get
    if _get(job_id) is None:
        raise HTTPException(404, f"Job '{job_id}' nicht gefunden")
    _trigger(job_id)
    return {"ok": True}


@router.patch("/{job_id}/toggle", summary="Toggle job enabled")
def toggle_job(job_id: str):
    from astrapi.core.modules.scheduler.engine import toggle_job as _toggle, get_job as _get
    if _get(job_id) is None:
        raise HTTPException(404, f"Job '{job_id}' nicht gefunden")
    _toggle(job_id)
    return _get(job_id)

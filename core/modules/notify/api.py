# core/modules/notify/api.py
"""FastAPI-Router für /api/notify/ – Kanal- und Job-CRUD + Test-Endpunkte."""

from fastapi import APIRouter, HTTPException

from .engine import (
    KEY,
    list_channels, get_channel, create_channel, update_channel, toggle_channel, delete_channel,
    list_jobs, get_job, create_job, update_job, toggle_job, delete_job,
    test_channel, test_job,
)
from .schema import ChannelIn, JobIn

router = APIRouter()


# ── Kanäle ────────────────────────────────────────────────────────────────────

@router.get("/", summary="Kanäle auflisten")
def list_channels_ep():
    items = list_channels()
    return {"channels": items, "total": len(items)}


@router.get("/{channel_id}", summary="Kanal abrufen")
def get_channel_ep(channel_id: str):
    item = get_channel(channel_id)
    if item is None:
        raise HTTPException(404, f"Kanal '{channel_id}' nicht gefunden")
    return item


@router.post("/", summary="Kanal erstellen", status_code=201)
def create_channel_ep(channel_id: str, item: ChannelIn):
    try:
        return {"created": channel_id, "channel": create_channel(channel_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(409, str(e))


@router.put("/{channel_id}", summary="Kanal aktualisieren")
def update_channel_ep(channel_id: str, item: ChannelIn):
    try:
        return {"updated": channel_id, "channel": update_channel(channel_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.patch("/{channel_id}/toggle", summary="Kanal aktivieren/deaktivieren")
def toggle_channel_ep(channel_id: str):
    try:
        return {"channel_id": channel_id, "enabled": toggle_channel(channel_id)}
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.delete("/{channel_id}", summary="Kanal löschen", status_code=204)
def delete_channel_ep(channel_id: str):
    try:
        delete_channel(channel_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/{channel_id}/test", summary="Testbenachrichtigung über Kanal senden")
def test_channel_ep(channel_id: str):
    ok, msg = test_channel(channel_id)
    return {"ok": ok, "message": msg}


# ── Notify-Jobs ───────────────────────────────────────────────────────────────

@router.get("/jobs/", summary="Jobs auflisten")
def list_jobs_ep():
    items = list_jobs()
    return {"jobs": items, "total": len(items)}


@router.get("/jobs/{job_id}", summary="Job abrufen")
def get_job_ep(job_id: str):
    item = get_job(job_id)
    if item is None:
        raise HTTPException(404, f"Job '{job_id}' nicht gefunden")
    return item


@router.post("/jobs/", summary="Job erstellen", status_code=201)
def create_job_ep(job_id: str, item: JobIn):
    try:
        return {"created": job_id, "job": create_job(job_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(409, str(e))


@router.put("/jobs/{job_id}", summary="Job aktualisieren")
def update_job_ep(job_id: str, item: JobIn):
    try:
        return {"updated": job_id, "job": update_job(job_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.patch("/jobs/{job_id}/toggle", summary="Job aktivieren/deaktivieren")
def toggle_job_ep(job_id: str):
    try:
        return {"job_id": job_id, "enabled": toggle_job(job_id)}
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.delete("/jobs/{job_id}", summary="Job löschen", status_code=204)
def delete_job_ep(job_id: str):
    try:
        delete_job(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/jobs/{job_id}/test", summary="Testbenachrichtigung über Job senden")
def test_job_ep(job_id: str):
    ok, msg = test_job(job_id)
    return {"ok": ok, "message": msg}

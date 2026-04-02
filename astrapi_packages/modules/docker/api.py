"""app/modules/docker/api.py – FastAPI-Router für das Docker-Modul."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .images import IMAGES
from .storage import store

router = APIRouter()


@router.get("/", summary="List Docker Images")
def list_images():
    items = {
        img_id: {"tag": cfg["tag"], **(store.get(img_id) or {})}
        for img_id, cfg in IMAGES.items()
    }
    return {"docker": items, "total": len(items)}


@router.post("/{item_id}/build", summary="Image bauen")
def build_item(item_id: str):
    if item_id not in IMAGES:
        raise HTTPException(404, detail="Nicht gefunden")
    from .jobs import build_image_async
    build_image_async(item_id)
    return JSONResponse({"status": "building", "item_id": item_id}, status_code=202)



@router.get("/{item_id}/log", summary="Build-Log abrufen")
def get_log(item_id: str):
    if item_id not in IMAGES:
        raise HTTPException(404, detail="Nicht gefunden")
    state = store.get(item_id) or {}
    return {"item_id": item_id, "log": state.get("last_log") or ""}

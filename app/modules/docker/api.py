"""app/modules/docker/api.py – FastAPI-Router für das Docker-Modul."""

from typing import Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.ui.crud_router import make_crud_router
from .storage import store, KEY


class ItemIn(BaseModel):
    name:       Optional[str]       = ""
    image:      Optional[str]       = ""
    tag:        Optional[str]       = "latest"
    context:    Optional[str]       = ""
    build_args: Optional[list[str]] = []
    enabled:    bool                = True


router = make_crud_router(store, KEY, ItemIn)


@router.post("/{item_id}/build")
def build_item(item_id: str):
    """Startet den Docker-Build asynchron."""
    if store.get(item_id) is None:
        raise HTTPException(404, detail="Nicht gefunden")
    from .jobs import build_image_async
    build_image_async(item_id)
    return JSONResponse({"status": "building", "item_id": item_id}, status_code=202)


@router.post("/{item_id}/update")
def update_item(item_id: str):
    """Pullt das Basis-Image und startet den Build asynchron."""
    if store.get(item_id) is None:
        raise HTTPException(404, detail="Nicht gefunden")
    from .jobs import update_image_async
    update_image_async(item_id)
    return JSONResponse({"status": "updating", "item_id": item_id}, status_code=202)


@router.get("/{item_id}/log")
def get_log(item_id: str):
    """Gibt den letzten Build-Log zurück."""
    item = store.get(item_id)
    if item is None:
        raise HTTPException(404, detail="Nicht gefunden")
    return {"item_id": item_id, "log": item.get("last_log") or ""}

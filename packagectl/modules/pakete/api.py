"""app/modules/pakete/api.py – FastAPI-Router für das Pakete-Modul."""

from typing import Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from astrapi.core.ui.crud_router import make_crud_router
from .storage import store, KEY


class ItemIn(BaseModel):
    name:       Optional[str] = ""
    source_url: Optional[str] = ""
    enabled:    bool          = True


from .jobs import delete_package

router = make_crud_router(store, KEY, ItemIn, on_delete=delete_package)


@router.post("/{item_id}/build")
def build_item(item_id: str):
    if store.get(item_id) is None:
        raise HTTPException(404, detail="Nicht gefunden")
    from .jobs import build_package_async
    build_package_async(item_id)
    return JSONResponse({"status": "building", "item_id": item_id}, status_code=202)


@router.get("/{item_id}/log")
def get_log(item_id: str):
    item = store.get(item_id)
    if item is None:
        raise HTTPException(404, detail="Nicht gefunden")
    return {"item_id": item_id, "log": item.get("last_log") or ""}

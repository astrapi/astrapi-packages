"""
core/ui/crud_router.py – Generischer FastAPI CRUD-Router

Erzeugt einen Standard-CRUD-Router mit folgenden Endpunkten:
  GET    /                    → Liste aller Einträge
  GET    /{item_id}           → Einzelner Eintrag
  POST   /  ?item_id=...      → Anlegen
  PUT    /{item_id}           → Aktualisieren
  PATCH  /{item_id}/toggle    → enabled-Flag umschalten
  DELETE /{item_id}           → Löschen

Verwendung:
    from core.ui.crud_router import make_crud_router
    from pydantic import BaseModel

    class ItemIn(BaseModel):
        ...

    router = make_crud_router(store, KEY, ItemIn)

    # Modulspezifische Extrarouten einfach hinzufügen:
    # @router.post("/{item_id}/run", ...)
"""

from typing import Type

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


def make_crud_router(store, key: str, ItemIn: Type[BaseModel]) -> APIRouter:
    """Erstellt einen generischen CRUD-Router für FastAPI.

    Args:
        store:  YamlStorage-Instanz des Moduls
        key:    Ressourcenname (z.B. "hosts", "tasks")
        ItemIn: Pydantic-Modell für Eingabedaten

    Returns:
        APIRouter mit LIST / GET / CREATE / UPDATE / TOGGLE / DELETE
    """
    label    = key.capitalize()
    singular = key[:-1] if key.endswith("s") else key
    label_s  = label[:-1] if label.endswith("s") else label

    router = APIRouter()

    @router.get("/", summary=f"List {label}")
    def list_items():
        items = store.list()
        return {key: items, "total": len(items)}

    @router.get("/{item_id}", summary=f"Get {label_s}")
    def get_item(item_id: str):
        item = store.get(item_id)
        if item is None:
            raise HTTPException(404, f"{label_s} '{item_id}' nicht gefunden")
        return item

    @router.post("/", summary=f"Create {label_s}", status_code=201)
    def create_item(item_id: str, item: ItemIn):
        try:
            return {"created": item_id, singular: store.create(item_id, item.model_dump())}
        except KeyError as e:
            raise HTTPException(409, str(e))

    @router.put("/{item_id}", summary=f"Update {label_s}")
    def edit_item(item_id: str, item: ItemIn):
        try:
            return {"updated": item_id, singular: store.update(item_id, item.model_dump())}
        except KeyError as e:
            raise HTTPException(404, str(e))

    @router.patch("/{item_id}/toggle", summary=f"Toggle {label_s}")
    def toggle_item(item_id: str):
        try:
            return {"item_id": item_id, "enabled": store.toggle(item_id)}
        except KeyError as e:
            raise HTTPException(404, str(e))

    @router.delete("/{item_id}", summary=f"Delete {label_s}", status_code=204)
    def delete_item(item_id: str):
        try:
            store.delete(item_id)
        except KeyError as e:
            raise HTTPException(404, str(e))

    return router

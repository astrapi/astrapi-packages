"""astrapi_packages.utils.file_routes – generische FastAPI-Routen fuer den
Datei-Editor (file_store.py), von builder/debian/archlinux gemeinsam
genutzt. Siehe projects/packages/planung-datei-editor.md, Abschnitt 2.2.

Verwendung in einem Modul-Router:

    from astrapi_packages.utils.file_routes import build_file_routes
    router.include_router(build_file_routes("debian"))
"""

from fastapi import APIRouter, Body, HTTPException

from astrapi_packages.utils import file_store


def build_file_routes(owner_type: str) -> APIRouter:
    router = APIRouter()

    @router.get(f"/api/{owner_type}/{{item_id}}/files")
    def list_files(item_id: str):
        return file_store.list_files(owner_type, item_id)

    @router.get(f"/api/{owner_type}/{{item_id}}/files/{{filename}}")
    def read_file(item_id: str, filename: str):
        content = file_store.read(owner_type, item_id, filename)
        if content is None:
            raise HTTPException(404, "Datei nicht gefunden")
        return {"filename": filename, "content": content}

    @router.post(f"/api/{owner_type}/{{item_id}}/files/{{filename}}/diff")
    def diff_file(item_id: str, filename: str, payload: dict = Body(...)):
        new_content = payload.get("content", "")
        return {"diff": file_store.diff(owner_type, item_id, filename, new_content)}

    @router.post(f"/api/{owner_type}/{{item_id}}/files/{{filename}}")
    def save_file(item_id: str, filename: str, payload: dict = Body(...)):
        content = payload.get("content", "")
        message = payload.get("message", "")
        file_store.save(owner_type, item_id, filename, content, message)
        return {"ok": True}

    @router.delete(f"/api/{owner_type}/{{item_id}}/files/{{filename}}")
    def delete_file(item_id: str, filename: str, message: str = ""):
        file_store.delete(owner_type, item_id, filename, message)
        return {"ok": True}

    @router.get(f"/api/{owner_type}/{{item_id}}/files/{{filename}}/history")
    def file_history(item_id: str, filename: str, limit: int = 20):
        return file_store.history(owner_type, item_id, filename, limit)

    @router.post(f"/api/{owner_type}/{{item_id}}/files/{{filename}}/restore/{{version_id}}")
    def restore_file(item_id: str, filename: str, version_id: int):
        try:
            file_store.restore(owner_type, item_id, filename, version_id)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True}

    return router

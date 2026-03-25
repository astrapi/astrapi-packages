"""core/modules/sysinfo/api.py – FastAPI-Router für /api/sysinfo/"""
from fastapi import APIRouter
from .engine import collect, collect_cached

router = APIRouter()


@router.get("/")
def get_sysinfo():
    return collect()


@router.get("/cpu")
def get_cpu():
    d = collect_cached()
    return d.get("cpu", {})


@router.get("/ram")
def get_ram():
    d = collect_cached()
    return d.get("mem", {})


@router.get("/disk")
def get_disk():
    d = collect_cached()
    return d.get("disks", [])

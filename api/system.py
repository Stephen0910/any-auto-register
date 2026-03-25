from __future__ import annotations

from fastapi import APIRouter

from application.system import SystemService

router = APIRouter(tags=["system"])
service = SystemService()


@router.get("/solver/status")
def solver_status():
    return service.solver_status()


@router.post("/solver/restart")
def solver_restart():
    return service.restart_solver()

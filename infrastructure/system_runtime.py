from __future__ import annotations

from services.solver_manager import is_running, start_async, stop


class SystemRuntime:
    def solver_status(self) -> dict:
        return {"running": is_running()}

    def restart_solver(self) -> dict:
        stop()
        start_async()
        return {"message": "重启中"}

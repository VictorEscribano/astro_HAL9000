"""Mount control endpoints (simulated OAT)."""
from fastapi import APIRouter
from app.tools.mount import execute_mount_command, get_mount_status, get_mount_log
from app.models.mount import SlewCommand, MountCommandResult, MountStatus

router = APIRouter(prefix="/api/mount", tags=["mount"])


@router.get("/status", response_model=MountStatus)
def mount_status():
    return get_mount_status()


@router.post("/slew", response_model=MountCommandResult)
def slew(cmd: SlewCommand):
    return execute_mount_command(cmd)


@router.post("/stop", response_model=MountCommandResult)
def stop():
    from app.models.mount import SlewCommand
    return execute_mount_command(SlewCommand(target_name="__STOP__"))


@router.post("/park", response_model=MountCommandResult)
def park():
    return execute_mount_command(SlewCommand(target_name="__PARK__"))


@router.post("/sync", response_model=MountCommandResult)
def sync():
    return execute_mount_command(SlewCommand(target_name="__SYNC__"))


@router.get("/log")
def mount_log():
    return {"log": get_mount_log()}

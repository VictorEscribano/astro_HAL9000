"""Simulated OAT mount — converts commands to Meade LX200 serial strings and logs them."""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path

from app.models.mount import MountStatus, SlewCommand, MountCommandResult, TrackingRate

LOG_PATH = Path(__file__).parent.parent.parent / "data" / "mount_commands.log"
LOG_PATH.parent.mkdir(exist_ok=True)

# Global simulated mount state
_state = MountStatus()


def _ra_to_lx200(ra_h: float) -> str:
    """Convert RA decimal hours to LX200 format HH:MM:SS."""
    total_s = int(abs(ra_h) * 3600)
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _dec_to_lx200(dec_deg: float) -> str:
    """Convert Dec decimal degrees to LX200 format ±DD*MM:SS."""
    sign = "+" if dec_deg >= 0 else "-"
    total_s = int(abs(dec_deg) * 3600)
    d = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{sign}{d:02d}*{m:02d}:{s:02d}"


def _log_command(cmd: str):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {cmd}\n"
    with open(LOG_PATH, "a") as f:
        f.write(line)
    _state.log.append(f"{ts} {cmd}")
    if len(_state.log) > 100:
        _state.log = _state.log[-100:]


def execute_mount_command(cmd: SlewCommand) -> MountCommandResult:
    """Simulate a mount command, log LX200 serial strings."""
    global _state
    serial_cmds: List[str] = []
    messages: List[str] = []
    ts = datetime.now(timezone.utc)

    if cmd.ra_h is not None and cmd.dec_deg is not None:
        ra_str = _ra_to_lx200(cmd.ra_h)
        dec_str = _dec_to_lx200(cmd.dec_deg)
        set_ra = f":Sr{ra_str}#"
        set_dec = f":Sd{dec_str}#"
        slew = ":MS#"
        serial_cmds = [set_ra, set_dec, slew]
        for s in serial_cmds:
            _log_command(s)
        _state.ra_h = cmd.ra_h
        _state.dec_deg = cmd.dec_deg
        _state.slewing = True
        _state.parked = False
        _state.tracking = True
        _state.tracking_rate = cmd.tracking_rate
        _state.target_name = cmd.target_name
        messages.append(f"Slewing to RA {ra_str} Dec {dec_str}")
        if cmd.tracking_rate == TrackingRate.SIDEREAL:
            track_cmd = ":TQ#"
        elif cmd.tracking_rate == TrackingRate.LUNAR:
            track_cmd = ":TL#"
        elif cmd.tracking_rate == TrackingRate.SOLAR:
            track_cmd = ":TS#"
        else:
            track_cmd = ":TQ#"
        _log_command(track_cmd)
        serial_cmds.append(track_cmd)

    elif cmd.alt_deg is not None and cmd.az_deg is not None:
        # LX200 alt/az slew
        alt_s = int(abs(cmd.alt_deg) * 3600)
        alt_d = alt_s // 3600
        alt_m = (alt_s % 3600) // 60
        alt_sec = alt_s % 60
        az_s = int(cmd.az_deg * 3600)
        az_d = az_s // 3600
        az_m = (az_s % 3600) // 60
        az_sec = az_s % 60
        serial_cmds = [
            f":Sz{az_d:03d}*{az_m:02d}:{az_sec:02d}#",
            f":Sa+{alt_d:02d}*{alt_m:02d}:{alt_sec:02d}#",
            ":MA#",
        ]
        for s in serial_cmds:
            _log_command(s)
        messages.append(f"Slewing to Alt {cmd.alt_deg:.1f}° Az {cmd.az_deg:.1f}°")

    elif cmd.target_name == "__STOP__":
        _log_command(":Q#")
        serial_cmds = [":Q#"]
        _state.slewing = False
        _state.tracking = False
        messages.append("Mount stopped.")

    elif cmd.target_name == "__PARK__":
        _log_command(":hP#")
        serial_cmds = [":hP#"]
        _state.slewing = False
        _state.tracking = False
        _state.parked = True
        messages.append("Mount parked.")

    elif cmd.target_name == "__SYNC__":
        if _state.ra_h and _state.dec_deg:
            ra_str = _ra_to_lx200(_state.ra_h)
            dec_str = _dec_to_lx200(_state.dec_deg)
            serial_cmds = [f":Sr{ra_str}#", f":Sd{dec_str}#", ":CM#"]
            for s in serial_cmds:
                _log_command(s)
            messages.append("Synced on current coordinates.")

    return MountCommandResult(
        success=True,
        command_strings=serial_cmds,
        message=" | ".join(messages) if messages else "Command executed.",
        timestamp=ts,
    )


def get_mount_status() -> MountStatus:
    return _state


def get_mount_log() -> List[str]:
    try:
        return LOG_PATH.read_text().splitlines()[-50:]
    except FileNotFoundError:
        return []

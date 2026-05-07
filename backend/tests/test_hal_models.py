"""HAL Pydantic schema tests.

These run offline — they don't talk to Ollama.  The instructor-driven parsing
tests live in `test_hal_parse.py` and are marked `@pytest.mark.online` so CI
can skip them when no LLM is reachable."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.models import (
    CameraExposure,
    Intent,
    MountGoto,
    SatellitePassesQuery,
    ToolResult,
    tool_list_for_prompt,
)


# ── MountGoto range validation ───────────────────────────────────────────────


def test_mount_goto_alt_above_horizon_ok():
    m = MountGoto(target_name="M31", alt_deg=45.0, az_deg=120.0)
    assert m.alt_deg == 45.0
    assert m.tracking is True   # default


def test_mount_goto_alt_above_90_rejected():
    with pytest.raises(ValidationError):
        MountGoto(alt_deg=95.0, az_deg=0.0)


def test_mount_goto_negative_alt_rejected():
    with pytest.raises(ValidationError):
        MountGoto(alt_deg=-5.0, az_deg=0.0)


def test_mount_goto_az_must_be_lt_360():
    # 0..359.99 ok, 360 rejected because lt=360 (azimuth wraps)
    MountGoto(alt_deg=30.0, az_deg=359.9)
    with pytest.raises(ValidationError):
        MountGoto(alt_deg=30.0, az_deg=360.0)


def test_mount_goto_ra_dec_bounds():
    MountGoto(ra_h=12.0, dec_deg=-30.0)
    with pytest.raises(ValidationError):
        MountGoto(ra_h=24.0, dec_deg=0.0)         # ra in [0, 24)
    with pytest.raises(ValidationError):
        MountGoto(ra_h=12.0, dec_deg=91.0)        # dec must be ≤ 90


# ── Camera exposure validation ───────────────────────────────────────────────


def test_camera_exposure_seconds_positive():
    CameraExposure(exposure_seconds=30.0)
    with pytest.raises(ValidationError):
        CameraExposure(exposure_seconds=0.0)
    with pytest.raises(ValidationError):
        CameraExposure(exposure_seconds=4000.0)   # max 3600


def test_camera_exposure_iso_optional_and_bounded():
    CameraExposure(exposure_seconds=10.0)         # iso optional
    CameraExposure(exposure_seconds=10.0, iso=800)
    with pytest.raises(ValidationError):
        CameraExposure(exposure_seconds=10.0, iso=49)


def test_camera_filter_literal():
    with pytest.raises(ValidationError):
        CameraExposure(exposure_seconds=10.0, filter="weird")  # type: ignore[arg-type]


# ── Satellite query ──────────────────────────────────────────────────────────


def test_satellite_passes_norad_positive():
    SatellitePassesQuery(norad_id=25544, days=3)
    with pytest.raises(ValidationError):
        SatellitePassesQuery(norad_id=0, days=3)
    with pytest.raises(ValidationError):
        SatellitePassesQuery(norad_id=25544, days=0)
    with pytest.raises(ValidationError):
        SatellitePassesQuery(norad_id=25544, days=11)


# ── Intent + ToolResult ──────────────────────────────────────────────────────


def test_intent_kind_literal():
    Intent(kind="tool", rationale="needs hardware")
    Intent(kind="conversation", rationale="explanation")
    with pytest.raises(ValidationError):
        Intent(kind="other", rationale="")  # type: ignore[arg-type]


def test_tool_result_round_trip():
    ok = ToolResult(tool="weather", success=True, result={"clouds_pct": 30})
    fail = ToolResult(tool="mount_goto", success=False, error="timeout")
    assert ok.success and ok.error is None
    assert not fail.success and fail.error == "timeout"


# ── Prompt rendering ─────────────────────────────────────────────────────────


def test_tool_list_renders_all_tools():
    out = tool_list_for_prompt()
    # Must mention every tool name
    for token in ("mount_goto", "satellite_search", "object_position", "python_exec"):
        assert token in out


def test_system_prompt_substitutes_placeholders():
    from app.agent.prompts import build_system_prompt
    rendered = build_system_prompt(memory_context="user observed M42 last night")
    assert "user observed M42 last night" in rendered
    assert "{tool_list}" not in rendered
    assert "{memory_context}" not in rendered
    assert "{session_context}" not in rendered

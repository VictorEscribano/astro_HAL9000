"""Pydantic schemas for HAL tool calls.

Every tool the agent can invoke is described by a model that inherits from
`HALToolCall`.  These schemas are what `instructor` constrains the LLM to fill
in — that's how we guarantee that no malformed tool argument ever reaches the
hardware layer.

Field descriptions are read by the LLM at extraction time, so they should be
written for the model's benefit (concise, in plain English, with enough
context to disambiguate units and defaults)."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# ── Base ──────────────────────────────────────────────────────────────────────


class HALToolCall(BaseModel):
    """Marker base class.  All concrete tool schemas inherit from this so the
    intent classifier can return a discriminated union without ambiguity."""

    model_config = {"extra": "forbid"}


# ── Mount ────────────────────────────────────────────────────────────────────


class MountGoto(HALToolCall):
    """Move the telescope mount to a target.

    Provide one of:
      - `target_name` (e.g. "Jupiter", "M31") — HAL resolves coords
      - `ra_h` + `dec_deg` (equatorial)
      - `alt_deg` + `az_deg` (horizontal)

    Never command an altitude below 20° — that would point at the trees.
    """

    target_name: str | None = Field(
        None,
        description="Object name, e.g. 'Jupiter', 'M31', 'NGC 224', 'Polaris'.",
    )
    ra_h: float | None = Field(
        None, ge=0.0, lt=24.0,
        description="Right ascension in hours (0–24)."
    )
    dec_deg: float | None = Field(
        None, ge=-90.0, le=90.0,
        description="Declination in degrees (−90 to +90)."
    )
    alt_deg: float | None = Field(
        None, ge=0.0, le=90.0,
        description="Altitude in degrees above horizon (0–90). Never command < 20°."
    )
    az_deg: float | None = Field(
        None, ge=0.0, lt=360.0,
        description="Azimuth in degrees, 0=North, 90=East."
    )
    tracking: bool = Field(
        True,
        description="Engage sidereal tracking after the slew completes."
    )


class MountTrack(HALToolCall):
    """Set the mount's tracking rate.  Use `MountAbort` if you want to stop
    motion entirely; this tool is for selecting between rates."""

    rate: Literal["sidereal", "lunar", "solar"] = Field(
        ...,
        description="Tracking rate to engage."
    )


class MountPark(HALToolCall):
    """Park the mount in its safe stowed position.  Refuses if a long
    exposure is currently running unless `force=True`."""

    force: bool = Field(False, description="Park even if an exposure is in progress.")


class MountAbort(HALToolCall):
    """EMERGENCY STOP — halts any mount motion immediately.  Always honoured
    without confirmation; it's the one tool with priority over everything."""

    reason: str | None = Field(None, description="Optional human-readable reason.")


# ── Ephemerides / catalogue queries ──────────────────────────────────────────


class ObjectPositionQuery(HALToolCall):
    """Resolve a celestial object by name and return its current RA/Dec, Alt/Az,
    rise/set/transit times.  Use this whenever the user mentions an object."""

    name: str = Field(..., description="Object name, catalogue ID, or planet name.")


class SkyTonightQuery(HALToolCall):
    """List ranked observable objects from the observer's location tonight."""

    min_alt_deg: float = Field(
        20.0, ge=0.0, le=90.0,
        description="Minimum altitude in degrees to be considered visible."
    )


class MoonInfoQuery(HALToolCall):
    """Get current Moon phase, illumination, rise/set, and sky-interference
    rating (helps decide whether deep-sky imaging is feasible tonight)."""


# ── Satellites ────────────────────────────────────────────────────────────────


class SatelliteSearch(HALToolCall):
    """Search a satellite by name and return its NORAD catalogue ID.
    Always run this before passes/track/feasibility when only a name is given."""

    name: str = Field(..., description="Common name, e.g. 'ISS', 'Hubble', 'Mohammed VI-A'.")


class SatellitePassesQuery(HALToolCall):
    """Predicted visible passes of a satellite from the observer over the next
    `days` days.  Use after `SatelliteSearch` resolved the NORAD ID."""

    norad_id: int = Field(..., gt=0, description="NORAD catalogue ID.")
    days: int = Field(3, ge=1, le=10, description="Window in days (1–10).")


class SatelliteGroundTrack(HALToolCall):
    """Propagate a satellite's TLE to produce a ground-track polyline for the
    map view.  Use this whenever the user says 'show … on the map'."""

    norad_id: int = Field(..., gt=0)
    minutes: float = Field(
        190.0, ge=10.0, le=720.0,
        description="Propagation horizon. 190 ≈ two ISS orbits."
    )


class TrackingFeasibilityCheck(HALToolCall):
    """Verify whether the OAT mount can keep up with a target's peak angular
    rate.  ISS peak ≈ 1800 arcsec/s; sidereal = 15 arcsec/s."""

    target_name: str
    peak_rate_arcsec_s: float = Field(..., gt=0.0)


# ── Camera (currently a stub; harness will land later) ───────────────────────


class CameraExposure(HALToolCall):
    """Trigger a single exposure with the imaging camera."""

    exposure_seconds: float = Field(..., gt=0.0, le=3600.0)
    iso: int | None = Field(None, ge=50, le=102400)
    binning: Literal[1, 2, 3, 4] = 1
    filter: Literal["luminance", "ha", "oiii", "sii", "rgb", "none"] = "none"


class CameraSequence(HALToolCall):
    """Schedule a sequence of exposures with the same parameters."""

    frames: int = Field(..., ge=1, le=500)
    exposure_seconds: float = Field(..., gt=0.0, le=3600.0)
    interval_seconds: float = Field(0.0, ge=0.0)
    iso: int | None = Field(None, ge=50, le=102400)


# ── Environment ──────────────────────────────────────────────────────────────


class WeatherQuery(HALToolCall):
    """Current weather + astronomical seeing/transparency at observer site."""


# ── Generic Python ───────────────────────────────────────────────────────────


class PythonExec(HALToolCall):
    """Execute arbitrary Python in the sandboxed analysis kernel.  Use this
    only when no other tool fits (custom calculations, plotting, file I/O on
    the user's data dir).  Assign the answer to `result`."""

    code: str = Field(..., min_length=1, description="Python source to execute.")


# ── Web search ───────────────────────────────────────────────────────────────


class WebSearch(HALToolCall):
    """Search the live web for facts HAL doesn't have locally — current events,
    biographies, equipment reviews, links to papers/profiles/wikipedia, weather
    advisories, etc.

    Use this ONLY when the answer needs information beyond the model's training
    cut-off or beyond HAL's astronomy tools (ephemerides, satellites, weather
    already cover those).  Examples that DO fit: "who is John Dobson?",
    "latest news from the Webb telescope", "find the Wikipedia page of
    NGC 6946", "compare reviews of the ZWO ASI294MC Pro".

    The caller specifies how many results to retrieve; 3-5 is usually enough.
    Backend prefers Tavily (cleaner snippets) and falls back to DuckDuckGo if
    no API key is configured."""

    query: str = Field(..., min_length=2, max_length=300,
                       description="Search query in natural language. Be specific.")
    max_results: int = Field(default=5, ge=1, le=10,
                             description="How many top results to return (1-10).")


# ── Discriminated union of every tool ────────────────────────────────────────


# Type alias kept for callers that want a tagged union; the extraction path
# uses two-step (name then args) because Qwen 2.5 7B emits "$ref" tags when
# given a Pydantic Union, which fails validation.
AnyToolCall = Union[
    MountGoto,
    MountTrack,
    MountPark,
    MountAbort,
    ObjectPositionQuery,
    SkyTonightQuery,
    MoonInfoQuery,
    SatelliteSearch,
    SatellitePassesQuery,
    SatelliteGroundTrack,
    TrackingFeasibilityCheck,
    CameraExposure,
    CameraSequence,
    WeatherQuery,
    PythonExec,
    WebSearch,
]


ToolName = Literal[
    "mount_goto", "mount_track", "mount_park", "mount_abort",
    "object_position", "sky_tonight", "moon_info",
    "satellite_search", "satellite_passes", "satellite_ground_track",
    "tracking_feasibility",
    "camera_expose", "camera_sequence",
    "weather", "python_exec",
    "web_search",
]


class ToolSelection(BaseModel):
    """First step of tool extraction: pick which tool fits the user's turn.
    Kept as a tiny separate schema (just a Literal field) so the LLM doesn't
    get tangled in a Union with `$ref` indirection."""

    tool_name: ToolName = Field(..., description="Name of the tool that best fits the user's request.")


class Plan(BaseModel):
    """Ordered list of tools HAL will execute to fulfil a multi-step request.

    Examples:
      - "apunta a M42 y haz 5 fotos de 30 s" →
            steps=["mount_goto", "camera_sequence"]
      - "muestra la ISS en el mapa" →
            steps=["satellite_search", "satellite_ground_track"]
      - "¿dónde está Júpiter?" →
            steps=["object_position"]
      - "Hola HAL" →
            steps=[]   # no tool needed; intent classifier should have routed
                       # to conversation, but a zero-step plan is a valid answer.

    Keep the list minimal — only include steps that are required to answer
    the user.  At most 6 steps; longer plans should be broken into multiple
    user turns."""

    steps: list[ToolName] = Field(
        default_factory=list,
        max_length=6,
        description="Ordered list of tool names to execute, in dependency order."
    )
    rationale: str = Field(
        "",
        description="One short sentence (in the user's language) explaining the plan."
    )


# ── Intent classification ────────────────────────────────────────────────────


class Intent(BaseModel):
    """Output of the intent_classifier node — does this turn require a tool
    call, or is it pure conversation we can answer from memory + knowledge?"""

    kind: Literal["tool", "conversation"] = Field(
        ...,
        description=(
            "'tool' if executing this turn requires hardware control, an external "
            "data lookup (ephemerides, satellites, weather), or numerical "
            "computation. 'conversation' for chit-chat, explanations, and "
            "questions HAL can answer from its own astronomy knowledge."
        ),
    )
    rationale: str = Field(
        "",
        description="One short sentence explaining the choice (for logs/debug).",
    )


# ── Tool execution result ────────────────────────────────────────────────────


class ToolResult(BaseModel):
    """Uniform return shape from every tool wrapper.  Either result is set
    (success) or error is set (failure, with message the LLM can read)."""

    tool: str
    success: bool
    result: dict | list | str | None = None
    error: str | None = None


# ── Catalogue mapping (used by the prompt builder) ───────────────────────────


# Human-readable docs surfaced to the model as part of {tool_list}.
TOOL_CATALOGUE: list[tuple[str, type[HALToolCall], str]] = [
    ("mount_goto",                  MountGoto,                 "Slew the mount to a target (name, RA/Dec, or Alt/Az)."),
    ("mount_track",                 MountTrack,                "Set tracking rate (sidereal/lunar/solar/off)."),
    ("mount_park",                  MountPark,                 "Stow the mount in its parked position."),
    ("mount_abort",                 MountAbort,                "Emergency stop — halts mount motion immediately."),
    ("object_position",             ObjectPositionQuery,       "Resolve a name to RA/Dec, Alt/Az, rise/set/transit."),
    ("sky_tonight",                 SkyTonightQuery,           "Ranked list of observable objects right now."),
    ("moon_info",                   MoonInfoQuery,             "Moon phase, illumination, sky-interference."),
    ("satellite_search",            SatelliteSearch,           "Resolve a satellite name to its NORAD ID."),
    ("satellite_passes",            SatellitePassesQuery,      "Visible passes for a NORAD ID."),
    ("satellite_ground_track",      SatelliteGroundTrack,      "Ground-track polyline for the map view."),
    ("tracking_feasibility",        TrackingFeasibilityCheck,  "Can the OAT keep up with this peak rate?"),
    ("camera_expose",               CameraExposure,            "Single exposure with the imaging camera."),
    ("camera_sequence",             CameraSequence,            "Scheduled multi-frame exposure sequence."),
    ("weather",                     WeatherQuery,              "Current weather + seeing/transparency."),
    ("python_exec",                 PythonExec,                "Run arbitrary Python in the analysis kernel."),
    ("web_search",                  WebSearch,                 "Search the live web for current events, biographies, links, papers, equipment reviews — anything outside the model's training data or HAL's astronomy tools."),
]


def tool_list_for_prompt() -> str:
    """Render TOOL_CATALOGUE as a bullet list for inclusion in the system prompt."""
    return "\n".join(f"- `{name}` — {desc}" for name, _cls, desc in TOOL_CATALOGUE)


# Tool-name → schema lookup for the two-step extractor (defined here so it
# can see TOOL_CATALOGUE).
TOOL_NAME_TO_SCHEMA: dict[str, type[HALToolCall]] = {
    name: cls for name, cls, _ in TOOL_CATALOGUE
}

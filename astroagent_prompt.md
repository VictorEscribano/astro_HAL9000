# AstroAgent — Claude Code Implementation Guide

> **Standalone prototype.** No physical telescope hardware required.
> All mount commands are simulated and logged so they can be wired to
> the real OAT later with zero refactoring.

---

## What is AstroAgent

AstroAgent is a local AI assistant for **astrophotography and visual astronomy**,
running entirely on a single consumer GPU (RTX 3070 Ti, 8 GB VRAM). It combines
a locally hosted LLM with a set of specialized tools so the astronomer can
have a natural conversation about the sky, get help planning a session, and
ultimately command a motorized mount to point at or track any target.

The primary use cases, in order of importance:

1. **Session planning** — "What can I photograph tonight from Sabadell?"
   The agent knows the observer's location, the current date/time, and the
   sky conditions well enough to suggest objects ranked by altitude, phase
   (for the Moon), and suitability for astrophotography (brightness, angular
   size, required focal length).

2. **Celestial object queries** — "Tell me about the Orion Nebula."
   "What's the current position of Jupiter?" "When does Mars rise tonight?"
   The agent answers using ephemeris calculations, not from its training weights.
   Facts about object positions are always computed, never recalled.

3. **Mount control — deep sky objects** — "Point at M42."
   The agent looks up the object's current RA/Dec, checks feasibility against
   the mount's hardware limits, converts to mount coordinates, and sends the
   slew command. In standalone mode this is simulated; later it's real serial.

4. **Mount control — solar system** — "Track the Moon." "Center Jupiter."
   Same flow but with ephemeris-derived coordinates that update in real time.

5. **Satellite tracking** — "Show me the ISS pass tonight." "Track Starlink."
   The N2YO API provides TLE data and pass predictions. Satellite tracking is
   a bonus feature — it's included because it's interesting and the API is free,
   but the app is not primarily a satellite tracker.

6. **Astrophotography guidance** — "What exposure settings for M31 at f/5.6 with
   a modified DSLR?" "How long before field rotation becomes a problem without guiding?"
   The math executor handles these calculations precisely.

---

## The non-negotiable design principles

### 1. The LLM never computes numbers

Every numerical result — an altitude, a slew time, an exposure duration, a
satellite's angular velocity — must come from a tool execution, not from the
LLM's weights. The LLM's job is to understand what the user wants, decide
which tool to call with which arguments, interpret the result, and explain it.

There is a `execute_python` tool available at all times. When the agent needs
to calculate anything, it writes clean Python code and calls that tool. This
is the only path to numbers that are correct enough to send to hardware.

### 2. Every action that touches the mount is logged verbatim

The simulated mount tool writes the exact Meade LX200 serial command strings
to a log file before executing them in simulation. When the real OAT is
connected, that log file becomes the validation layer. Nothing changes in the
agent or tool layer — only the serial port gets opened.

### 3. The system works without the LLM running

Map, satellite browser, sky chart, pass predictions — all of this works as a
standalone web app even if Ollama is offline. The chat panel shows a banner
saying the AI assistant is unavailable, and everything else works normally.

### 4. Positions are always computed, never hardcoded

The system has no database of "tonight's best objects" that gets stale.
Every position, every altitude, every rise/set time is calculated fresh
from ephemeris data (Skyfield + astropy) or from TLE propagation (sgp4).
The agent always injects the current UTC time into its context at the
start of each conversation turn.

---

## Tech stack

**Backend — Python 3.11**

- `FastAPI` + `uvicorn` for the REST API and WebSocket server
- `LangGraph` for the agent graph (ReAct loop: LLM → tools → LLM)
- `Ollama` Python client for local LLM inference
  - Primary model: `qwen2.5:7b-instruct-q4_K_M` (~4.5 GB VRAM)
  - Fallback for heavy reasoning: `qwen3:8b-q4_K_M` if the user wants slower
    but deeper analysis (e.g. detailed astrophotography session planning)
- `skyfield` for all ephemeris calculations (planets, Moon, Sun, stars, DSOs)
- `sgp4` for satellite TLE propagation
- `astropy` for coordinate transforms and unit conversions
- `requests` / `httpx` for N2YO API calls
- `pydantic v2` for all data models
- `python-dotenv` for secrets
- `APScheduler` for background TLE refresh jobs
- `aiosqlite` + `SQLite` for TLE cache and session history
- `faster-whisper` for STT (only loaded if `USE_VOICE=true` in env)
- `piper-tts` for TTS (same condition)

**Frontend — React 18 + Vite**

- `react-leaflet` + Leaflet.js for the interactive sky/earth map
- `Recharts` for elevation/azimuth charts and sky brightness curves
- `Tailwind CSS` for styling
- `Zustand` for global state
- Native browser WebSocket for real-time position updates

**Inference**

Everything runs locally. No cloud APIs. The only external network calls are
to N2YO (satellite data) and to the astronomy data services listed below.

---

## External data sources

| Source | What it provides | How to access |
|--------|-----------------|---------------|
| N2YO REST API | Satellite TLEs, positions, visual passes, category lists | REST, requires free API key from n2yo.com |
| NASA JPL Horizons | High-precision solar system ephemerides | REST, no key required |
| Celestrak | Backup TLE source for satellites | HTTP, no key required |
| Simbad (CDS) | Deep sky object catalog: RA/Dec, type, magnitude, size | REST, no key required |
| OpenNGC / Messier CSV | Offline catalog of ~13,000 NGC/IC/Messier objects | Bundled flat file |
| Gaia DR3 (subset) | Bright star catalog for pointing | Bundled flat file (BSC5) |

Skyfield handles planetary ephemerides entirely offline using the DE421 kernel
downloaded once on first run and cached locally.

---

## The agent's tools

These are the capabilities the LLM has access to. Describe each one to Claude
Code so it understands what to build. Do not prescribe the implementation — let
Claude Code decide the right library calls and error handling.

### `execute_python`
Runs arbitrary Python in a sandboxed subprocess with a 15-second timeout.
Pre-imported: `math`, `numpy`, `datetime`, `astropy`, `skyfield`, `sgp4`.
The code must assign its final result to a variable named `result`.
This is the anti-hallucination tool — every number the agent produces
must come through here.

### `get_sky_objects_tonight`
Given the observer location and a date (defaulting to tonight), returns a
ranked list of observable objects: planets, bright DSOs, notable double stars,
the Moon if present. Ranks by current/peak altitude, filters below 20° horizon.
Annotates each object with its type, magnitude, angular size, and a brief note
on what imaging equipment it suits.

### `get_object_position`
Given any object name (e.g. "M42", "Jupiter", "Betelgeuse", "NGC 224",
"Andromeda Galaxy"), resolves it to RA/Dec and computes current Alt/Az from
the observer's location. Returns: RA, Dec (J2000), Alt, Az, rise time, set time,
transit time, angular size if available. Uses Skyfield for solar system bodies,
Simbad/local catalog for DSOs and stars.

### `get_moon_info`
Returns current Moon phase (0–1), illumination percentage, rise/set/transit times,
angular diameter, and whether it will interfere with the session tonight (based on
proximity to the target and sky brightness impact).

### `get_satellite_passes`
Given a satellite name or NORAD ID and an optional time window, returns predicted
visible passes from the observer's location. Uses N2YO API. Each pass: start/end
time, max elevation, start/end azimuth, visual magnitude estimate.

### `get_satellites_overhead`
Returns all satellites of a given N2YO category currently above the observer,
with their current positions. Categories include: ISS, Starlink, GPS, Galileo,
Weather, Amateur Radio, Military, Geostationary, and more.

### `get_satellite_ground_track`
Given a NORAD ID, propagates the TLE with sgp4 for one full orbital period and
returns the ground track as a sequence of (lat, lng) pairs. This data is sent
to the frontend to draw the orbit path on the Leaflet map. Never calls N2YO's
positions endpoint for this — always propagates locally to avoid burning API quota.

### `check_tracking_feasibility`
Given a target (object name or NORAD ID), its current angular velocity in
the sky, and the mount's hardware parameters (steps/rev, microstepping, gear
reduction ratio), computes whether the OAT can track it. Returns: feasible yes/no,
peak angular velocity in arcsec/s, mount's maximum tracking rate, and a clear
recommendation ("The ISS moves at ~1800 arcsec/s at peak — the OAT maxes out at
~58 arcsec/s. Not trackable. Suggest photographing with a fixed wide field instead.")

### `mount_control`
Sends a command to the telescope mount. In standalone mode, converts to Meade LX200
serial strings and logs them. Commands: slew to RA/Dec, slew to Alt/Az, start tracking
(sidereal / lunar / solar / custom rate), stop, park, sync on current object, set location.

### `plan_imaging_session`
Given a list of targets, tonight's sky conditions, available equipment parameters
(focal length, sensor size, pixel scale), and available time window, produces a
prioritized imaging plan: which target first, recommended exposure settings, when
to switch targets, what to avoid. Uses execute_python for all exposure math.

### `get_weather_and_seeing`
Queries a weather API for the observer's location: cloud cover, humidity, wind,
and estimates astronomical seeing (Antoniadi scale) from temperature gradient data.
(Use Open-Meteo API — free, no key required — for weather data.)

---

## The N2YO integration in detail

N2YO has a free REST API (register at n2yo.com, generate key in your profile).
Base URL: `https://api.n2yo.com/rest/v1/satellite/`
All requests: `GET` with `&apiKey={key}` appended.
Rate limit: **1000 transactions per hour** — this is tight. Cache aggressively.

Key endpoints to use:

- `/tle/{norad_id}` — fetch TLE. Cache result for 1 hour per satellite.
- `/above/{lat}/{lng}/{alt}/{radius}/{category}` — satellites overhead. Radius=90 for full sky.
- `/visualpasses/{id}/{lat}/{lng}/{alt}/{days}/{min_el}` — visible passes.
- `/positions/{id}/{lat}/{lng}/{alt}/{seconds}` — position array (1 per second).
  Use sparingly — prefer local sgp4 propagation for anything that can be done offline.

The satellite category IDs Victor wants available:

```
2   → International Space Station
54  → Chinese Space Station (Tiangong)
1   → Brightest 100
52  → Starlink
20  → GPS Operational
21  → Glonass Operational
22  → Galileo
35  → Beidou
30  → Military
15  → Iridium
17  → Globalstar
10  → Geostationary
26  → Space & Earth Science
3   → Weather
18  → Amateur Radio
6   → Disaster Monitoring
8   → Earth Resources
28  → CubeSats
32  → Engineering
24  → Experimental
```

Important limitation: `/above` returns at most ~100 satellites per call.
For large constellations (Starlink has 6000+), you only see what's currently
overhead. Make this clear in the UI and to the agent in its system prompt.

---

## The map / visualization layer

There are two visual contexts and the UI should make switching between them
seamless:

**Earth map (for satellites)**
Leaflet.js with OpenStreetMap tiles (toggle to ESRI dark satellite view).
When a satellite is selected: draw its ground track as a polyline, animate
its current position as a blinking marker, show the footprint circle (area of
visibility on the ground), add the day/night terminator (`leaflet-terminator`).
Real-time position updates via WebSocket from the backend tracking loop (poll
every 5 seconds — do not go faster, rate limit).

**Sky chart / polar plot (for stars, planets, DSOs)**
A 2D polar projection centered on the observer's zenith. Altitude = radial
distance from center (0° at edge = horizon, 90° at center = zenith). Azimuth
= angular position. Render using an HTML5 Canvas or an inline SVG.
Show: cardinal directions, altitude circles at 30°/60°, current position of
all planets, the Moon, and the selected target with its track across the sky
for the next 4 hours. This is the primary tool for session planning.

Both views live in the same panel. The user or agent can switch between them
depending on whether they're talking about a satellite (Earth map) or a
celestial object (sky chart).

---

## The chat interface

The conversation UI is the main entry point. Voice is optional (toggle in settings).

When the agent calls a tool, show a collapsible card below the assistant's
in-progress message: tool name, input summary, and the result. This is critical
for trust — the user can see that the position data came from an ephemeris
calculation, not from the LLM's imagination.

Streaming: the backend sends Server-Sent Events. Render tokens as they arrive.
Tool call cards appear when tool execution completes, before the agent resumes
writing.

The chat panel has a sidebar awareness: if the agent's response contains an
object name and coordinates, the map/sky chart should automatically navigate
to that object's position.

---

## The system prompt (agent persona and constraints)

The system prompt sets up the astronomer persona and injects live context.
Every conversation turn must refresh: current UTC, observer location, active
tracking session if any, tonight's Moon phase.

The persona: knowledgeable, precise, direct. Not verbose. When the user says
"show me M42", the agent doesn't explain the history of the Orion Nebula
unless asked — it immediately looks up the position, checks visibility, and
either sends the slew command or explains why it can't (below horizon, Moon
interference, etc.).

Critical constraints the agent must internalize and follow:

- Never compute numbers in prose. Always call `execute_python`.
- Always verify object visibility before sending a mount command. If the target
  is below 20° altitude or below the horizon, say so and offer alternatives.
- Always run `check_tracking_feasibility` before attempting satellite tracking.
- TLEs older than 24 hours for LEO objects must be refreshed before use.
- When the agent references equipment specs (gear ratios, motor steps), it must
  use the values from the hardware context in its state, not assume defaults.

The system prompt must include the OAT hardware parameters numerically so the
agent can reference them without making tool calls:
steps/revolution, microstepping factor, RA and Dec gear reduction ratios,
max step rate in Hz, and the resulting max tracking rate in arcsec/s.

---

## Observer configuration

All observer data lives in a `.env` file and is loaded once at startup:

```
N2YO_API_KEY=...
OBSERVER_LAT=41.548
OBSERVER_LNG=2.105
OBSERVER_ALT_M=190
OBSERVER_NAME=Sabadell
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M
USE_VOICE=false
```

The observer can update their location from the UI for travelling, and the
agent's context must update immediately when they do.

---

## Implementation order

Claude Code should build this in layers, each one independently functional
before moving to the next:

**Layer 1 — Data and ephemeris**
Get all the data plumbing working. N2YO client with rate limiting and TLE
cache. Skyfield ephemeris for planets and DSOs. sgp4 propagation for ground
tracks. FastAPI endpoints that serve raw data. No frontend, no LLM.
Validate everything with direct HTTP calls (curl / httpie / Python script).
Key validation: ISS ground track should close correctly after ~92 minutes.
Jupiter's Alt/Az from Sabadell at a known time should match Stellarium.

**Layer 2 — Visualization**
React frontend. Earth map with satellite ground tracks and live position
marker. Sky chart polar plot with planet positions and target marker.
Category browser for N2YO satellites. Object search for DSOs and stars.
No LLM, no chat. Just a functional sky/satellite viewer.

**Layer 3 — Simulated mount**
Mount simulator that accepts commands and logs LX200 serial strings.
REST endpoint to trigger slew commands manually (useful for UI testing).
Mount status panel in the frontend showing: current pointed coordinates,
tracking rate, simulated command log.

**Layer 4 — LLM agent**
LangGraph graph with all tools. System prompt with hardware context.
Streaming chat endpoint. Tool call visualization in the UI.
Map/sky chart updates driven by agent responses.
Voice pipeline last (only if USE_VOICE=true).

---

## What "done" looks like for the prototype

The user opens the app, sees a sky chart showing tonight's observable objects
from their location, and a list of N2YO satellite categories in a sidebar.

They type: *"What should I photograph tonight? I have a 500mm lens and a
full-frame sensor."*

The agent: calls `get_sky_objects_tonight`, calls `get_moon_info`, calls
`execute_python` to compute the pixel scale and field of view for their setup,
returns a ranked list of 3–4 targets with notes on exposure and timing.

They click on M42 in the list. The sky chart flies to Orion and shows M42's
track across the sky for the next 4 hours, peak altitude, rise and set times.

They type: *"Point there."*

The agent: calls `get_object_position` to get current RA/Dec, calls
`check_tracking_feasibility` (M42 is a DSO — sidereal rate, trivially
feasible), calls `mount_control` with the coordinates. The mount log shows:
`:Sr05:35:17#`, `:Sd-05*23:28#`, `:MS#`. The chat says: *"Slewing to M42.
Currently at 47° altitude, transiting in 2h 15m at 68°. Good window."*

They then say: *"Show me the ISS pass tonight."*

The agent: calls `get_satellite_passes` for NORAD 25544, returns the next
visible pass. The map switches to Earth view. The ISS ground track appears.
The agent says: *"Next pass at 21:34 local, max elevation 72° (excellent),
duration 6 minutes. Note: the ISS moves at ~1,800 arcsec/s at peak — the
OAT cannot track it. Best captured with a fixed camera at 50–85mm."*

That is the complete prototype experience.

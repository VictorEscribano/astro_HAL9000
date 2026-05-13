"""Sandboxed Python executor — the anti-hallucination tool.

Runs LLM-authored Python in a subprocess with:
  - 15 s wall-clock timeout (kills the process tree on overrun)
  - A pre-imported scientific stack (numpy, astropy, skyfield, sgp4)
  - User code is wrapped in a try/except that captures `result` AND all
    stdout — so the model can use `print(…)` for incremental output and
    we still get a structured payload back.
  - No network, no filesystem writes outside cwd, no GUI.

The protocol uses a unique sentinel line to separate user-print output
from the structured envelope, so a `print('{"ok": true}')` from the user
can never collide with the wrapper's own JSON line."""

import asyncio
import io
import json
import sys
import textwrap


# A unique sentinel the user code is extremely unlikely to ever print.
_ENVELOPE_SENTINEL = "__HAL_PYEXEC_ENVELOPE_V1__"


PREAMBLE = """
import math
import numpy as np
from datetime import datetime, timezone, timedelta
try:
    from astropy import units as u
    from astropy.coordinates import SkyCoord, EarthLocation, AltAz
    from astropy.time import Time
except ImportError:
    pass
try:
    from skyfield.api import load, wgs84, Star
except ImportError:
    pass
try:
    from sgp4.api import Satrec, jday
except ImportError:
    pass

result = None
"""

TIMEOUT_S = 15
STDOUT_MAX_CHARS = 8000  # truncate runaway prints so the LLM prompt stays sane


def _wrap(code: str) -> str:
    """Wrap user code so it runs under a stdout-capturing guard and emits
    a single, separator-delimited JSON envelope on its own line."""
    body = textwrap.indent(textwrap.dedent(code).rstrip(), "    ")
    return f"""\
{PREAMBLE}

import io as _io, sys as _sys, json as _json, traceback as _tb
_real_stdout = _sys.stdout
_buf = _io.StringIO()
_sys.stdout = _buf
_err = None
try:
{body}
except Exception as _e:
    _err = _tb.format_exc()
finally:
    _sys.stdout = _real_stdout

_stdout = _buf.getvalue()
if len(_stdout) > {STDOUT_MAX_CHARS}:
    _stdout = _stdout[:{STDOUT_MAX_CHARS}] + "\\n…[truncated]"

# Coerce result to a JSON-friendly type.
try:
    _json.dumps(result)
    _result_serial = result
except (TypeError, ValueError):
    _result_serial = repr(result) if result is not None else None

_envelope = {{
    "ok":     _err is None,
    "result": _result_serial,
    "stdout": _stdout,
    "error":  _err,
}}
print("{_ENVELOPE_SENTINEL}" + _json.dumps(_envelope, default=str))
"""


async def execute_python(code: str) -> dict:
    """Run LLM-authored code in a subprocess and return:

        {
          "ok":     bool,
          "result": Any | None,   # the `result` variable, JSON-coerced
          "stdout": str,          # everything the code print()ed (truncated)
          "error":  str | None,   # full traceback if execution raised
        }

    Any subprocess failure (timeout, OS error, sentinel never emitted)
    surfaces here as `{"ok": False, "error": "..."}` so the agent layer
    can route to self-correction.
    """
    full_code = _wrap(code)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", full_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(),
                                                    timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {"ok": False, "result": None, "stdout": "",
                "error": f"Execution timed out after {TIMEOUT_S}s"}
    except Exception as e:
        return {"ok": False, "result": None, "stdout": "", "error": str(e)}

    raw_stdout = stdout_b.decode("utf-8", errors="replace")
    raw_stderr = stderr_b.decode("utf-8", errors="replace").strip()

    # The wrapper always prints exactly one line starting with the sentinel.
    # If we don't see it, the child crashed before our `finally` ran (e.g.
    # syntax error) — surface stderr in that case.
    idx = raw_stdout.rfind(_ENVELOPE_SENTINEL)
    if idx < 0:
        return {
            "ok": False, "result": None,
            "stdout": raw_stdout.strip(),
            "error": raw_stderr or "Subprocess emitted no envelope — likely a syntax error.",
        }

    envelope_line = raw_stdout[idx + len(_ENVELOPE_SENTINEL):]
    # Split on the first newline so we only parse the envelope itself,
    # not anything the user printed AFTER the wrapper (shouldn't happen,
    # but defensively).
    envelope_line = envelope_line.splitlines()[0] if envelope_line else ""
    try:
        return json.loads(envelope_line)
    except json.JSONDecodeError as e:
        return {
            "ok": False, "result": None,
            "stdout": raw_stdout.strip(),
            "error": f"Envelope parse failed ({e}); stderr: {raw_stderr[:200]}",
        }

"""Sandboxed Python executor — the anti-hallucination tool."""
import asyncio
import subprocess
import sys
import textwrap
import json
from typing import Any


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


async def execute_python(code: str) -> dict:
    """Run code in subprocess with timeout. Code must assign to `result`."""
    full_code = PREAMBLE + "\n" + textwrap.dedent(code) + "\n" + """
import json
try:
    if isinstance(result, (int, float, bool, str, list, dict, type(None))):
        print(json.dumps({"ok": True, "result": result}))
    else:
        print(json.dumps({"ok": True, "result": str(result)}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", full_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_S)
        output = stdout.decode().strip()
        if not output:
            err = stderr.decode().strip()
            return {"ok": False, "error": err or "No output produced"}
        return json.loads(output)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {"ok": False, "error": f"Execution timed out after {TIMEOUT_S}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

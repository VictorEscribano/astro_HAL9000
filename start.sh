#!/bin/bash
# AstroAgent — start LLM backend (per .env) + FastAPI + Vite dev servers.
#
# Reads LLM_BACKEND from .env to decide what to bring up:
#   - "ollama"   → assume `ollama serve` runs as a systemd service.
#                  Just sanity-check that it answers on :11434.
#   - "ik_llama" → if nothing's listening on :8080, launch
#                  scripts/run_ik_llama.sh in the background and wait
#                  for the HTTP server to come up before starting HAL.
#
# Stopping the script (Ctrl+C) tears down everything *this* script
# started, including the LLM server if we launched it.  Pre-existing
# servers are left alone.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔭 Starting AstroAgent..."

# ── Read LLM_BACKEND from .env (default: ollama) ─────────────────────────────
LLM_BACKEND="ollama"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    val=$(grep -E '^[[:space:]]*LLM_BACKEND[[:space:]]*=' "$SCRIPT_DIR/.env" \
          | tail -n1 | cut -d= -f2- | tr -d ' "'"'")
    [[ -n "$val" ]] && LLM_BACKEND="$val"
fi
echo "  LLM backend: $LLM_BACKEND"

# Helper: returns 0 if a TCP port already has something listening.
port_in_use() {
    (echo > "/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
}

LLM_PID=""

case "$LLM_BACKEND" in
    ik_llama)
        if port_in_use 8080; then
            echo "  llama-server: already running on :8080 (reusing)"
        else
            echo "  llama-server: launching in background (logs → /tmp/ik_llama.log)"
            "$SCRIPT_DIR/scripts/run_ik_llama.sh" > /tmp/ik_llama.log 2>&1 &
            LLM_PID=$!
            echo "  llama-server PID: $LLM_PID"
            # Wait up to ~3 minutes for the model to finish loading.  Big
            # MoE GGUFs (Qwen3-30B-A3B is 16 GB) take ~10-30 s to map and
            # populate KV.  Bail out early if the process dies first.
            for i in $(seq 1 90); do
                if ! kill -0 "$LLM_PID" 2>/dev/null; then
                    echo "  llama-server: died during startup, see /tmp/ik_llama.log" >&2
                    exit 1
                fi
                if port_in_use 8080; then
                    echo "  llama-server: ready on :8080 (after ${i}s)"
                    break
                fi
                sleep 2
            done
            if ! port_in_use 8080; then
                echo "  llama-server: never came up on :8080 — see /tmp/ik_llama.log" >&2
                kill "$LLM_PID" 2>/dev/null
                exit 1
            fi
        fi
        ;;
    ollama)
        if port_in_use 11434; then
            echo "  ollama: detected on :11434"
        else
            echo "  ollama: NOT running on :11434 — start it with 'ollama serve' or" >&2
            echo "          'sudo systemctl start ollama' before this script." >&2
        fi
        ;;
    *)
        echo "  warning: unknown LLM_BACKEND='$LLM_BACKEND' (expected 'ollama' or 'ik_llama')" >&2
        ;;
esac

# ── Backend ──────────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR/backend"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID (http://localhost:8000)"

# ── Frontend ─────────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR/frontend"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID (http://localhost:5173)"

echo ""
echo "  Open:    http://localhost:5173"
echo "  API:     http://localhost:8000/docs"
[[ "$LLM_BACKEND" == "ik_llama" ]] && echo "  LLM log: tail -f /tmp/ik_llama.log"
echo ""
echo "  Press Ctrl+C to stop everything launched by this script."

# Tear down everything we started; leave pre-existing services alone.
cleanup() {
    [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null
    [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null
    [[ -n "$LLM_PID"      ]] && kill "$LLM_PID"      2>/dev/null
    exit
}
trap cleanup INT TERM
wait

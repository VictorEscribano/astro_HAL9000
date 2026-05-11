#!/usr/bin/env bash
# Launch ik_llama.cpp's llama-server on http://127.0.0.1:8080 with the
# OpenAI-compatible API enabled, GPU-offloaded as much as fits, and a
# context size large enough for HAL's system prompt + memory + history.
#
# Override any of the env vars below to tweak.  Defaults assume:
#   - You ran scripts/setup_ik_llama.sh into $HOME/ik_llama.cpp
#   - You dropped a GGUF model into $HOME/ik_llama.cpp/models/
#   - You're on an 8 GB NVIDIA card (RTX 3070 Ti) — full GPU offload of a 7B
#     IQ4_K model fits with ~3 GB headroom for the KV cache at 8k context.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/ik_llama.cpp}"
SERVER_BIN="${SERVER_BIN:-$REPO_DIR/build/bin/llama-server}"
MODELS_DIR="${MODELS_DIR:-$REPO_DIR/models}"

# If MODEL is not set, pick the first .gguf file we find.
if [[ -z "${MODEL:-}" ]]; then
    MODEL="$(find "$MODELS_DIR" -maxdepth 2 -type f -name '*.gguf' | sort | head -n1 || true)"
fi
if [[ -z "$MODEL" || ! -f "$MODEL" ]]; then
    echo "ERROR: no GGUF model found in $MODELS_DIR" >&2
    echo "Set MODEL=/path/to/model.gguf or drop one into $MODELS_DIR" >&2
    exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
NGL="${NGL:-999}"           # layers to offload to GPU (-1 = all; 999 also "all")
CTX="${CTX:-8192}"          # context window (must >= HAL prompt + history)
THREADS="${THREADS:-$(nproc)}"
PARALLEL="${PARALLEL:-1}"   # parallel slots (HAL uses 1; bump if you serve > 1 client)

echo "=== ik_llama.cpp llama-server ==="
echo "  binary  : $SERVER_BIN"
echo "  model   : $MODEL"
echo "  bind    : $HOST:$PORT"
echo "  ngl     : $NGL"
echo "  ctx     : $CTX"
echo "  threads : $THREADS"

exec "$SERVER_BIN" \
    --model "$MODEL" \
    --host "$HOST" \
    --port "$PORT" \
    --ctx-size "$CTX" \
    --n-gpu-layers "$NGL" \
    --threads "$THREADS" \
    --parallel "$PARALLEL" \
    --jinja

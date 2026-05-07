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

# Resolve which GGUF file to load.
#
#   MODEL unset      → auto-pick the LARGEST real .gguf in $MODELS_DIR
#   MODEL=/abs/path  → use exactly that file
#   MODEL=substring  → first .gguf in $MODELS_DIR whose basename matches
#                      (case-insensitive).  Lets you do `MODEL=8b ./run...`
#                      to switch between Qwen3-8B and Qwen3-30B-A3B without
#                      typing the whole filename.
#
# We always exclude the small `ggml-vocab-*.gguf` files that the
# ik_llama.cpp source tree ships under models/ for unit tests — they're
# vocab-only and would crash the server.
resolve_model() {
    local hint="$1"
    if [[ -z "$hint" ]]; then
        # Auto: largest real GGUF
        find "$MODELS_DIR" -maxdepth 2 -type f -name '*.gguf' \
             ! -name 'ggml-vocab-*' -size +100M -printf '%s %p\n' 2>/dev/null \
        | sort -rn | head -n1 | cut -d' ' -f2-
        return
    fi
    if [[ -f "$hint" ]]; then
        echo "$hint"
        return
    fi
    # Substring match (case-insensitive) inside the models dir.
    find "$MODELS_DIR" -maxdepth 2 -type f -name '*.gguf' \
         ! -name 'ggml-vocab-*' -size +100M -iname "*${hint}*.gguf" 2>/dev/null \
    | head -n1
}

resolved="$(resolve_model "${MODEL:-}")"
if [[ -z "$resolved" || ! -f "$resolved" ]]; then
    echo "ERROR: could not resolve a GGUF for MODEL='${MODEL:-<auto>}'." >&2
    echo "Available models in $MODELS_DIR:" >&2
    find "$MODELS_DIR" -maxdepth 2 -type f -name '*.gguf' ! -name 'ggml-vocab-*' \
        -size +100M -printf '  %p (%s bytes)\n' 2>/dev/null | sort >&2 \
        || echo "  (none)" >&2
    exit 1
fi
MODEL="$resolved"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
NGL="${NGL:-999}"           # layers to offload to GPU (-1 = all; 999 also "all")
CTX="${CTX:-8192}"          # context window (must >= HAL prompt + history)
THREADS="${THREADS:-$(nproc)}"
PARALLEL="${PARALLEL:-1}"   # parallel slots (HAL uses 1; bump if you serve > 1 client)

# MoE expert-offload: when set to "1" (default), Mixture-of-Experts weights
# are split between CPU (RAM) and GPU (VRAM).  The dense layers
# (attention, embeddings, lm_head, KV cache) ALWAYS go to GPU.
#
# `MOE_CPU_FROM` (default: 14) is the first layer index whose expert
# weights get pushed to CPU/RAM.  Layers below that keep their experts on
# GPU.  Tunable by VRAM budget:
#   - On an 8 GB card running Qwen3-30B-A3B (48 layers, ~309 MB experts/layer)
#     with 8k context, MOE_CPU_FROM=14 puts ~4.3 GB of experts on GPU and
#     ~10.5 GB on RAM, leaving ~1.5 GB VRAM headroom.  Roughly 25-30 %
#     speedup over MOE_CPU_FROM=0 (all experts on CPU).
#   - Set MOE_CPU_FROM=0 if you see CUDA OOM at startup; that's the
#     conservative all-CPU-experts setting.
#   - Set MOE_CPU_FROM=20+ if you have a larger card or want to push it.
#
# Safe to leave on for dense (non-MoE) models too: the tensor-name regex
# below matches nothing on dense weights, so the flag is a no-op for them.
# Set MOE_CPU=0 explicitly to disable.
MOE_CPU="${MOE_CPU:-1}"
MOE_CPU_FROM="${MOE_CPU_FROM:-14}"

# Qwen3 (and other "thinking" models) emit a <think>…</think> block before
# every reply.  Useful for one-shot reasoning, but *deadly* for HAL:
# each turn issues 4 LLM calls (classify → plan → extract args → respond)
# and 200-300 thinking tokens per call adds ~30-40 s of latency.  Disable
# globally by default; set THINKING=1 to opt back in.
THINKING="${THINKING:-0}"

echo "=== ik_llama.cpp llama-server ==="
echo "  binary  : $SERVER_BIN"
echo "  model   : $MODEL"
echo "  bind    : $HOST:$PORT"
echo "  ngl     : $NGL"
echo "  ctx     : $CTX"
echo "  threads : $THREADS"

ARGS=(
    --model "$MODEL"
    --host "$HOST"
    --port "$PORT"
    --ctx-size "$CTX"
    --n-gpu-layers "$NGL"
    --threads "$THREADS"
    --parallel "$PARALLEL"
    --jinja
)

if [[ "$THINKING" != "1" ]]; then
    echo "  thinking: OFF  (Qwen3 reasoning <think>…</think> disabled in chat template)"
    ARGS+=(--chat-template-kwargs '{"enable_thinking":false}')
fi

if [[ "$MOE_CPU" == "1" ]]; then
    if [[ "$MOE_CPU_FROM" -le 0 ]]; then
        echo "  moe-cpu : ON (ALL *.ffn_*_exps tensors → CPU)"
        # Tensor-name regex: keep ALL expert FFN weights on CPU.  Matches
        # Qwen3-MoE / DeepSeek MoE / Mixtral naming conventions.
        ARGS+=(-ot "blk\\.[0-9]+\\.ffn_(down|gate|up)_exps\\.=CPU")
    else
        # Build a regex that matches only layers >= $MOE_CPU_FROM.  Lower
        # layers' experts stay on GPU (faster compute).  Overspecify the
        # range up to layer 199 so the same expression works on any current
        # MoE model regardless of its actual depth.
        layers_re="$(seq "$MOE_CPU_FROM" 199 | tr '\n' '|' | sed 's/|$//')"
        echo "  moe-cpu : ON (layers ${MOE_CPU_FROM}+ *.ffn_*_exps tensors → CPU; layers 0..$((MOE_CPU_FROM-1)) stay on GPU)"
        ARGS+=(-ot "blk\\.(${layers_re})\\.ffn_(down|gate|up)_exps\\.=CPU")
    fi
fi

exec "$SERVER_BIN" "${ARGS[@]}"

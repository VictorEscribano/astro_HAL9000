#!/usr/bin/env bash
# setup_cpu_llm.sh — download and configure a CPU-optimised LLM for HAL9000
#
# Usage:
#   ./scripts/setup_cpu_llm.sh [profile]
#
# Profiles (from model_registry.py):
#   phi4mini-onnx       — fastest (ONNX INT4, ~20 tok/s, 2.5 GB RAM)
#   qwen3-1.7b          — ultra-fast GGUF (~18 tok/s, 1.5 GB RAM)
#   qwen3-4b            — balanced GGUF with thinking mode (~10 tok/s, 2.8 GB RAM) [DEFAULT]
#   astrosage-8b        — astronomy specialist, GPT-4o parity (~6 tok/s, 5 GB RAM)
#   qwen3-30b-moe       — MoE: 30B params, 3B active (~8 tok/s, 8.5 GB RAM)
#   qwen3-30b-moe-abliterated — same, uncensored variant
#   qwen3-8b            — dense 8B with thinking mode (~5.5 tok/s, 5 GB RAM)
#
# Requirements: pip install huggingface-hub

set -euo pipefail

PROFILE="${1:-qwen3-4b}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="$REPO_ROOT/models"
mkdir -p "$MODELS_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  HAL9000 CPU LLM Setup"
echo "  Profile: $PROFILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Check huggingface-hub ──────────────────────────────────────────────────
if ! python3 -c "import huggingface_hub" 2>/dev/null; then
    echo "[!] huggingface-hub not found. Installing..."
    pip install huggingface-hub
fi

HF="python3 -m huggingface_hub.cli.cli download"

case "$PROFILE" in

phi4mini-onnx)
    echo "[*] Downloading Phi-4-mini ONNX INT4 (Microsoft)..."
    echo "    ~2.5 GB · backend: onnx · ~20 tok/s on i7/Ryzen 7"
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    'microsoft/Phi-4-mini-instruct-onnx',
    allow_patterns=['cpu-int4-rtn-block-32/*'],
    local_dir='$MODELS_DIR/phi4mini-onnx',
)
print('[+] Done → $MODELS_DIR/phi4mini-onnx/cpu-int4-rtn-block-32')"

    pip install onnxruntime-genai transformers

    ENV_BLOCK="LLM_BACKEND=onnx
ONNX_MODEL_PATH=$MODELS_DIR/phi4mini-onnx/cpu-int4-rtn-block-32"
    ;;

qwen3-1.7b)
    echo "[*] Downloading Qwen3-1.7B Q4_K_M..."
    echo "    ~1.2 GB · backend: llamacpp · ~18 tok/s"
    hf download Qwen/Qwen3-1.7B-GGUF \
        qwen3-1.7b-q4_k_m.gguf \
        --local-dir "$MODELS_DIR"

    pip install "llama-cpp-python[server]"

    ENV_BLOCK="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODELS_DIR/qwen3-1.7b-q4_k_m.gguf
LLAMACPP_N_CTX=32768"
    ;;

qwen3-4b)
    echo "[*] Downloading Qwen3-4B Q4_K_M (recommended default)..."
    echo "    ~2.5 GB · backend: llamacpp · ~10 tok/s · thinking mode"
    hf download Qwen/Qwen3-4B-GGUF \
        qwen3-4b-q4_k_m.gguf \
        --local-dir "$MODELS_DIR"

    pip install "llama-cpp-python[server]"

    ENV_BLOCK="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODELS_DIR/qwen3-4b-q4_k_m.gguf
LLAMACPP_N_CTX=32768"
    ;;

astrosage-8b)
    echo "[*] Downloading AstroSage-LLaMA-3.1-8B Q4_K_M..."
    echo "    ~5 GB · backend: llamacpp · ~6 tok/s"
    echo "    → GPT-4o parity on AstroMLab-1 astronomy benchmark"
    hf download AstroMLab/AstroSage-LLaMA-3.1-8B-GGUF \
        AstroSage-LLaMA-3.1-8B-Q4_K_M.gguf \
        --local-dir "$MODELS_DIR"

    pip install "llama-cpp-python[server]"

    ENV_BLOCK="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODELS_DIR/AstroSage-LLaMA-3.1-8B-Q4_K_M.gguf
LLAMACPP_N_CTX=131072"
    ;;

qwen3-30b-moe)
    echo "[*] Downloading Qwen3-30B-A3B Q4_K_M (MoE)..."
    echo "    ~8.5 GB · backend: llamacpp · ~8 tok/s"
    echo "    → 30B total params, 3B active — quality of 30B at 3B speed"
    hf download Qwen/Qwen3-30B-A3B-GGUF \
        qwen3-30b-a3b-q4_k_m.gguf \
        --local-dir "$MODELS_DIR"

    pip install "llama-cpp-python[server]"

    ENV_BLOCK="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODELS_DIR/qwen3-30b-a3b-q4_k_m.gguf
LLAMACPP_N_CTX=131072"
    ;;

qwen3-30b-moe-abliterated)
    echo "[*] Downloading Qwen3-30B-A3B abliterated Q4_K_M (huihui-ai)..."
    echo "    ~8.5 GB · backend: llamacpp · ~8 tok/s"
    echo "    → Uncensored MoE variant from huihui-ai"
    hf download huihui-ai/Qwen3-30B-A3B-abliterated-GGUF \
        "Qwen3-30B-A3B-abliterated-Q4_K_M.gguf" \
        --local-dir "$MODELS_DIR"

    pip install "llama-cpp-python[server]"

    ENV_BLOCK="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODELS_DIR/Qwen3-30B-A3B-abliterated-Q4_K_M.gguf
LLAMACPP_N_CTX=131072"
    ;;

qwen3-8b)
    echo "[*] Downloading Qwen3-8B Q4_K_M..."
    echo "    ~5 GB · backend: llamacpp · ~5.5 tok/s · thinking mode"
    hf download Qwen/Qwen3-8B-GGUF \
        qwen3-8b-q4_k_m.gguf \
        --local-dir "$MODELS_DIR"

    pip install "llama-cpp-python[server]"

    ENV_BLOCK="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODELS_DIR/qwen3-8b-q4_k_m.gguf
LLAMACPP_N_CTX=131072"
    ;;

*)
    echo "[!] Unknown profile: $PROFILE"
    echo "    Valid: phi4mini-onnx qwen3-1.7b qwen3-4b astrosage-8b qwen3-30b-moe qwen3-30b-moe-abliterated qwen3-8b"
    exit 1
    ;;
esac

# ── Write / patch .env ───────────────────────────────────────────────────────
ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    # Remove old LLM backend lines
    sed -i '/^LLM_BACKEND=/d;/^LLAMACPP_/d;/^ONNX_/d;/^MODEL_PROFILE=/d' "$ENV_FILE"
    echo "" >> "$ENV_FILE"
    echo "# CPU LLM (set by setup_cpu_llm.sh — profile: $PROFILE)" >> "$ENV_FILE"
    echo "$ENV_BLOCK" >> "$ENV_FILE"
else
    cp "$REPO_ROOT/.env.example" "$ENV_FILE"
    echo "" >> "$ENV_FILE"
    echo "# CPU LLM (set by setup_cpu_llm.sh — profile: $PROFILE)" >> "$ENV_FILE"
    echo "$ENV_BLOCK" >> "$ENV_FILE"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!  Profile '$PROFILE' configured."
echo ""
echo "  .env updated:"
echo "$ENV_BLOCK" | sed 's/^/    /'
echo ""
echo "  Start the observatory:"
echo "    cd $REPO_ROOT && ./start.sh"
echo ""
echo "  Benchmark this model:"
echo "    python3 scripts/benchmark_llm.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

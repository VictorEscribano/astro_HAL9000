#!/usr/bin/env bash
# Build ik_llama.cpp with CUDA support for the RTX 3070 Ti (sm_86 / Ampere).
#
# After this script finishes you'll have:
#   ~/ik_llama.cpp/build/bin/llama-server  ← OpenAI-compat HTTP server
#   ~/ik_llama.cpp/models/                 ← drop GGUF files here
#
# Then run scripts/run_ik_llama.sh to start the server, and set
# LLM_BACKEND=ik_llama in .env to make HAL talk to it.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/ik_llama.cpp}"
JOBS="${JOBS:-$(nproc)}"
WITH_CUDA="${WITH_CUDA:-1}"   # set to 0 for a CPU-only build
CUDA_ARCH="${CUDA_ARCH:-86}"  # 86 = Ampere (RTX 3070/3080/3090); 89 = Ada (4090); 80 = A100

echo "=== ik_llama.cpp setup ==="
echo "  repo dir : $REPO_DIR"
echo "  jobs     : $JOBS"
echo "  cuda     : $WITH_CUDA  (arch sm_${CUDA_ARCH})"

# 1. Build prereqs.  Skip if not on apt; user can install manually.
if command -v apt-get >/dev/null 2>&1; then
    echo "--- installing build deps (sudo apt-get) ---"
    sudo apt-get update
    sudo apt-get install -y build-essential git cmake curl libcurl4-openssl-dev libgomp1
fi

# 2. Clone or update the fork.
if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "--- cloning ik_llama.cpp into $REPO_DIR ---"
    git clone https://github.com/ikawrakow/ik_llama.cpp "$REPO_DIR"
else
    echo "--- updating ik_llama.cpp in $REPO_DIR ---"
    git -C "$REPO_DIR" fetch --all
    git -C "$REPO_DIR" pull --ff-only
fi

# 3. Configure + build.
cd "$REPO_DIR"
CMAKE_FLAGS=(-B build -DGGML_NATIVE=ON -DBUILD_SHARED_LIBS=OFF)
if [[ "$WITH_CUDA" == "1" ]]; then
    CMAKE_FLAGS+=(-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH")
fi

echo "--- cmake configure ---"
cmake "${CMAKE_FLAGS[@]}"

echo "--- cmake build ($JOBS jobs) ---"
cmake --build build --config Release -j"$JOBS" --target llama-server

mkdir -p "$REPO_DIR/models"

echo
echo "=== Done ==="
echo "Server binary: $REPO_DIR/build/bin/llama-server"
echo "Drop a GGUF model into: $REPO_DIR/models/"
echo
echo "Suggested model for the RTX 3070 Ti (8 GB VRAM):"
echo "  Qwen2.5-7B-Instruct, IQ4_K (~4.4 GB) — great speed / quality trade-off."
echo "  Example download:"
echo "    cd $REPO_DIR/models"
echo "    curl -LO https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-IQ4_XS.gguf"
echo
echo "Then start the server with: scripts/run_ik_llama.sh"

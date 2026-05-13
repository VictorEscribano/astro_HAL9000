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
    # Locate nvcc.  Ubuntu's CUDA toolkit installs it under
    # /usr/local/cuda/bin or /usr/local/cuda-<ver>/bin, but those bin dirs
    # are not on PATH by default — so CMake's `enable_language(CUDA)` fails
    # with "No CMAKE_CUDA_COMPILER could be found" even though the headers
    # are detected.  Find nvcc explicitly and pass it via CMAKE_CUDA_COMPILER.
    NVCC_BIN="${NVCC_BIN:-$(command -v nvcc || true)}"
    if [[ -z "$NVCC_BIN" ]]; then
        for cand in /usr/local/cuda/bin/nvcc \
                    /usr/local/cuda-*/bin/nvcc \
                    /opt/cuda/bin/nvcc; do
            if [[ -x "$cand" ]]; then NVCC_BIN="$cand"; break; fi
        done
    fi
    if [[ -z "$NVCC_BIN" || ! -x "$NVCC_BIN" ]]; then
        echo "ERROR: WITH_CUDA=1 but nvcc was not found." >&2
        echo "  Install the CUDA Toolkit (apt install nvidia-cuda-toolkit on Ubuntu)" >&2
        echo "  or point NVCC_BIN at it: NVCC_BIN=/usr/local/cuda-XX.Y/bin/nvcc $0" >&2
        echo "  Or skip CUDA: WITH_CUDA=0 $0" >&2
        exit 1
    fi
    echo "  nvcc     : $NVCC_BIN ($($NVCC_BIN --version | tail -1))"
    # Put the CUDA bin on PATH for the build subprocesses too.
    CUDA_BIN_DIR="$(dirname "$NVCC_BIN")"
    export PATH="$CUDA_BIN_DIR:$PATH"
    CMAKE_FLAGS+=(
        -DGGML_CUDA=ON
        -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH"
        -DCMAKE_CUDA_COMPILER="$NVCC_BIN"
    )
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

#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║  HAL9000 — CPU Install Script                                    ║
# ║  Ubuntu 24.04 · Python 3.12 · Node 18 · AVX2                    ║
# ║  Usage:  ./install.sh [model-profile]                            ║
# ║  Profiles: qwen3-4b (default) | astrosage-8b | qwen3-1.7b       ║
# ║            phi4mini-onnx | qwen3-8b | qwen3-30b-moe              ║
# ╚══════════════════════════════════════════════════════════════════╝

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✔${NC}  $*"; }
info() { echo -e "${CYAN}●${NC}  $*"; }
warn() { echo -e "${YELLOW}▲${NC}  $*"; }
err()  { echo -e "${RED}✘${NC}  $*" >&2; }
step() { echo -e "\n${BOLD}${CYAN}── $* ${NC}${DIM}──────────────────────────────────────${NC}"; }
die()  { err "$*"; exit 1; }

PROFILE="${1:-qwen3-4b}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
MODELS_DIR="$SCRIPT_DIR/models"

# ── Detect CPU capabilities ────────────────────────────────────────
CPU_FLAGS=$(cat /proc/cpuinfo)
HAS_AVX2=$(echo "$CPU_FLAGS" | grep -c "avx2" || true)
HAS_AVX512=$(echo "$CPU_FLAGS" | grep -c "avx512f" || true)
NCORES=$(nproc)
RAM_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         HAL9000 — Instalación CPU                ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  CPU cores : ${BOLD}$NCORES${NC}"
echo -e "  RAM       : ${BOLD}${RAM_GB}GB${NC}"
echo -e "  AVX2      : $([ "$HAS_AVX2" -gt 0 ] && echo "${GREEN}sí${NC}" || echo "${YELLOW}no${NC}")"
echo -e "  AVX-512   : $([ "$HAS_AVX512" -gt 0 ] && echo "${GREEN}sí${NC}" || echo "${DIM}no${NC}")"
echo -e "  Perfil    : ${BOLD}$PROFILE${NC}"
echo ""

# ── Pareto table for reference ─────────────────────────────────────
echo -e "${DIM}  Perfiles disponibles (Pareto velocidad/calidad en CPU):${NC}"
echo -e "${DIM}  ─────────────────────────────────────────────────────────────${NC}"
echo -e "${DIM}  Perfil                    RAM    tok/s   Notas${NC}"
echo -e "${DIM}  phi4mini-onnx             2.5G   ~20/s   Microsoft Phi-4 INT4 (más rápido)${NC}"
echo -e "${DIM}  qwen3-1.7b                1.5G   ~18/s   Ultra-rápido, thinking mode${NC}"
echo -e "${DIM}  qwen3-4b                  2.8G   ~10/s   Equilibrado [POR DEFECTO]${NC}"
echo -e "${DIM}  astrosage-8b              5.0G    ~6/s   Especialista astronomía (≈GPT-4o)${NC}"
echo -e "${DIM}  qwen3-8b                  5.0G   ~5.5/s  Dense 8B, thinking mode${NC}"
echo -e "${DIM}  qwen3-30b-moe             8.5G    ~8/s   MoE: calidad 30B, velocidad 3B${NC}"
echo -e "${DIM}  qwen3-30b-moe-abliterated 8.5G    ~8/s   Igual, sin censura (huihui-ai)${NC}"
echo -e "${DIM}  ─────────────────────────────────────────────────────────────${NC}"
echo ""

# ── RAM check ─────────────────────────────────────────────────────
warn_if_tight() {
    local needed=$1
    if [ "$RAM_GB" -lt "$needed" ]; then
        warn "Este perfil necesita ~${needed}GB RAM y tienes ${RAM_GB}GB. Podría ser justo."
        warn "Considera qwen3-4b (2.8GB) si hay problemas de memoria."
    fi
}

# ── Step 0: System dependencies ───────────────────────────────────
step "Dependencias del sistema"

MISSING_PKGS=()
for pkg in python3-venv python3-dev build-essential cmake git curl; do
    if ! dpkg -s "$pkg" &>/dev/null 2>&1; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    info "Instalando paquetes del sistema: ${MISSING_PKGS[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y "${MISSING_PKGS[@]}"
else
    ok "Dependencias del sistema ya instaladas"
fi

# Node / npm check
if ! command -v npm &>/dev/null; then
    info "Instalando Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
ok "Node $(node --version), npm $(npm --version)"

# ── Step 1: Python venv ───────────────────────────────────────────
step "Entorno virtual Python"

if [ ! -d "$VENV" ]; then
    info "Creando venv en .venv/ ..."
    python3 -m venv "$VENV"
    ok "Venv creado"
else
    ok "Venv ya existe (.venv/)"
fi

PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

# Upgrade pip silencing ROS conflict noise (launch-ros requires pyyaml but
# it's a system-level ROS package — irrelevant inside the venv).
"$PIP" install --quiet --upgrade pip wheel setuptools pyyaml

# ── Step 2: Backend dependencies ─────────────────────────────────
step "Dependencias del backend (requirements.txt)"

info "Instalando dependencias base..."
"$PIP" install --quiet --no-warn-conflicts -r "$SCRIPT_DIR/backend/requirements.txt"
ok "Backend base instalado"

# ── Step 3: CPU LLM backend ───────────────────────────────────────
step "Backend LLM para CPU — perfil: $PROFILE"

if [[ "$PROFILE" == "phi4mini-onnx" ]]; then
    warn_if_tight 3
    info "Instalando onnxruntime-genai + transformers..."
    "$PIP" install --quiet onnxruntime-genai transformers
    ok "onnxruntime-genai instalado"

else
    # All other profiles use llama-cpp-python
    warn_if_tight 3

    info "Compilando llama-cpp-python con optimizaciones AVX2..."
    info "(Esto puede tardar 3-8 minutos la primera vez)"

    # Build flags based on CPU capabilities
    CMAKE_FLAGS="-DGGML_NATIVE=ON"
    if [ "$HAS_AVX2" -gt 0 ]; then
        CMAKE_FLAGS="$CMAKE_FLAGS -DGGML_AVX2=ON"
        info "→ AVX2 activado"
    fi
    if [ "$HAS_AVX512" -gt 0 ]; then
        CMAKE_FLAGS="$CMAKE_FLAGS -DGGML_AVX512=ON"
        info "→ AVX-512 activado"
    fi

    # Number of parallel build jobs (leave 1 core free)
    MAKE_JOBS=$(( NCORES > 1 ? NCORES - 1 : 1 ))

    CMAKE_ARGS="$CMAKE_FLAGS" \
    MAKEFLAGS="-j$MAKE_JOBS" \
    "$PIP" install \
        --quiet \
        --no-binary llama-cpp-python \
        "llama-cpp-python[server]>=0.3.0"

    ok "llama-cpp-python compilado con AVX2 (${MAKE_JOBS} cores)"
fi

# Web search tools
info "Instalando herramientas de búsqueda web..."
"$PIP" install --quiet "duckduckgo-search>=6.0" "wikipedia>=1.4.0"
ok "duckduckgo-search + wikipedia instalados"

# Model downloader
"$PIP" install --quiet huggingface-hub
ok "huggingface-hub instalado"

# ── Step 4: Download model ─────────────────────────────────────────
step "Descarga del modelo LLM"

mkdir -p "$MODELS_DIR"
HF_CLI="$VENV/bin/hf"

case "$PROFILE" in

phi4mini-onnx)
    MODEL_PATH="$MODELS_DIR/phi4mini-onnx/cpu-int4-rtn-block-32"
    if [ -d "$MODEL_PATH" ]; then
        ok "Modelo ya descargado: $MODEL_PATH"
    else
        info "Descargando Phi-4-mini ONNX INT4 (~2.5 GB)..."
        "$PY" -c "
from huggingface_hub import snapshot_download
snapshot_download(
    'microsoft/Phi-4-mini-instruct-onnx',
    allow_patterns=['cpu-int4-rtn-block-32/*'],
    local_dir='$MODELS_DIR/phi4mini-onnx',
)
print('Descarga completa')
"
        ok "Phi-4-mini ONNX descargado"
    fi
    ENV_LLM="LLM_BACKEND=onnx
ONNX_MODEL_PATH=$MODEL_PATH"
    ;;

qwen3-1.7b)
    # Repo only publishes Q8_0 (no Q4_K_M available for this size)
    MODEL_FILE="$MODELS_DIR/Qwen3-1.7B-Q8_0.gguf"
    warn_if_tight 2
    if [ -f "$MODEL_FILE" ]; then
        ok "Modelo ya descargado: $MODEL_FILE"
    else
        info "Descargando Qwen3-1.7B Q8_0 (~1.8 GB)..."
        "$PY" -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Qwen/Qwen3-1.7B-GGUF', 'Qwen3-1.7B-Q8_0.gguf', local_dir='$MODELS_DIR')
print('Descarga completa')
"
        ok "Qwen3-1.7B descargado"
    fi
    ENV_LLM="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODEL_FILE
LLAMACPP_N_CTX=2048"
    ;;

qwen3-4b)
    MODEL_FILE="$MODELS_DIR/Qwen3-4B-Q4_K_M.gguf"
    if [ -f "$MODEL_FILE" ]; then
        ok "Modelo ya descargado: $MODEL_FILE"
    else
        info "Descargando Qwen3-4B Q4_K_M (~2.5 GB)..."
        "$PY" -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Qwen/Qwen3-4B-GGUF', 'Qwen3-4B-Q4_K_M.gguf', local_dir='$MODELS_DIR')
print('Descarga completa')
"
        ok "Qwen3-4B descargado"
    fi
    ENV_LLM="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODEL_FILE
LLAMACPP_N_CTX=2048"
    ;;

astrosage-8b)
    # Repo requires HuggingFace login (gated model)
    MODEL_FILE="$MODELS_DIR/AstroSage-LLaMA-3.1-8B-Q4_K_M.gguf"
    warn_if_tight 6
    if [ -f "$MODEL_FILE" ]; then
        ok "Modelo ya descargado: $MODEL_FILE"
    else
        if [ -z "${HF_TOKEN:-}" ]; then
            warn "AstroSage requiere autenticación en HuggingFace."
            warn "Obtén tu token en https://huggingface.co/settings/tokens y ejecútalo así:"
            warn "  HF_TOKEN=hf_xxx ./install.sh astrosage-8b"
            die "Token HF_TOKEN no encontrado. Abortando."
        fi
        info "Descargando AstroSage-8B Q4_K_M (~5 GB)..."
        info "→ Especialista en astronomía (paridad GPT-4o en AstroMLab-1)"
        HF_TOKEN="${HF_TOKEN:-}" "$PY" -c "
import os
from huggingface_hub import hf_hub_download
hf_hub_download('AstroMLab/AstroSage-LLaMA-3.1-8B-GGUF', 'AstroSage-LLaMA-3.1-8B-Q4_K_M.gguf',
    local_dir='$MODELS_DIR', token=os.environ.get('HF_TOKEN'))
print('Descarga completa')
"
        ok "AstroSage-8B descargado"
    fi
    ENV_LLM="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODEL_FILE
LLAMACPP_N_CTX=2048"
    ;;

qwen3-8b)
    MODEL_FILE="$MODELS_DIR/Qwen3-8B-Q4_K_M.gguf"
    warn_if_tight 6
    if [ -f "$MODEL_FILE" ]; then
        ok "Modelo ya descargado: $MODEL_FILE"
    else
        info "Descargando Qwen3-8B Q4_K_M (~5 GB)..."
        "$PY" -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Qwen/Qwen3-8B-GGUF', 'Qwen3-8B-Q4_K_M.gguf', local_dir='$MODELS_DIR')
print('Descarga completa')
"
        ok "Qwen3-8B descargado"
    fi
    ENV_LLM="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODEL_FILE
LLAMACPP_N_CTX=2048"
    ;;

qwen3-30b-moe)
    MODEL_FILE="$MODELS_DIR/Qwen3-30B-A3B-Q4_K_M.gguf"
    warn_if_tight 10
    if [ -f "$MODEL_FILE" ]; then
        ok "Modelo ya descargado: $MODEL_FILE"
    else
        info "Descargando Qwen3-30B-A3B Q4_K_M (~8.5 GB)..."
        info "→ MoE: 30B parámetros totales, 3B activos por token"
        "$PY" -c "
from huggingface_hub import hf_hub_download
hf_hub_download('Qwen/Qwen3-30B-A3B-GGUF', 'Qwen3-30B-A3B-Q4_K_M.gguf', local_dir='$MODELS_DIR')
print('Descarga completa')
"
        ok "Qwen3-30B-A3B descargado"
    fi
    ENV_LLM="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODEL_FILE
LLAMACPP_N_CTX=2048"
    ;;

qwen3-30b-moe-abliterated)
    # huihui-ai repos require HuggingFace login
    MODEL_FILE="$MODELS_DIR/Qwen3-30B-A3B-abliterated-Q4_K_M.gguf"
    warn_if_tight 10
    if [ -f "$MODEL_FILE" ]; then
        ok "Modelo ya descargado: $MODEL_FILE"
    else
        if [ -z "${HF_TOKEN:-}" ]; then
            warn "huihui-ai requiere autenticación en HuggingFace."
            warn "Obtén tu token en https://huggingface.co/settings/tokens y ejecútalo así:"
            warn "  HF_TOKEN=hf_xxx ./install.sh qwen3-30b-moe-abliterated"
            die "Token HF_TOKEN no encontrado. Abortando."
        fi
        info "Descargando Qwen3-30B-A3B abliterated Q4_K_M (~8.5 GB, huihui-ai)..."
        HF_TOKEN="${HF_TOKEN:-}" "$PY" -c "
import os
from huggingface_hub import hf_hub_download
hf_hub_download('huihui-ai/Qwen3-30B-A3B-abliterated-GGUF', 'Qwen3-30B-A3B-abliterated-Q4_K_M.gguf',
    local_dir='$MODELS_DIR', token=os.environ.get('HF_TOKEN'))
print('Descarga completa')
"
        ok "Qwen3-30B-A3B abliterated descargado"
    fi
    ENV_LLM="LLM_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=$MODEL_FILE
LLAMACPP_N_CTX=2048"
    ;;

*)
    die "Perfil desconocido: '$PROFILE'. Usa: phi4mini-onnx qwen3-1.7b qwen3-4b astrosage-8b qwen3-8b qwen3-30b-moe qwen3-30b-moe-abliterated"
    ;;
esac

# ── Step 5: Catálogos de datos ────────────────────────────────────
step "Catálogos de datos astronómicos"

mkdir -p "$SCRIPT_DIR/backend/data"
NGC_CSV="$SCRIPT_DIR/backend/data/ngc_catalog.csv"
if [ -f "$NGC_CSV" ] && [ "$(wc -l < "$NGC_CSV")" -gt 1000 ]; then
    ok "Catálogo NGC/IC ya presente ($(wc -l < "$NGC_CSV") objetos)"
else
    info "Descargando catálogo OpenNGC (~3.7 MB, 13969 objetos NGC/IC)..."
    wget -q --show-progress \
        "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/NGC.csv" \
        -O "$NGC_CSV"
    ok "Catálogo NGC descargado: $(( $(wc -l < "$NGC_CSV") - 1 )) objetos"
fi

# ── Step 6: Frontend ──────────────────────────────────────────────
step "Frontend (npm install)"

cd "$SCRIPT_DIR/frontend"
if [ -d node_modules ] && [ -f node_modules/.package-lock.json ]; then
    ok "node_modules ya existe, verificando..."
    npm install --silent 2>/dev/null || npm install
else
    info "Instalando dependencias del frontend..."
    npm install --silent
fi
ok "Frontend listo"
cd "$SCRIPT_DIR"

# ── Step 6: .env ──────────────────────────────────────────────────
step "Configuración (.env)"

ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
    info "Creado .env desde .env.example"
fi

# Remove old LLM backend lines and write new ones
sed -i '/^LLM_BACKEND=/d' "$ENV_FILE"
sed -i '/^LLAMACPP_/d' "$ENV_FILE"
sed -i '/^ONNX_/d' "$ENV_FILE"
sed -i '/^MODEL_PROFILE=/d' "$ENV_FILE"
sed -i '/^# CPU LLM/d' "$ENV_FILE"

{
    echo ""
    echo "# CPU LLM — perfil: $PROFILE (configurado por install.sh)"
    echo "$ENV_LLM"
} >> "$ENV_FILE"

ok ".env actualizado con perfil '$PROFILE'"

# ── Step 7: Update start.sh to use venv ──────────────────────────
step "Actualizando start.sh para usar el venv"

cat > "$SCRIPT_DIR/start.sh" << 'STARTEOF'
#!/usr/bin/env bash
# HAL9000 — start backend + frontend dev servers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate Python venv installed by install.sh
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
else
    echo "⚠  No se encontró .venv — ejecuta ./install.sh primero"
    exit 1
fi

echo "Starting HAL9000..."
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:5173"
echo "  API docs → http://localhost:8000/docs"
echo ""

# Backend
cd "$SCRIPT_DIR/backend"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Frontend
cd "$SCRIPT_DIR/frontend"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!

echo "  PIDs: backend=$BACKEND_PID  frontend=$FRONTEND_PID"
echo "  Ctrl+C para parar"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
STARTEOF

chmod +x "$SCRIPT_DIR/start.sh"
ok "start.sh actualizado"

# ── Final summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║   Instalación completa                           ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Perfil LLM : ${BOLD}$PROFILE${NC}"
echo -e "  Python venv: ${BOLD}.venv/${NC}"
echo -e "  Modelo     : ${BOLD}$MODELS_DIR${NC}"
echo ""
echo -e "  ${BOLD}Para arrancar HAL9000:${NC}"
echo -e "  ${CYAN}./start.sh${NC}"
echo ""
echo -e "  ${BOLD}Para cambiar de modelo:${NC}"
echo -e "  ${CYAN}./install.sh astrosage-8b${NC}     # especialista astronomía"
echo -e "  ${CYAN}./install.sh phi4mini-onnx${NC}    # más rápido (ONNX)"
echo -e "  ${CYAN}./install.sh qwen3-30b-moe${NC}    # más capaz (MoE)"
echo ""
echo -e "  ${BOLD}Para hacer benchmark:${NC}"
echo -e "  ${CYAN}./start.sh &  # arranca primero${NC}"
echo -e "  ${CYAN}.venv/bin/python scripts/benchmark_llm.py${NC}"
echo ""

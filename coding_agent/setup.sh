#!/usr/bin/env bash
# ============================================================================
#  ESIB AI Coding Agent - Setup Script (Linux / macOS)
#  FYP_26_21 | USJ Beirut | 2026
# ============================================================================
# NOTE: We do NOT use "set -e" here.  Several checks (grep, curl, docker)
#       return non-zero exit codes in normal "not-found" paths, and we want
#       to handle each one explicitly rather than abort the whole script.

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

ok()   { echo -e "${GREEN}[OK]${RESET}  $*"; }
warn() { echo -e "${YELLOW}[!]${RESET}   $*"; }
err()  { echo -e "${RED}[X]${RESET}   $*"; }
info() { echo -e "      $*"; }

echo ""
echo "======================================================================"
echo -e "  ${BOLD}ESIB AI Coding Agent - Setup${RESET}"
echo "  FYP_26_21 | USJ Beirut | 2026"
echo "======================================================================"
echo ""

# ============================================================================
#  STEP 0: Pre-flight checks
# ============================================================================

echo "[Step 0/6] Running pre-flight checks..."
echo ""

HAS_ERROR=0

# --- Python (must be 3.10+) ------------------------------------------------
PYTHON_CMD=""

# Find a Python 3.10+ interpreter: prefer python3.10, then python3, then python
for cmd in python3.10 python3.11 python3.12 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        _ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        _major=$(echo "$_ver" | cut -d. -f1)
        _minor=$(echo "$_ver" | cut -d. -f2)
        if [ "$_major" -eq 3 ] && [ "$_minor" -ge 10 ] 2>/dev/null; then
            PYTHON_CMD="$cmd"
            PY_VERSION=$("$cmd" --version 2>&1 | awk '{print $2}')
            ok "Python $PY_VERSION found ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    err "Python 3.10 or higher not found!"
    echo ""
    info "SOLUTION:"
    info "  Python 3.10+ is required (current code uses 3.10 type-hint syntax)."
    info ""
    info "  macOS:  brew install python@3.10"
    info "          Then verify:  python3.10 --version"
    info ""
    info "  Linux:  sudo apt-get install python3.10 python3.10-venv python3.10-pip"
    info "          Then verify:  python3.10 --version"
    info ""
    info "  Or download from: https://python.org/downloads"
    echo ""
    HAS_ERROR=1
fi

# --- Docker installed -------------------------------------------------------
if ! command -v docker &>/dev/null; then
    err "Docker not found!"
    echo ""
    info "SOLUTION:"
    info "  Linux:  sudo apt-get update && sudo apt-get install docker.io"
    info "          sudo systemctl start docker"
    info "          sudo usermod -aG docker \$USER   # then log out and back in"
    info "  macOS:  https://www.docker.com/products/docker-desktop"
    echo ""
    HAS_ERROR=1
else
    # --- Docker running ------------------------------------------------------
    if ! docker ps &>/dev/null; then
        err "Docker is installed but not running!"
        echo ""
        info "SOLUTION:"
        info "  Linux:  sudo systemctl start docker"
        info "  macOS:  open Docker Desktop from Applications"
        info "  Then run setup.sh again."
        echo ""
        HAS_ERROR=1
    else
        DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
        ok "Docker running (version $DOCKER_VERSION)"
    fi
fi

# --- Ollama installed -------------------------------------------------------
if ! command -v ollama &>/dev/null; then
    err "Ollama not found!"
    echo ""
    info "SOLUTION:"
    info "  Linux/macOS: curl -fsSL https://ollama.com/install.sh | sh"
    info "  macOS (DMG): https://ollama.com/download"
    info "  After installing, run:  ollama serve &"
    echo ""
    HAS_ERROR=1
else
    # --- Ollama running ------------------------------------------------------
    if ! curl -s http://localhost:11434 &>/dev/null; then
        err "Ollama is installed but not running on port 11434!"
        echo ""
        info "SOLUTION:"
        info "  Run in a separate terminal:  ollama serve"
        info "  Or in background:            nohup ollama serve > /dev/null 2>&1 &"
        info "  Then run setup.sh again."
        echo ""
        HAS_ERROR=1
    else
        ok "Ollama running on localhost:11434"
    fi
fi

# --- Disk space (warn if < 8 GB) -------------------------------------------
FREE_KB=$(df -k . 2>/dev/null | awk 'NR==2 {print $4}')
if [ -n "$FREE_KB" ]; then
    FREE_GB=$(( FREE_KB / 1024 / 1024 ))
    if [ "$FREE_GB" -lt 8 ]; then
        warn "Low disk space: ~${FREE_GB} GB free. Recommended: 8+ GB."
    else
        ok "Disk space: ~${FREE_GB} GB free"
    fi
fi

if [ "$HAS_ERROR" -ne 0 ]; then
    echo ""
    err "Pre-flight checks failed. Fix the issues above and run setup.sh again."
    echo ""
    exit 1
fi

echo ""
ok "All prerequisites satisfied!"
echo ""

# ============================================================================
#  STEP 1: Virtual environment
# ============================================================================

echo "[Step 1/6] Creating virtual environment..."
echo ""

if [ -d ".venv" ]; then
    warn "Virtual environment already exists — skipping creation"
else
    if ! "$PYTHON_CMD" -m venv .venv; then
        err "Failed to create virtual environment!"
        info "Check Python installation and available disk space."
        info "Linux: ensure python3.10-venv is installed:"
        info "  sudo apt-get install python3.10-venv"
        exit 1
    fi
    ok "Virtual environment created (.venv) using $PYTHON_CMD"
fi

# Activate for the rest of this script
# shellcheck disable=SC1091
source .venv/bin/activate

echo ""

# ============================================================================
#  STEP 2: Python dependencies
# ============================================================================

echo "[Step 2/6] Installing Python dependencies..."
echo ""

if [ ! -f "requirements.txt" ]; then
    warn "requirements.txt not found — creating minimal version"
    echo "pyyaml>=6.0" > requirements.txt
fi

python3 -m pip install --quiet --upgrade pip
if ! python3 -m pip install --quiet -r requirements.txt; then
    err "Failed to install dependencies!"
    info "Check internet connection, then try:"
    info "  python3 -m pip install -r requirements.txt"
    exit 1
fi

ok "Dependencies installed"
echo ""

# ============================================================================
#  STEP 3: Ollama models
# ============================================================================

echo "[Step 3/6] Setting up AI models..."
echo ""
echo "  Default model : qwen3:8b         (~5.0 GB)"
echo "  Optional      : qwen2.5-coder:7b (~4.7 GB extra)"
echo ""

# Always pull the default model
if ollama list 2>/dev/null | grep -q "qwen3:8b"; then
    ok "qwen3:8b already present"
else
    info "Pulling qwen3:8b (~5.0 GB) — this may take several minutes..."
    if ollama pull qwen3:8b; then
        ok "qwen3:8b downloaded"
    else
        err "Failed to pull qwen3:8b!"
        info "Check internet connection and disk space (~5 GB), then try:"
        info "  ollama pull qwen3:8b"
        exit 1
    fi
fi

# Ask about the fallback model
echo ""
echo "  Optional: Download qwen2.5-coder:7b (~4.7 GB)?"
echo "  This is a code-specialised fallback model."
echo "  You can always pull it later with:  ollama pull qwen2.5-coder:7b"
echo ""
read -r -p "  Download qwen2.5-coder:7b now? [y/N]: " PULL_FALLBACK

if [[ "$PULL_FALLBACK" =~ ^[Yy]$ ]]; then
    if ollama list 2>/dev/null | grep -q "qwen2.5-coder:7b"; then
        ok "qwen2.5-coder:7b already present"
    else
        info "Pulling qwen2.5-coder:7b (~4.7 GB)..."
        if ollama pull qwen2.5-coder:7b; then
            ok "qwen2.5-coder:7b downloaded"
        else
            warn "Failed to pull qwen2.5-coder:7b"
            info "Pull it later with:  ollama pull qwen2.5-coder:7b"
        fi
    fi
else
    info "Skipping qwen2.5-coder:7b."
    info "Pull later with:  ollama pull qwen2.5-coder:7b"
fi

echo ""

# ============================================================================
#  STEP 4: Docker sandbox image
# ============================================================================

echo "[Step 4/6] Building Docker sandbox image..."
echo ""

if [ ! -f "docker/Dockerfile" ]; then
    err "Dockerfile not found at docker/Dockerfile!"
    info "Make sure you are running setup.sh from the project root (coding_agent/)."
    exit 1
fi

if docker image inspect agent-sandbox &>/dev/null; then
    ok "Docker image 'agent-sandbox' already exists"
else
    info "Building agent-sandbox image (first time may take ~1-2 min)..."
    if docker build -t agent-sandbox -f docker/Dockerfile . --quiet; then
        ok "Docker image built successfully"
    else
        warn "Quiet build failed — retrying with verbose output..."
        if docker build -t agent-sandbox -f docker/Dockerfile .; then
            ok "Docker image built successfully"
        else
            err "Docker build failed!"
            info "Try:  docker system prune -a  then run setup.sh again."
            info "Or build manually:  docker build -t agent-sandbox -f docker/Dockerfile ."
            exit 1
        fi
    fi
fi

echo ""

# ============================================================================
#  STEP 5: Directories
# ============================================================================

echo "[Step 5/6] Creating required directories..."
echo ""

mkdir -p logs
mkdir -p demos
mkdir -p src/generation/generated_code
mkdir -p src/orchestrator/memory_store
mkdir -p docs

ok "Directories ready"
echo ""

# ============================================================================
#  STEP 6: Verification
# ============================================================================

echo "[Step 6/6] Running system verification..."
echo ""

if [ -f "pre_check.py" ]; then
    python3 pre_check.py
    echo ""
else
    warn "pre_check.py not found — skipping verification"
    echo ""
fi

# ============================================================================
#  Done — launch run.sh to activate venv in the user's shell
# ============================================================================

echo "======================================================================"
echo -e "  ${GREEN}${BOLD}SETUP COMPLETE!${RESET}"
echo "======================================================================"
echo ""
echo "  Launching virtual environment shell..."
echo ""
echo "  Once inside, you can run:"
echo "    python3 ESIB_AiCodingAgent.py --generate \"Create a simple calculator\""
echo "    python3 ESIB_AiCodingAgent.py --fix demos/03_broken_script.py"
echo "    python3 ESIB_AiCodingAgent.py --demo"
echo "    python3 ESIB_AiCodingAgent.py --help"
echo ""
echo "  For issues: see TROUBLESHOOTING.md"
echo ""
echo "======================================================================"
echo ""

# Launch run.sh so the user lands directly in an activated shell.
# exec replaces this process — the venv stays active with no manual step needed.
exec "$(dirname "$0")/run.sh"
#!/usr/bin/env bash
# ============================================================================
#  ESIB AI Coding Agent - Setup Script (Linux / macOS)
#  FYP_26_21 | 2026
# ============================================================================

set -e

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

# Python
if ! command -v python3 &>/dev/null; then
    err "Python 3 not found!"
    info "Install Python 3.10+ from: https://python.org"
    info "Linux:  sudo apt-get install python3 python3-venv python3-pip"
    info "macOS:  brew install python@3.10"
    HAS_ERROR=1
else
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    ok "Python $PY_VERSION found"
fi

# Docker
if ! command -v docker &>/dev/null; then
    err "Docker not found!"
    info "Linux:  sudo apt-get install docker.io && sudo systemctl start docker"
    info "macOS:  https://www.docker.com/products/docker-desktop"
    HAS_ERROR=1
elif ! docker ps &>/dev/null; then
    err "Docker is installed but not running!"
    info "Linux:  sudo systemctl start docker"
    info "macOS:  open Docker Desktop"
    HAS_ERROR=1
else
    DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
    ok "Docker running (version $DOCKER_VERSION)"
fi

# Ollama
if ! command -v ollama &>/dev/null; then
    err "Ollama not found!"
    info "Install: curl -fsSL https://ollama.com/install.sh | sh"
    HAS_ERROR=1
elif ! curl -s http://localhost:11434 &>/dev/null; then
    err "Ollama installed but not running on port 11434!"
    info "Start it: ollama serve &"
    HAS_ERROR=1
else
    ok "Ollama running on localhost:11434"
fi

# Disk space (warn if < 8 GB)
FREE_KB=$(df -k . | awk 'NR==2 {print $4}')
FREE_GB=$(( FREE_KB / 1024 / 1024 ))
if [ "$FREE_GB" -lt 8 ]; then
    warn "Low disk space: ~${FREE_GB} GB free. Recommended: 8+ GB."
else
    ok "Disk space: ~${FREE_GB} GB free"
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
    python3 -m venv .venv
    ok "Virtual environment created (.venv)"
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
python3 -m pip install --quiet -r requirements.txt

ok "Dependencies installed"
echo ""

# ============================================================================
#  STEP 3: Ollama models
# ============================================================================

echo "[Step 3/6] Setting up AI models..."
echo ""
echo "  Default model: qwen3:8b  (~5.0 GB)"
echo "  Optional:      qwen2.5-coder:7b  (~4.7 GB extra)"
echo ""

# Always pull the default model
if ollama list 2>/dev/null | grep -q "qwen3:8b"; then
    ok "qwen3:8b already present"
else
    info "Pulling qwen3:8b (~5.0 GB) — this may take several minutes..."
    if ollama pull qwen3:8b; then
        ok "qwen3:8b downloaded"
    else
        err "Failed to pull qwen3:8b"
        info "Try manually:  ollama pull qwen3:8b"
        info "Check your internet connection and available disk space (~5 GB)."
        echo ""
        exit 1
    fi
fi

# Ask about the second model
echo ""
echo -e "  ${BOLD}Optional:${RESET} Do you also want to download qwen2.5-coder:7b (~4.7 GB)?"
echo "  This is a code-specialised fallback model. You can always pull it later."
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
            info "You can pull it later:  ollama pull qwen2.5-coder:7b"
        fi
    fi
else
    info "Skipping qwen2.5-coder:7b. Pull later with:  ollama pull qwen2.5-coder:7b"
fi

echo ""

# ============================================================================
#  STEP 4: Docker sandbox image
# ============================================================================

echo "[Step 4/6] Building Docker sandbox image..."
echo ""

if [ ! -f "docker/Dockerfile" ]; then
    err "Dockerfile not found at docker/Dockerfile!"
    info "Make sure you are running this script from the project root (coding_agent/)."
    exit 1
fi

if docker image inspect agent-sandbox &>/dev/null; then
    ok "Docker image 'agent-sandbox' already exists"
else
    info "Building agent-sandbox image (first time may take ~1–2 min)..."
    if docker build -t agent-sandbox -f docker/Dockerfile . --quiet; then
        ok "Docker image built successfully"
    else
        err "Docker build failed"
        info "Try:  docker system prune -a  then run setup.sh again"
        info "Or build manually:  docker build -t agent-sandbox -f docker/Dockerfile ."
        exit 1
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
mkdir -p memory_store
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
fi

# ============================================================================
#  Done
# ============================================================================

echo "======================================================================"
echo -e "  ${GREEN}${BOLD}SETUP COMPLETE!${RESET}"
echo "======================================================================"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Generate code:"
echo "     python3 ESIB_AiCodingAgent.py --generate \"Create a simple calculator\""
echo ""
echo "  2. Debug a script:"
echo "     python3 ESIB_AiCodingAgent.py --fix demos/03_broken_script.py"
echo ""
echo "  3. Run the demo:"
echo "     python3 ESIB_AiCodingAgent.py --demo"
echo ""
echo "  4. Get help:"
echo "     python3 ESIB_AiCodingAgent.py --help"
echo ""
echo "  For issues: see TROUBLESHOOTING.md"
echo ""
echo "======================================================================"
echo ""
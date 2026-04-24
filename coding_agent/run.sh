#!/usr/bin/env bash
# ============================================================================
#  ESIB AI Coding Agent - Virtual Environment Activator
#  FYP_26_21 | 2026
#
#  This script activates the virtual environment and keeps the shell open.
#  After activation, run Python commands directly.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -f ".venv/bin/activate" ]; then
    echo ""
    echo "[ERROR] Virtual environment not found!"
    echo ""
    echo "Please run setup first:  ./setup.sh"
    echo ""
    exit 1
fi

# Activate virtual environment
# shellcheck disable=SC1091
source .venv/bin/activate

echo ""
echo "======================================================================"
echo "  Virtual Environment Activated!"
echo "======================================================================"
echo ""
echo "Now you can run:"
echo "  python3 ESIB_AiCodingAgent.py --generate \"your prompt\""
echo "  python3 ESIB_AiCodingAgent.py --fix script.py"
echo "  python3 ESIB_AiCodingAgent.py --demo"
echo "  python3 ESIB_AiCodingAgent.py --help"
echo ""
echo "Examples:"
echo "  python3 ESIB_AiCodingAgent.py --generate \"Create a simple calculator\""
echo "  python3 ESIB_AiCodingAgent.py --fix demos/03_broken_script.py"
echo ""
echo "======================================================================"
echo ""

# Keep the shell open with venv activated.
# $SHELL is the user's login shell (bash on Linux, zsh on macOS).
# Falling back to bash if $SHELL is unset or unavailable.
CURRENT_SHELL="${SHELL:-bash}"
exec "$CURRENT_SHELL" --norc --noprofile 2>/dev/null || exec bash --norc --noprofile
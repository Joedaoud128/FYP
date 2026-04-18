#!/bin/bash

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                                                               ║"
echo "║         ESIB AI Coding Agent - Setup & Validation            ║"
echo "║              FYP 26/21 - USJ Beirut                          ║"
echo "║                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track if we have errors
HAS_ERROR=0

echo "🔍 Step 1/6: Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found${NC}"
    echo "   Please install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    HAS_ERROR=1
else
    if ! docker ps &> /dev/null; then
        echo -e "${RED}❌ Docker is installed but not running${NC}"
        echo "   Please start Docker Desktop"
        HAS_ERROR=1
    else
        DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
        echo -e "${GREEN}✅ Docker running${NC} (version $DOCKER_VERSION)"
    fi
fi

echo ""
echo "🔍 Step 2/6: Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}❌ Ollama not found${NC}"
    echo "   Please install Ollama from: https://ollama.ai"
    HAS_ERROR=1
else
    if ! curl -s http://localhost:11434/api/tags &> /dev/null; then
        echo -e "${RED}❌ Ollama installed but not running on port 11434${NC}"
        echo "   Please start Ollama:"
        echo "   - Linux/Mac: run 'ollama serve' in another terminal"
        echo "   - Windows: Ollama should start automatically"
        HAS_ERROR=1
    else
        echo -e "${GREEN}✅ Ollama running${NC} on localhost:11434"
    fi
fi

echo ""
echo "🔍 Step 3/6: Checking AI Models..."
if [ $HAS_ERROR -eq 0 ]; then
    MODELS_FOUND=0
    
    # Check qwen2.5-coder:7b
    if curl -s http://localhost:11434/api/tags | grep -q "qwen2.5-coder:7b"; then
        echo -e "${GREEN}✅ Model qwen2.5-coder:7b found${NC}"
        MODELS_FOUND=$((MODELS_FOUND + 1))
    else
        echo -e "${YELLOW}⚠️  Model qwen2.5-coder:7b not found${NC}"
        echo "   Downloading now (this will take 5-10 minutes, ~4.7GB)..."
        echo ""
        if ollama pull qwen2.5-coder:7b; then
            echo -e "${GREEN}✅ Model qwen2.5-coder:7b downloaded successfully${NC}"
            MODELS_FOUND=$((MODELS_FOUND + 1))
        else
            echo -e "${RED}❌ Failed to download qwen2.5-coder:7b${NC}"
            HAS_ERROR=1
        fi
    fi
    
    # Check qwen3:8b
    if curl -s http://localhost:11434/api/tags | grep -q "qwen3:8b"; then
        echo -e "${GREEN}✅ Model qwen3:8b found${NC}"
        MODELS_FOUND=$((MODELS_FOUND + 1))
    else
        echo -e "${YELLOW}⚠️  Model qwen3:8b not found${NC}"
        echo "   Downloading now (this will take 5-10 minutes, ~5.0GB)..."
        echo ""
        if ollama pull qwen3:8b; then
            echo -e "${GREEN}✅ Model qwen3:8b downloaded successfully${NC}"
            MODELS_FOUND=$((MODELS_FOUND + 1))
        else
            echo -e "${YELLOW}⚠️  Failed to download qwen3:8b (optional model)${NC}"
            echo "   You can still use qwen2.5-coder:7b"
        fi
    fi
    
    if [ $MODELS_FOUND -eq 0 ]; then
        echo -e "${RED}❌ No models available${NC}"
        HAS_ERROR=1
    elif [ $MODELS_FOUND -eq 1 ]; then
        echo -e "${YELLOW}⚠️  Only one model available (system will work but model selection limited)${NC}"
    else
        echo -e "${GREEN}✅ Both models available${NC}"
    fi
fi

echo ""
echo "🔍 Step 4/6: Getting Docker sandbox image..."
if [ $HAS_ERROR -eq 0 ]; then
    # Check if image already exists locally
    if docker images mariasabbagh1/esib-ai-agent:latest -q | grep -q .; then
        echo -e "${GREEN}✅ Docker image already exists locally${NC}"
    else
        echo "   Downloading pre-built image from Docker Hub..."
        echo "   (This is faster than building locally - ~200MB download)"
        if docker pull mariasabbagh1/esib-ai-agent:latest; then
            echo -e "${GREEN}✅ Docker image downloaded${NC}"
        else
            echo -e "${YELLOW}⚠️  Failed to pull from Docker Hub${NC}"
            echo "   Falling back to local build (will take 1-2 minutes)..."
            if docker build -t mariasabbagh1/esib-ai-agent:latest -f docker/Dockerfile . --quiet; then
                echo -e "${GREEN}✅ Docker image built locally${NC}"
            else
                echo -e "${RED}❌ Docker build failed${NC}"
                echo "   Try running: docker build -t mariasabbagh1/esib-ai-agent:latest -f docker/Dockerfile ."
                HAS_ERROR=1
            fi
        fi
    fi
    
    # Tag as agent-sandbox for compatibility with existing code
    if [ $HAS_ERROR -eq 0 ]; then
        docker tag mariasabbagh1/esib-ai-agent:latest agent-sandbox
        echo -e "${GREEN}✅ Image tagged as 'agent-sandbox'${NC}"
    fi
fi

echo ""
echo "🔍 Step 5/6: Installing Python dependencies..."
if [ $HAS_ERROR -eq 0 ]; then
    if pip install -q -r requirements.txt; then
        echo -e "${GREEN}✅ Python dependencies installed${NC}"
    else
        echo -e "${RED}❌ Failed to install dependencies${NC}"
        HAS_ERROR=1
    fi
fi

echo ""
echo "🔍 Step 6/6: Creating necessary directories..."
mkdir -p generated_code memory_store logs
echo -e "${GREEN}✅ Directories created${NC}"

echo ""
echo "══════════════════════════════════════════════════════════════"

if [ $HAS_ERROR -eq 0 ]; then
    echo -e "${GREEN}"
    echo "✅ Setup Complete! Your system is ready."
    echo -e "${NC}"
    echo "Next steps:"
    echo "  1. Test the system:  ./run.sh check"
    echo "  2. Run a demo:       ./run.sh demo"
    echo "  3. Generate code:    ./run.sh generate 'your prompt here'"
    echo ""
    echo "Or use the direct entry point:"
    echo "  python ESIB_AiCodingAgent.py --generate 'your prompt'"
    echo "  python ESIB_AiCodingAgent.py --generate 'your prompt' --model qwen3:8b"
else
    echo -e "${RED}"
    echo "❌ Setup incomplete - please fix the errors above"
    echo -e "${NC}"
    echo "Need help? Check docs/TROUBLESHOOTING.md"
    exit 1
fi

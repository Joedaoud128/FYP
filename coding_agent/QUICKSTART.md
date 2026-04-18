# ESIB AI Coding Agent - Quick Start Guide

## Overview

This is an autonomous AI coding agent that can:
- **Generate** Python code from natural language descriptions
- **Debug** broken Python scripts automatically
- Run in a **secure Docker sandbox**
- Use two different AI models: `qwen2.5-coder:7b` or `qwen3:8b`

**Project:** FYP 26/21 - École Supérieure d'Ingénieurs de Beyrouth (USJ)

---

## Prerequisites

Install these two tools before starting:

### 1. Docker Desktop
- **Windows/Mac:** Download from https://www.docker.com/products/docker-desktop
- **Linux:** Install Docker Engine via your package manager

**Verify installation:**
```bash
docker --version
docker ps
```

### 2. Ollama
- **All platforms:** Download from https://ollama.ai
- **Windows/Mac:** Starts automatically after installation
- **Linux:** Run `ollama serve` in a separate terminal

**Verify installation:**
```bash
ollama --version
curl http://localhost:11434/api/tags
```

---

## Installation (5-10 minutes)

### Step 1: Download the Project

```bash
# Clone the repository
git clone https://github.com/Joedaoud128/FYP.git
cd FYP/coding_agent

# Or download and extract the ZIP file
```

### Step 2: Run Setup

**On Linux/Mac:**
```bash
chmod +x setup.sh run.sh
./setup.sh
```

**On Windows:**
```batch
setup.bat
```

**What the setup does:**
1. ✅ Checks Docker is running
2. ✅ Checks Ollama is running
3. ✅ Downloads AI models (~10GB total, first time only)
   - `qwen2.5-coder:7b` (~4.7GB) - Default model
   - `qwen3:8b` (~5.0GB) - Alternative model
4. ✅ Downloads pre-built Docker image from Docker Hub (~200MB)
   - **OR** builds locally if download fails (automatic fallback)
5. ✅ Installs Python dependencies (only `pyyaml`)
6. ✅ Creates necessary directories

**Expected time:**
- First time: 10-15 minutes (downloads models + Docker image)
- Subsequent runs: < 1 minute (everything cached)
- Docker image download: ~30 seconds (vs 2 minutes if building locally)

### Step 3: Verify Installation

```bash
# Linux/Mac
./run.sh check

# Windows
run.bat check
```

**Expected output:**
```
✅ Docker Engine         Docker is running
✅ Ollama Service        Ollama is running on port 11434
✅ AI Models             Both models available: qwen2.5-coder:7b, qwen3:8b
✅ Docker Image          Docker image 'agent-sandbox' exists
✅ Python Dependencies   Python dependencies installed

System is ready to run!
```

---

## Docker Image Distribution

Our production-ready Docker image is available on Docker Hub for faster setup.

**Registry:** [mariasabbagh1/esib-ai-agent](https://hub.docker.com/r/mariasabbagh1/esib-ai-agent)

**Benefits:**
- ✅ Faster setup (~30 seconds vs 2 minutes)
- ✅ Guaranteed identical environment
- ✅ Production-grade deployment

**Manual pull (optional):**
```bash
docker pull mariasabbagh1/esib-ai-agent:latest
```

**Note:** The setup script automatically handles this. You don't need to pull manually.

---

## Usage

### Option 1: Convenience Wrapper Scripts (Easiest)

**Run a demo:**
```bash
./run.sh demo           # Linux/Mac
run.bat demo            # Windows
```

**Generate code with default model:**
```bash
./run.sh generate "Write a web scraper for Hacker News"
```

**Generate code with specific model:**
```bash
./run.sh generate "Build a REST API with Flask" qwen3:8b
```

**Debug a script:**
```bash
./run.sh debug demos/03_broken_script.py
./run.sh debug my_script.py qwen3:8b
```

---

### Option 2: Direct Entry Point (Full Control)

**Generate Mode:**
```bash
# Use default model (qwen2.5-coder:7b)
python ESIB_AiCodingAgent.py --generate "Write a CSV parser"

# Use specific model
python ESIB_AiCodingAgent.py --generate "Write a CSV parser" --model qwen3:8b

# Save to custom location
python ESIB_AiCodingAgent.py --generate "..." --output my_script.py

# Enable verbose logging
python ESIB_AiCodingAgent.py --generate "..." --verbose
```

**Debug Mode:**
```bash
# Use default model
python ESIB_AiCodingAgent.py --fix broken_script.py

# Use specific model
python ESIB_AiCodingAgent.py --fix broken_script.py --model qwen3:8b

# With verbose output
python ESIB_AiCodingAgent.py --fix broken_script.py --verbose
```

**Demo Mode:**
```bash
# Run all demos
python ESIB_AiCodingAgent.py --demo

# Run specific demo
python ESIB_AiCodingAgent.py --demo --demo-mode generate
python ESIB_AiCodingAgent.py --demo --demo-mode debug
```

**Help:**
```bash
python ESIB_AiCodingAgent.py --help
```

---

## Model Selection Guide

### qwen2.5-coder:7b (Default)
- **Optimized for:** Code generation and debugging
- **Size:** 4.7GB
- **Speed:** Faster responses
- **Best for:** Most coding tasks, debugging, script generation

### qwen3:8b
- **Optimized for:** General-purpose tasks
- **Size:** 5.0GB
- **Speed:** Slightly slower but more capable
- **Best for:** Complex logic, API design, architectural planning

**How to choose:**
- Use **default** for everyday coding tasks
- Use **qwen3:8b** for more complex or creative tasks
- Try both and compare results

**Switching models:**
```bash
# Environment variable (affects all subsequent commands)
export OLLAMA_MODEL=qwen3:8b
python ESIB_AiCodingAgent.py --generate "..."

# Command-line flag (one-time override)
python ESIB_AiCodingAgent.py --generate "..." --model qwen3:8b
```

---

## What Happens During Execution?

### Generate Mode Pipeline (6 Stages)

```
🤖 Starting code generation...
   Stage 1/6: Prompt validation & sanitization
   Stage 2/6: Environment detection (Python, OS, packages)
   Stage 3/6: Requirement parsing & complexity analysis
   Stage 4/6: Agentic planning with ReAct pattern
              (LLM uses tools: search_docs, write_file, run_sandbox, install_package)
   Stage 5/6: Library verification via PyPI + venv creation
   Stage 6/6: Final code assembly & guardrails check
   
✅ Code generated successfully
📁 Output: generated_code/script.py
🔒 Security: All commands validated by guardrails
⏱️  Time: ~25-40 seconds
```

### Debug Mode Pipeline

```
🔧 Starting debugging session...
   📝 Reading script: my_script.py
   🔍 Analyzing errors (syntax, runtime, logic)
   🔄 Iteration 1/10: Fixing NameError on line 42
      - Proposed fix validated by guardrails
      - Code rewritten deterministically
      - Testing in Docker sandbox...
   ✅ Fix successful
   
📁 Fixed code: generated_code/script.py
🔄 Iterations: 1
⏱️  Time: ~15-30 seconds
```

---

## Example Workflows

### Workflow 1: Quick Code Generation

```bash
# 1. Generate a script
./run.sh generate "Parse a CSV file and create a bar chart"

# 2. Check the output
cat generated_code/script.py

# 3. Run it
python generated_code/script.py
```

### Workflow 2: Model Comparison

```bash
# Generate with model 1
./run.sh generate "Build a JSON API client" qwen2.5-coder:7b
mv generated_code/script.py version1.py

# Generate with model 2
./run.sh generate "Build a JSON API client" qwen3:8b
mv generated_code/script.py version2.py

# Compare results
diff version1.py version2.py
```

### Workflow 3: Debug → Fix → Verify

```bash
# 1. Try to run a broken script
python my_broken_script.py
# (fails with errors)

# 2. Debug it
./run.sh debug my_broken_script.py

# 3. Check the fixed version
python generated_code/script.py
# (works correctly)
```

---

## Command Reference

### Setup & Verification
```bash
./run.sh setup          # First-time setup
./run.sh check          # Health check
```

### Code Generation
```bash
./run.sh generate 'prompt'          # Use default model
./run.sh generate 'prompt' qwen3:8b # Use specific model
```

### Debugging
```bash
./run.sh debug script.py            # Use default model
./run.sh debug script.py qwen3:8b   # Use specific model
```

### Demos
```bash
./run.sh demo           # Run all 3 demo scenarios
```

### Help
```bash
./run.sh help           # Show all commands
python ESIB_AiCodingAgent.py --help  # Show detailed options
```

---

## Output Locations

```
project/
├── generated_code/      # Generated and fixed scripts
│   ├── script.py        # Latest output
│   └── venv/            # Auto-created virtual environment
├── memory_store/        # System learning data
│   └── memory_store.json
├── logs/                # Execution logs
│   ├── generate_*.log
│   └── debug_*.log
└── demos/               # Example scenarios
    ├── 01_calculator.txt
    ├── 02_web_scraper.txt
    └── 03_broken_script.py
```

---

## Tips for Best Results

### Writing Good Prompts

**Good prompts:**
```
✅ "Write a Python script that fetches weather data from OpenWeatherMap API and displays it"
✅ "Create a CSV parser that reads sales.csv and calculates total revenue per product"
✅ "Build a simple REST API client for the JSONPlaceholder API with GET and POST methods"
```

**Bad prompts:**
```
❌ "Make me a website" (too vague, wrong language)
❌ "Code" (no context)
❌ "Fix this" (no file provided)
```

**Prompt guidelines:**
- Be specific about what you want
- Mention libraries/frameworks if you have preferences
- Specify input/output formats
- Include error handling requirements
- Provide example data if relevant

### Performance Tips

- **First run:** Slower due to model loading and venv creation
- **Subsequent runs:** Faster (cached models, reused venv)
- **GPU acceleration:** Automatically used if available (NVIDIA/AMD)
- **CPU mode:** Works fine, just slower (~2x)

### Troubleshooting

**"Docker is not running"**
```bash
# Start Docker Desktop and wait for it to fully initialize
# Look for the whale icon in system tray (Windows/Mac)
docker ps  # Should show empty list, not error
```

**"Ollama not running on port 11434"**
```bash
# Linux/Mac: Start Ollama manually
ollama serve

# Windows: Ollama should auto-start; if not, reinstall

# Test: Open http://localhost:11434 in browser
# Should show: "Ollama is running"
```

**"Model not found"**
```bash
# Manually pull the model
ollama pull qwen2.5-coder:7b
ollama pull qwen3:8b

# Verify
ollama list
```

**"Docker build failed"**
```bash
# Check disk space
df -h  # Need at least 2GB free

# Rebuild with verbose output
docker build -t agent-sandbox -f docker/Dockerfile .
```

**"Generation fails or hangs"**
```bash
# Enable verbose logging to see what's happening
python ESIB_AiCodingAgent.py --generate "..." --verbose

# Check logs
cat logs/generate_*.log
```

---

## System Requirements

**Minimum:**
- **OS:** Windows 10/11, macOS 12+, or Linux (Ubuntu 20.04+)
- **RAM:** 8GB (16GB recommended)
- **Disk:** 15GB free (models + Docker images)
- **Docker:** Version 20.10+
- **Python:** 3.10+
- **Internet:** Required for first-time model download

**Optional (for GPU acceleration):**
- **NVIDIA GPU** with CUDA support (Linux/Windows)
- **AMD GPU** with ROCm support (Linux)

---

## Advanced Usage

### Environment Variables

```bash
# Override model selection
export OLLAMA_MODEL=qwen3:8b

# Override Ollama URL (if running remotely)
export OLLAMA_BASE_URL=http://192.168.1.100:11434

# Debugging configuration
export MAX_DEBUG_ITERATIONS=15
export DEBUG_TIMEOUT=60
```

### Custom Output Paths

```bash
# Save generated code to specific location
python ESIB_AiCodingAgent.py --generate "..." --output ~/my_scripts/parser.py

# Generate multiple scripts
for prompt in "script1" "script2" "script3"; do
    python ESIB_AiCodingAgent.py --generate "$prompt" --output "${prompt}.py"
done
```

### Running in Docker

```bash
# Build the full system image (optional)
docker build -t esib-ai-agent .

# Run in container
docker run -it --rm \
    -v $(pwd)/generated_code:/app/generated_code \
    -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    esib-ai-agent \
    python ESIB_AiCodingAgent.py --generate "..."
```

---

## FAQ

**Q: Do I need both models?**
A: No. The system works with just one model. Both are downloaded by default for flexibility.

**Q: Can I use other Ollama models?**
A: The system is optimized for `qwen2.5-coder:7b` and `qwen3:8b`. Other models may work but are untested.

**Q: Does this work offline?**
A: Yes, after initial setup. Models run locally via Ollama.

**Q: How much does it cost?**
A: $0. Everything runs locally. No API keys or subscriptions.

**Q: Is my code safe?**
A: Yes. All execution happens in an isolated Docker sandbox with strict security policies.

**Q: Can it generate code in other languages?**
A: Currently optimized for Python only.

**Q: What if generation fails?**
A: The system automatically retries with guardrails validation. Check logs for details.

---

## Support & Documentation

- **Troubleshooting:** See `docs/TROUBLESHOOTING.md`
- **Architecture:** See `docs/ARCHITECTURE.md`
- **Handoff Protocol:** See `docs/HANDOFF_PROTOCOL.md`
- **Logs:** Check `logs/` directory
- **Memory Store:** Check `memory_store/memory_store.json`

---

## Quick Reference Card

```
┌──────────────────────────────────────────────────────────────┐
│  FIRST TIME SETUP                                            │
│  1. Install Docker Desktop                                   │
│  2. Install Ollama                                           │
│  3. Run: ./setup.sh  (or setup.bat on Windows)               │
│  4. Test: ./run.sh check                                     │
├──────────────────────────────────────────────────────────────┤
│  GENERATE CODE                                               │
│  ./run.sh generate "your prompt"                             │
│  ./run.sh generate "your prompt" qwen3:8b                    │
│  OR: python ESIB_AiCodingAgent.py --generate "..." --model X │
├──────────────────────────────────────────────────────────────┤
│  DEBUG CODE                                                  │
│  ./run.sh debug path/to/script.py                            │
│  OR: python ESIB_AiCodingAgent.py --fix script.py --model X  │
├──────────────────────────────────────────────────────────────┤
│  SEE IT WORK                                                 │
│  ./run.sh demo                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## License & Credits

**Project:** FYP 26/21  
**Institution:** École Supérieure d'Ingénieurs de Beyrouth (USJ)  
**Supervisor:** Anthony Assi  

**Team:**
- Joe Anthony Daoud — Code Generation
- Raymond Rached — Code Debugging
- Elise Nassar — Security & Guardrails
- Maria — Orchestration & Docker Execution

---

*Last updated: April 2026*

# Quick Start Guide

Get the ESIB AI Coding Agent running in under 10 minutes.

---

## Prerequisites Check

**BEFORE running setup, verify these are installed and running:**

### 1. Python 3.10+

```bash
python --version
```
**Expected:** `Python 3.10.x` or higher

**If not installed:**
- Download from [python.org](https://python.org)
- **Windows:** Check "Add Python to PATH" during installation
- Restart terminal after installation

---

### 2. Docker Desktop (Running)

```bash
docker ps
```
**Expected:** Table of containers (even if empty) — no errors

**If error or not installed:**

**Windows/Mac:**
1. Download [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Install and restart your computer
3. **Start Docker Desktop** (important — wait for the whale icon to be steady)

**Linux:**
```bash
sudo apt-get update
sudo apt-get install docker.io
sudo systemctl start docker
sudo usermod -aG docker $USER  # Then log out and back in
```

---

### 3. Ollama (Running)

```bash
curl http://localhost:11434
```
**Expected:** `Ollama is running`

**If not installed:**

**Windows:** Download from [ollama.com/download](https://ollama.com/download) and run the installer. Ollama starts automatically on port 11434.

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS:** Download the .dmg from [ollama.com/download](https://ollama.com/download).

**To start Ollama manually (Linux/Mac):**
```bash
ollama serve &
```

---

## Installation

### Windows

```cmd
:: 1. Clone repository
git clone https://github.com/Joedaoud128/FYP.git
cd FYP\coding_agent

:: 2. Run setup (5-10 min — downloads ~10 GB of models)
.\setup.bat

:: 3. Verify installation
python pre_check.py
```

### Linux / macOS

```bash
# 1. Clone repository
git clone https://github.com/Joedaoud128/FYP.git
cd FYP/coding_agent

# 2. Make scripts executable
chmod +x setup.sh

# 3. Run setup (5-10 min — downloads ~10 GB of models)
./setup.sh

# 4. Verify installation
python pre_check.py
```

---

## What Setup Does

1. ✅ Creates Python virtual environment (`.venv`)
2. ✅ Installs Python dependencies (`pyyaml`, etc.)
3. ✅ Pulls AI models — `qwen2.5-coder:7b` (~4.7 GB) and `qwen3:8b` (~5.0 GB)
4. ✅ Builds Docker sandbox image (`agent-sandbox`)
5. ✅ Creates required directories (`logs/`, `demos/`, etc.)
6. ✅ Verifies system health

**Total time:** 5–10 minutes | **Total download:** ~10 GB

---

## Windows — Activating the Virtual Environment

On Windows, `run.bat` activates the `.venv` and opens a persistent CMD shell so you can type commands directly:

```cmd
run.bat
```

You will see:

```
======================================================================
  Virtual Environment Activated!
======================================================================

Now you can run:
  python ESIB_AiCodingAgent.py --generate "your prompt"
  python ESIB_AiCodingAgent.py --fix script.py
  python ESIB_AiCodingAgent.py --demo
  python ESIB_AiCodingAgent.py --help
```

> **Keep this window open** for your entire session. All subsequent Python commands go here.

On **Linux/Mac**, the venv is activated once and your normal terminal is used — no separate step needed if setup completed successfully.

---

## First Run — Generation Mode

Create code from a natural language prompt.

```bash
python ESIB_AiCodingAgent.py --generate "Create a simple calculator"
```

**What happens:**
1. Prompt is validated by guardrails
2. LLM plans and generates Python code (6-stage pipeline)
3. Code runs in hardened Docker sandbox
4. Working script saved to `src/generation/generated_code/`
5. Session log saved to `logs/`

**More complex example:**
```bash
python ESIB_AiCodingAgent.py --generate "Build a web scraper that extracts article titles and summaries from a news website, handles pagination, and saves results to CSV"
```

---

## First Run — Debug Mode

Automatically detect and fix errors in broken scripts.

```bash
python ESIB_AiCodingAgent.py --fix demos/03_broken_script.py
```

**What happens:**
1. Script runs → error detected
2. LLM analyses error and generates a fix
3. Fix validated and tested in Docker sandbox
4. Fixed script saved; iterations logged

---

## Model Selection

The agent defaults to `qwen2.5-coder:7b`. Use `--model` to switch:

```bash
# Use qwen3:8b (if available)
python ESIB_AiCodingAgent.py --generate "..." --model qwen3:8b

# Explicitly use qwen2.5-coder:7b
python ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b
```

### If `qwen3:8b` is not available on your machine

If you only have `qwen2.5-coder:7b` installed, always pass `--model qwen2.5-coder:7b`:

```bash
python ESIB_AiCodingAgent.py --generate "Create a calculator" --model qwen2.5-coder:7b
python ESIB_AiCodingAgent.py --fix buggy.py --model qwen2.5-coder:7b
```

Check what models are installed:
```bash
ollama list
```

To download qwen3:8b later:
```bash
ollama pull qwen3:8b
```

---

## Common Commands

```bash
# Help
python ESIB_AiCodingAgent.py --help

# Verbose logging (shows all pipeline stages)
python ESIB_AiCodingAgent.py --generate "..." --verbose
python ESIB_AiCodingAgent.py --fix script.py --verbose

# Save generated script to a custom path
python ESIB_AiCodingAgent.py --generate "..." --output my_script.py

# Run built-in demo
python ESIB_AiCodingAgent.py --demo
python ESIB_AiCodingAgent.py --demo --demo-mode generate
python ESIB_AiCodingAgent.py --demo --demo-mode debug

# System health check
python pre_check.py
```

---

## Troubleshooting

### "Docker not running"

```bash
# Windows/Mac: Open Docker Desktop and wait for it to start
# Linux:
sudo systemctl start docker
```

### "Ollama not responding"

```bash
# Check
curl http://localhost:11434

# Start it (Linux/Mac):
ollama serve &
# Windows: find Ollama in Start menu or system tray
```

### Model not found

```bash
# See what is installed
ollama list

# Pull missing models
ollama pull qwen2.5-coder:7b
ollama pull qwen3:8b

# If only qwen2.5-coder is available, always add --model:
python ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b
```

### "Python not found"

Add Python to PATH:
- **Windows:** System Settings → Environment Variables → PATH → add `C:\Python3X\` and `C:\Python3X\Scripts\`
- Restart terminal and try again

**For full troubleshooting:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## What You Get After Setup

```
coding_agent/
├── .venv/                              # Virtual environment
├── logs/                               # Session logs & pipeline stats
│   └── pipeline_run_stats.jsonl        # Token usage & cost tracking
├── src/generation/generated_code/      # Generated scripts appear here
├── memory_store/                       # Error pattern memory
├── demos/                              # Example scripts
└── docker/                             # Sandbox container definition
```

---

## Next Steps

### Try generation

```bash
# Simple
python ESIB_AiCodingAgent.py --generate "Create a CSV parser"

# Medium
python ESIB_AiCodingAgent.py --generate "Build a to-do list manager with SQLite"

# Complex
python ESIB_AiCodingAgent.py --generate "Create a REST API with authentication, rate limiting, and database integration"
```

### Try debug mode

```bash
# Create a buggy script
cat > buggy.py << 'EOF'
def divide(a, b):
    return a / b

print(divide(10, 0))
EOF

# Fix it automatically
python ESIB_AiCodingAgent.py --fix buggy.py
```

### Check pipeline statistics

After each run, `logs/pipeline_run_stats.jsonl` is updated:

```bash
cat logs/pipeline_run_stats.jsonl
```

Each entry records: `run_id`, `timestamp`, `status`, `stage reached`, `token usage`, `estimated cost`, and a `summary` with the generated file path, function count, and class count.

> **Note:** Cost is "equivalent cloud pricing" — estimates what the same tokens would cost on a commercial API. Since you are running Ollama locally, your actual cost is $0.

### Customise model / timeouts

```bash
# Linux/Mac
export OLLAMA_MODEL=qwen2.5-coder:7b
export LLM_TIMEOUT=300

# Windows CMD
set OLLAMA_MODEL=qwen2.5-coder:7b
set LLM_TIMEOUT=300
```

---

## Verification Checklist

- [ ] `python pre_check.py` — all green
- [ ] `docker ps` — no errors
- [ ] `curl http://localhost:11434` — returns "Ollama is running"
- [ ] `ollama list` — shows at least `qwen2.5-coder:7b`
- [ ] Generation mode creates a working script in `src/generation/generated_code/`
- [ ] Debug mode fixes a broken script
- [ ] `logs/pipeline_run_stats.jsonl` is updated after each run

---

**You're all set! Start generating and debugging code. 🚀**
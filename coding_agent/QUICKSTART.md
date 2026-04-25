# Quick Start Guide

Get the ESIB AI Coding Agent running in under 10 minutes.

---

## Python Command Note

Depending on your OS, the Python command differs:

- **Windows:** use `python`
- **Linux / macOS:** use `python3`

All commands in this guide are shown for both platforms.

---

## Prerequisites Check

**BEFORE running setup, verify these are installed and running:**

### 1. Python 3.10+

> **Python 3.10 or higher is required.** The project uses the `str | None` union type-hint syntax introduced in 3.10. Older versions (3.8, 3.9) will crash on startup.

```bash
# Linux/macOS
python3 --version

# Windows
python --version
```
**Expected:** `Python 3.10.x` or higher

**If not installed or version is too old:**

**macOS:**
```bash
brew install python@3.10
python3.10 --version   # verify
```

**Linux:**
```bash
sudo apt-get install python3.10 python3.10-venv python3.10-pip
python3.10 --version   # verify
```

**Windows:** Download Python 3.10+ from [python.org/downloads](https://python.org/downloads). During installation, check **"Add Python to PATH"**. Restart your terminal after installation.

---

### 2. Docker Desktop (Running)

```bash
docker ps
```
**Expected:** Table of containers (even if empty) — no errors

**If error or not installed:**

**Windows/macOS:**
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

**To start Ollama manually (Linux/macOS):**
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

:: 2. Run setup — installs everything and opens an activated shell automatically
.\setup.bat

:: 3. Verify everything is ready (run this inside the shell that setup opened)
python pre_check.py
```

> `setup.bat` activates the virtual environment and launches `run.bat` automatically at the end. Once setup finishes, you are already inside an active shell — run `python pre_check.py` straight away.

### Linux / macOS

```bash
# 1. Clone repository
git clone https://github.com/Joedaoud128/FYP.git
cd FYP/coding_agent

# 2. Make scripts executable
chmod +x setup.sh run.sh

# 3. Run setup — installs everything and opens an activated shell automatically
./setup.sh

# 4. Verify everything is ready (run this inside the shell that setup opened)
python3 pre_check.py
```

> `setup.sh` activates the virtual environment and launches `./run.sh` automatically at the end. Once setup finishes, you are already inside an active shell — run `python3 pre_check.py` straight away.

---

## What Setup Does

1. ✅ Creates Python virtual environment (`.venv`)
2. ✅ Installs Python dependencies (`pyyaml`, etc.)
3. ✅ Pulls the default AI model — `qwen3:8b` (~5.0 GB)
4. ✅ **Asks whether you want to also download `qwen2.5-coder:7b`** (~4.7 GB extra)
5. ✅ Builds Docker sandbox image (`agent-sandbox`)
6. ✅ Creates required directories (`logs/`, `demos/`, etc.)
7. ✅ Verifies system health

**Total time:** 5–10 minutes | **Minimum download:** ~5 GB (default model only)

### Do you need the second model?

During setup you will be prompted:

```
Optional: Download qwen2.5-coder:7b (~4.7 GB)?
Download qwen2.5-coder:7b now? [y/N]:
```

Answer **N** (or press Enter) to skip it. Pull it later if you need it:

```bash
ollama pull qwen2.5-coder:7b
```

Pull it when you want to:
- Switch to a dedicated code-specialised model
- Compare outputs between the two models
- Use `qwen2.5-coder:7b` as an explicit fallback if `qwen3:8b` is slow on your machine

If you only plan to use `qwen3:8b`, skip this — no extra download needed.

---

## Starting a New Session

After first-time setup, every time you open a new terminal you need to re-activate the venv before running any commands.

### Windows

```cmd
:: 1. Activate the virtual environment
run.bat

:: 2. Verify the system is healthy before starting work
python pre_check.py
```

### Linux / macOS

```bash
# 1. Activate the virtual environment
./run.sh

# 2. Verify the system is healthy before starting work
python3 pre_check.py
```

You will see after activation:

```
======================================================================
  Virtual Environment Activated!
======================================================================

Now you can run:
  python3 ESIB_AiCodingAgent.py --generate "your prompt"
  python3 ESIB_AiCodingAgent.py --fix script.py
  python3 ESIB_AiCodingAgent.py --demo
  python3 ESIB_AiCodingAgent.py --help
```

> **Keep this window open** for your entire session. All subsequent Python commands go here.

> **Always run `pre_check.py` at the start of each session** — it confirms Docker is running, Ollama is responding, and the model is available before you begin.

---

## First Run — Generation Mode

Create code from a natural language prompt.

```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "Create a simple calculator"

# Windows
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
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "Build a web scraper that extracts article titles and summaries from a news website, handles pagination, and saves results to CSV"

# Windows
python ESIB_AiCodingAgent.py --generate "Build a web scraper that extracts article titles and summaries from a news website, handles pagination, and saves results to CSV"
```

---

## First Run — Debug Mode

Automatically detect and fix errors in broken scripts.

```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --fix demos/03_broken_script.py

# Windows
python ESIB_AiCodingAgent.py --fix demos/03_broken_script.py
```

**What happens:**
1. Script runs → error detected
2. LLM analyses error and generates a fix
3. Fix validated and tested in Docker sandbox
4. Fixed script saved; iterations logged

---

## Model Selection

The agent defaults to `qwen3:8b`. Use `--model` to switch:

```bash
# Linux/macOS — explicitly use qwen3:8b
python3 ESIB_AiCodingAgent.py --generate "..." --model qwen3:8b

# Windows — explicitly use qwen3:8b
python ESIB_AiCodingAgent.py --generate "..." --model qwen3:8b

# Linux/macOS — use qwen2.5-coder:7b (e.g. if qwen3 is unavailable or slow)
python3 ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b

# Windows — use qwen2.5-coder:7b
python ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b
```

### If `qwen3:8b` is not available on your machine

If you only have `qwen2.5-coder:7b` installed, always pass `--model qwen2.5-coder:7b`:

```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "Create a calculator" --model qwen2.5-coder:7b
python3 ESIB_AiCodingAgent.py --fix buggy.py --model qwen2.5-coder:7b

# Windows
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
# Linux/macOS
python3 ESIB_AiCodingAgent.py --help
# Windows
python ESIB_AiCodingAgent.py --help

# Verbose logging (shows all pipeline stages)
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "..." --verbose
python3 ESIB_AiCodingAgent.py --fix script.py --verbose
# Windows
python ESIB_AiCodingAgent.py --generate "..." --verbose
python ESIB_AiCodingAgent.py --fix script.py --verbose

# Save generated script to a custom path
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "..." --output my_script.py
# Windows
python ESIB_AiCodingAgent.py --generate "..." --output my_script.py

# Run built-in demo
# Linux/macOS
python3 ESIB_AiCodingAgent.py --demo
python3 ESIB_AiCodingAgent.py --demo --demo-mode generate
python3 ESIB_AiCodingAgent.py --demo --demo-mode debug
# Windows
python ESIB_AiCodingAgent.py --demo
python ESIB_AiCodingAgent.py --demo --demo-mode generate
python ESIB_AiCodingAgent.py --demo --demo-mode debug

# System health check
# Linux/macOS
python3 pre_check.py
# Windows
python pre_check.py
```

---

## Troubleshooting

### "Docker not running"

```bash
# Windows/macOS: Open Docker Desktop and wait for it to start
# Linux:
sudo systemctl start docker
```

### "Ollama not responding"

```bash
# Check
curl http://localhost:11434

# Start it (Linux/macOS):
ollama serve &
# Windows: find Ollama in Start menu or system tray
```

### Model not found

```bash
# See what is installed
ollama list

# Pull missing models
ollama pull qwen3:8b
ollama pull qwen2.5-coder:7b

# If only qwen2.5-coder is available, always add --model:
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b
# Windows
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
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "Create a CSV parser"
python3 ESIB_AiCodingAgent.py --generate "Build a to-do list manager with SQLite"
python3 ESIB_AiCodingAgent.py --generate "Create a REST API with authentication, rate limiting, and database integration"

# Windows
python ESIB_AiCodingAgent.py --generate "Create a CSV parser"
python ESIB_AiCodingAgent.py --generate "Build a to-do list manager with SQLite"
python ESIB_AiCodingAgent.py --generate "Create a REST API with authentication, rate limiting, and database integration"
```

### Try debug mode

```bash
# Linux/macOS — create a buggy script
cat > buggy.py << 'EOF'
def divide(a, b):
    return a / b

print(divide(10, 0))
EOF

# Fix it automatically (Linux/macOS)
python3 ESIB_AiCodingAgent.py --fix buggy.py

# Windows — create a buggy script (save the lines above to buggy.py manually, then run:)
python ESIB_AiCodingAgent.py --fix buggy.py
```

### Check pipeline statistics

After each run, `logs/pipeline_run_stats.jsonl` is updated:

```bash
# Linux/macOS
cat logs/pipeline_run_stats.jsonl

# Windows
type logs\pipeline_run_stats.jsonl
```

Each entry records: `run_id`, `timestamp`, `status`, `stage reached`, `token usage`, `estimated cost`, and a `summary` with the generated file path, function count, and class count.

> **Note:** Cost is "equivalent cloud pricing" — estimates what the same tokens would cost on a commercial API. Since you are running Ollama locally, your actual cost is $0.

### Customise model / timeouts

```bash
# Linux/macOS
export OLLAMA_MODEL=qwen3:8b              # or qwen2.5-coder:7b
export LLM_TIMEOUT=300

# Windows CMD
set OLLAMA_MODEL=qwen3:8b
set LLM_TIMEOUT=300

# Windows PowerShell
$env:OLLAMA_MODEL="qwen3:8b"
$env:LLM_TIMEOUT="300"
```

---

## Verification Checklist

- [ ] `python3 pre_check.py` (Linux/macOS) / `python pre_check.py` (Windows) — all green
- [ ] `docker ps` — no errors
- [ ] `curl http://localhost:11434` — returns "Ollama is running"
- [ ] `ollama list` — shows at least `qwen3:8b`
- [ ] Generation mode creates a working script in `src/generation/generated_code/`
- [ ] Debug mode fixes a broken script
- [ ] `logs/pipeline_run_stats.jsonl` is updated after each run

---

**You're all set! Start generating and debugging code.**
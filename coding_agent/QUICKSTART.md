# Quick Start Guide

Get the ESIB AI Coding Agent running in under 10 minutes.

---

## Prerequisites Check

**BEFORE running setup, verify these are installed and running:**

### 1. Python 3.8+

```bash
python --version
```
**Expected:** `Python 3.8.x` or higher

**If not installed:**
- Download from [python.org](https://python.org)
- **Windows:** Check "Add Python to PATH" during installation
- Restart terminal after installation

---

### 2. Docker Desktop (Running)

```bash
docker ps
```
**Expected:** Table of containers (even if empty) without errors

**If error or not installed:**

**Windows/Mac:**
1. Download [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Install and restart computer
3. **Start Docker Desktop** (important!)
4. Wait for "Docker Desktop is running" message

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

**If error or not installed:**

**Windows:**
1. Download from [ollama.com/download](https://ollama.com/download)
2. Run installer
3. Ollama starts automatically on port 11434

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS:**
1. Download from [ollama.com/download](https://ollama.com/download)
2. Install .dmg file

**To start Ollama (Linux/Mac):**
```bash
ollama serve &
```

---

## Installation

### Windows (PowerShell or CMD)

```powershell
# 1. Clone repository
git clone https://github.com/Joedaoud128/FYP.git
cd FYP\coding_agent

# 2. Run setup (takes 5-10 min, downloads ~10GB models)
.\setup.bat

# 3. Verify installation
python pre_check.py
```

### Linux / macOS

```bash
# 1. Clone repository
git clone https://github.com/Joedaoud128/FYP.git
cd FYP/coding_agent

# 2. Make setup executable
chmod +x setup.sh

# 3. Run setup (takes 5-10 min, downloads ~10GB models)
./setup.sh

# 4. Verify installation
python pre_check.py
```

---

## What Setup Does

The automated setup script:

1. ✅ **Creates virtual environment** (.venv)
2. ✅ **Installs Python dependencies** (pyyaml)
3. ✅ **Pulls AI models** (qwen3:8b ~4.7GB, qwen2.5-coder:7b ~4.7GB)
4. ✅ **Builds Docker image** (agent-sandbox)
5. ✅ **Creates required directories** (logs/, demos/, docs/)
6. ✅ **Verifies system health**

**Total time:** 5-10 minutes  
**Total download:** ~10GB

---

## First Run - Generation Mode

Create code from natural language prompts.

### Simple Example

```bash
python ESIB_AiCodingAgent.py --generate "Create a simple calculator"
```

**What happens:**
1. LLM generates Python code
2. Code is validated by guardrails
3. Code runs in Docker sandbox
4. Working script saved to `src/generation/generated_code/`

### Complex Example

```bash
python ESIB_AiCodingAgent.py --generate "Build a web scraper that extracts article titles and summaries from a news website, handles pagination, and saves results to CSV"
```

### Using the Convenience Wrapper

**Windows:**
```powershell
.\run.bat generate "Create a REST API with error handling"
```

**Linux/Mac:**
```bash
./run.sh generate "Create a REST API with error handling"
```

---

## First Run - Debug Mode

Automatically detect and fix errors in broken scripts.

### Example with Demo Script

```bash
python ESIB_AiCodingAgent.py --fix demos/03_broken_script.py
```

**What happens:**
1. Script runs → error detected
2. LLM analyzes error and generates fix
3. Fix is validated
4. Fixed script tested
5. If successful, fixed version saved

### Using the Convenience Wrapper

**Windows:**
```powershell
.\run.bat fix demos\03_broken_script.py
```

**Linux/Mac:**
```bash
./run.sh fix demos/03_broken_script.py
```

---

## Model Selection

### Use Primary Model (qwen3:8b) - Better Quality

```bash
python ESIB_AiCodingAgent.py --generate "..." --model qwen3:8b
```

### Use Fallback Model (qwen2.5-coder:7b) - Faster

```bash
python ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b
```

### Check Available Models

```bash
ollama list
```

---

## Common Options

```bash
# Help
python ESIB_AiCodingAgent.py --help

# Verbose logging
python ESIB_AiCodingAgent.py --generate "..." --verbose
python ESIB_AiCodingAgent.py --fix script.py --verbose

# Different model
python ESIB_AiCodingAgent.py --generate "..." --model qwen3:8b

# System health check
python pre_check.py

# Using convenience wrapper
.\run.bat check          # Windows
./run.sh check           # Linux/Mac
```

---

## Troubleshooting

### Setup Fails with "Docker not running"

```bash
# Solution
# Windows/Mac: Open Docker Desktop and wait for it to start
# Linux: sudo systemctl start docker
```

### Setup Fails with "Ollama not responding"

```bash
# Check if Ollama is running
curl http://localhost:11434

# If not, start it:
# Windows: Check system tray, or Start menu → Ollama
# Linux/Mac: ollama serve &
```

### Model Download Fails

```bash
# Pull models manually
ollama pull qwen3:8b
ollama pull qwen2.5-coder:7b

# If network is slow, start with smaller model
ollama pull qwen2.5-coder:7b
```

### "Python not found"

```bash
# Add Python to PATH
# Windows: System Properties → Environment Variables → PATH
# Add: C:\Python3X\ and C:\Python3X\Scripts\

# Or reinstall Python with "Add to PATH" checked
```

**For complete troubleshooting:**
```bash
# See detailed troubleshooting guide
cat docs/TROUBLESHOOTING.md
```

---

## What You Get

After setup, you have:

```
coding_agent/
├── .venv/                          # Virtual environment
├── src/
│   ├── generation/
│   │   └── generated_code/         # Your generated scripts appear here
│   └── orchestrator/
│       └── memory_store/           # Error pattern memory
├── logs/                           # Execution logs + pipeline stats
│   └── pipeline_run_stats.jsonl   # Token usage & cost tracking
├── demos/                          # Example scripts
└── docker/                         # Sandbox container
```

---

## Next Steps

### 1. Try Generation Examples

```bash
# Simple
python ESIB_AiCodingAgent.py --generate "Create a CSV parser"

# Medium
python ESIB_AiCodingAgent.py --generate "Build a to-do list manager with SQLite"

# Complex
python ESIB_AiCodingAgent.py --generate "Create a REST API with authentication, rate limiting, and database integration"
```

### 2. Try Debug Mode

```bash
# Create a buggy script
cat > buggy.py << EOF
def divide(a, b):
    return a / b

print(divide(10, 0))
EOF

# Fix it automatically
python ESIB_AiCodingAgent.py --fix buggy.py
```

### 3. Check Pipeline Statistics

```bash
# View token usage and cost estimates
cat logs/pipeline_run_stats.jsonl

# Each entry shows:
# - run_id, timestamp
# - status (success/error)
# - stage reached
# - usage (input/output tokens)
# - cost (equivalent cloud pricing)
# - summary (file path, functions, classes)
```

### 4. Customize Configuration

```bash
# Set environment variables
export OLLAMA_MODEL=qwen3:8b
export LLM_TIMEOUT=300
export AGENT_WORKSPACE=/your/workspace

# Then run normally
python ESIB_AiCodingAgent.py --generate "..."
```

### 5. Read Documentation

```
docs/
├── TROUBLESHOOTING.md             # Solve common issues
├── IMPLEMENTATION_SUMMARY.md      # Technical details
├── WINDOWS_GUIDE.md               # Windows-specific notes
└── CROSS_PLATFORM_GUIDE.md        # Platform compatibility
```

---

## Performance Tips

### For Faster Generation

```bash
# Use smaller, faster model
python ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b

# Increase timeout for complex tasks
export LLM_TIMEOUT=300
```

### For Better Quality

```bash
# Use larger, more capable model
python ESIB_AiCodingAgent.py --generate "..." --model qwen3:8b

# Be more specific in prompts
python ESIB_AiCodingAgent.py --generate "Create a Python script that uses BeautifulSoup to scrape headlines from BBC News, saves to CSV with timestamp and URL columns"
```

---

## Verification Checklist

After setup, verify everything works:

- [ ] `python pre_check.py` shows all green checkmarks
- [ ] `docker ps` runs without errors
- [ ] `curl http://localhost:11434` returns "Ollama is running"
- [ ] `ollama list` shows `qwen3:8b` and `qwen2.5-coder:7b`
- [ ] Generation mode creates working code
- [ ] Debug mode fixes errors
- [ ] `logs/pipeline_run_stats.jsonl` exists and is updated after each run

---

## Understanding Pipeline Statistics

Each generation creates an entry in `logs/pipeline_run_stats.jsonl`:

```json
{
  "run_id": "gen_a1b2c3d4",
  "timestamp": "2026-04-21T12:00:00Z",
  "status": "success",
  "stage": 8,
  "duration_ms": 45230,
  "usage": {
    "input_tokens": 1250,
    "output_tokens": 850,
    "total_tokens": 2100
  },
  "cost": {
    "input_usd": 0.00025,
    "output_usd": 0.00068,
    "total_usd": 0.00093,
    "cumulative_usd": 0.05432
  },
  "summary": {
    "file_path": "src/generation/generated_code/generated_abc123_20260421.py",
    "functions_count": 3,
    "classes_count": 1
  },
  "features": {
    "prompt_injection_blocked": false,
    "stage6_syntax_repairs": 0,
    "stage6_used_fallback": false
  }
}
```

**Cost is "equivalent cloud pricing"** - estimates what this would cost using commercial LLM APIs (like GPT-4). Since you're running Ollama locally, actual cost is $0.

---

## Getting Help

If you encounter issues:

1. **Run health check:**
   ```bash
   python pre_check.py
   ```

2. **Check logs:**
   ```
   logs/generation_*_logs.log
   logs/debug_*_logs.log
   logs/pipeline_run_stats.jsonl
   ```

3. **Read troubleshooting:**
   ```bash
   cat docs/TROUBLESHOOTING.md
   ```

4. **Enable verbose output:**
   ```bash
   python ESIB_AiCodingAgent.py --generate "..." --verbose
   ```

---

**You're all set! Start generating and debugging code! 🚀**
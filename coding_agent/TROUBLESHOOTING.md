# Troubleshooting Guide

This guide helps resolve common issues with the ESIB AI Coding Agent.

---

## Table of Contents

1. [Setup Issues](#setup-issues)
2. [Docker Issues](#docker-issues)
3. [Ollama Issues](#ollama-issues)
4. [Model Issues](#model-issues)
5. [Generation Mode Issues](#generation-mode-issues)
6. [Debug Mode Issues](#debug-mode-issues)
7. [Network Issues](#network-issues)
8. [Platform-Specific Issues](#platform-specific-issues)

---

## Setup Issues

### "Virtual environment not found"

**Symptom:**
```
[ERROR] Virtual environment not found!
```

**Solution:**
```bash
# Run setup first
.\setup.bat          # Windows
./setup.sh           # Linux/macOS
```

---

### "Python not found" or Python version is too old

**Symptom:**
```
[X] Python 3.10 or higher not found!
```
or:
```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

The second error means Python 3.9 or older was used to create the venv. The `str | None` syntax used in the project requires 3.10+.

**Check your version:**
```bash
python3 --version    # Linux/macOS
python --version     # Windows
```

**macOS — install Python 3.10:**
```bash
brew install python@3.10
python3.10 --version   # verify
```
Then delete the old venv and re-run setup:
```bash
deactivate
rm -rf .venv
./setup.sh
```

**Linux — install Python 3.10:**
```bash
sudo apt-get install python3.10 python3.10-venv python3.10-pip
python3.10 --version   # verify
```
Then delete the old venv and re-run setup:
```bash
deactivate
rm -rf .venv
./setup.sh
```

**Windows:** Download Python 3.10+ from [python.org/downloads](https://python.org/downloads). During installation, check **"Add Python to PATH"**. Restart your terminal, then re-run `setup.bat`.

---

### Windows — venv not active when running commands

**Symptom:**  
Running `python ESIB_AiCodingAgent.py` gives `ModuleNotFoundError` for `yaml` or other dependencies, even after setup.

**Solution:**  
On Windows, CMD does not persist venv activation between sessions. Run `run.bat` first to open an activated shell:

```cmd
run.bat
```

Then type all Python commands inside that window. Do not close it during your session.

---

### Linux/macOS — venv not active when running commands

**Symptom:**  
After closing and reopening a terminal, `python3 ESIB_AiCodingAgent.py` gives `ModuleNotFoundError` for `yaml` or other dependencies.

**Solution:**  
The venv must be re-activated in each new terminal session. Use `run.sh` to open an interactive shell with the venv already active:

```bash
chmod +x run.sh
./run.sh
```

Or activate manually:

```bash
source .venv/bin/activate
```

You should see `(.venv)` at the start of your prompt. All subsequent Python commands go in that terminal.

---

### Linux — `python3-venv` not installed

**Symptom:**
```
Error: Command '[...] python3 -m venv .venv' returned non-zero exit status 1
```
or
```
The virtual environment was not created successfully because ensurepip is not available.
```

**Solution:**
```bash
sudo apt-get install python3-venv python3-pip
./setup.sh
```

---

### `setup.sh` — "Permission denied"

**Symptom:**
```
bash: ./setup.sh: Permission denied
```

**Solution:**
```bash
chmod +x setup.sh run.sh
./setup.sh
```

---

## Docker Issues

### Docker Not Installed

**Symptom:**
```
[X] Docker not found
```

**Solution:**

**Windows:**
1. Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
2. Install and restart your computer
3. Start Docker Desktop
4. Run setup again

**Linux:**
```bash
sudo apt-get update
sudo apt-get install docker.io
sudo systemctl start docker
sudo usermod -aG docker $USER
# Log out and log back in
```

**macOS:**
1. Download [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop)
2. Install and start Docker Desktop

---

### Docker Not Running

**Symptom:**
```
[X] Docker is installed but not running
```

**Solution:**

**Windows/macOS:** Open Docker Desktop and wait for the whale icon to be steady ("Docker Desktop is running").

**Linux:**
```bash
sudo systemctl start docker
sudo systemctl status docker
```

---

### "Permission denied" connecting to Docker daemon (Linux)

**Symptom:**
```
permission denied while trying to connect to the Docker daemon socket
```

**Solution:**
```bash
sudo usermod -aG docker $USER
# Log out and log back in, then test:
docker run hello-world
```

---

### Docker Image Build Fails

**Symptom:**
```
ERROR: failed to build agent-sandbox image
```

**Solution:**
```bash
# Clean Docker cache and rebuild from project root
docker system prune -a
docker build -t agent-sandbox -f docker/Dockerfile .
```

**macOS (Apple Silicon):**
```bash
docker build --platform linux/amd64 -t agent-sandbox -f docker/Dockerfile .
```

---

## Ollama Issues

### Ollama Not Installed

**Symptom:**
```
[X] Ollama not found
```

**Solution:**

**Windows:** Download from [ollama.com/download](https://ollama.com/download) and run the installer. Ollama starts automatically.

**Linux/macOS:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS (alternative):** Download the .dmg from [ollama.com/download](https://ollama.com/download).

---

### Ollama Not Running

**Symptom:**
```
[X] Ollama installed but not running on port 11434
```

**Solution:**

**Windows:** Check the system tray for the Ollama icon. If missing, open Start menu → Ollama.

**Linux/macOS:**
```bash
# Start in foreground (keep this terminal open)
ollama serve

# Or in background
nohup ollama serve > /dev/null 2>&1 &
```

**Verify:**
```bash
curl http://localhost:11434
# Expected: "Ollama is running"
```

---

### Port 11434 Already in Use

**Symptom:**
```
Error: listen tcp :11434: bind: address already in use
```

**Solution:**
```bash
# Find what is using port 11434
# Windows:
netstat -ano | findstr :11434
# Linux/macOS:
lsof -i :11434

# Or point the agent at a different port
export OLLAMA_BASE_URL=http://localhost:11435
```

---

## Model Issues

### Model Not Found

**Symptom:**
```
[X] Model 'qwen3:8b' not found
```
or the agent hangs/errors with an unrecognised model name.

**Solution — use the model you have:**
```bash
# Check what is installed
ollama list

# If only qwen2.5-coder:7b is listed, pass --model explicitly:
python3 ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b
python3 ESIB_AiCodingAgent.py --fix script.py --model qwen2.5-coder:7b
```

**Solution — download the missing model:**
```bash
ollama pull qwen3:8b
ollama pull qwen2.5-coder:7b
```

> **Important:** `qwen3:8b` is the default model. If it is not available on your machine, always add `--model qwen2.5-coder:7b` to every command.

---

### Only `qwen2.5-coder:7b` is Available

If you chose to skip `qwen3:8b` during setup (or cannot download it due to disk/network constraints), run every command with the explicit flag:

```bash
# Generate
python3 ESIB_AiCodingAgent.py --generate "Create a calculator" --model qwen2.5-coder:7b

# Debug
python3 ESIB_AiCodingAgent.py --fix buggy.py --model qwen2.5-coder:7b

# Demo
python3 ESIB_AiCodingAgent.py --demo --model qwen2.5-coder:7b
```

`qwen2.5-coder:7b` is fully capable of handling all project tasks.

---

### Model Download Fails / Network Error

**Symptom:**
```
Error pulling model: connection timeout
```

**Solutions:**

1. Check internet connection: `ping ollama.com`

2. Retry with a longer timeout:
   ```bash
   # Linux/macOS
   export OLLAMA_TIMEOUT=300
   ollama pull qwen3:8b

   # Windows PowerShell
   $env:OLLAMA_TIMEOUT="300"
   ollama pull qwen3:8b
   ```

3. Start with the smaller model first:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```

4. Use a proxy if needed:
   ```bash
   export HTTP_PROXY=http://proxy:port
   export HTTPS_PROXY=http://proxy:port
   ollama pull qwen3:8b
   ```

---

### Model Loading Timeout

**Symptom:**
```
TimeoutError: Model loading exceeded 180s
```

**Solution:**
```bash
# Increase timeout
export LLM_TIMEOUT=300   # Linux/macOS
set LLM_TIMEOUT=300      # Windows CMD

# Or switch to the smaller model
python3 ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b
```

---

## Generation Mode Issues

### "Generation timeout"

**Symptom:**
```
TimeoutError: LLM generation exceeded timeout
```

**Solution:**
```bash
export LLM_TIMEOUT=300

# Or simplify the prompt
python3 ESIB_AiCodingAgent.py --generate "Simple calculator"
```

---

### "Guardrails blocking code"

**Symptom:**
```
[Guardrails] DENY: <reason>
```

**Solution:**  
Check `guardrails_config.yaml`. If the block is a false positive, review the relevant policy:
```yaml
policies:
  PATH-01:
    enabled: true
    # Ensure workspace_root matches your actual working directory
```

---

### Generated Code Has Import Errors (ModuleNotFoundError)

**Symptom:**  
Generated code fails in Docker with `ModuleNotFoundError` for a third-party package.

**Solution:**
1. The orchestrator will automatically retry via the debugging loop.
2. If the error persists after retries, try the `--fix` mode on the generated file:
   ```bash
   python3 ESIB_AiCodingAgent.py --fix src/generation/generated_code/script.py
   ```
3. For packages the sandbox cannot install, simplify the prompt to avoid that library.

---

## Debug Mode Issues

### "LLM returns empty code"

**Symptom:**
```
[LLM Parse] Found code: 0 chars
[LLM Parse] JSON valid but corrected_code is empty!
```

**Solution:**
1. Try `qwen3:8b` if available — it produces more structured output:
   ```bash
   python3 ESIB_AiCodingAgent.py --fix script.py --model qwen3:8b
   ```
2. Simplify the test case — start with single-error scripts.

---

### "Code failed validation"

**Symptom:**
```
[Probabilistic] Code failed ast.parse validation
```

**Solution:**
1. Check logs for the specific syntax error.
2. Try a different model: `--model qwen3:8b` or `--model qwen2.5-coder:7b`.
3. Inspect LLM output in the session log under `logs/`.

---

### "Same error repeated 3 times"

**Symptom:**
```
Error: Same error repeated 3 times — aborting retry loop
```

**Solution:**  
The LLM could not fix the error within the retry budget.
1. Try a different model.
2. Manually inspect the script and simplify the problematic section.
3. Report the case with the session log attached.

---

## Network Issues

### "Cannot connect to Ollama"

**Symptom:**
```
Failed to connect to http://localhost:11434
```

**Solution:**
```bash
# Verify Ollama is running
curl http://localhost:11434

# Linux — allow port through firewall if needed
sudo ufw allow 11434

# Windows — check Windows Defender Firewall; allow Ollama through it
```

---

### "Docker network error"

**Symptom:**
```
Error response from daemon: network not found
```

**Solution:**
```bash
docker network prune
docker network create agent-network
```

---

## Platform-Specific Issues

### Windows: PowerShell `curl` Error

**Symptom:**
```
curl : The response content cannot be parsed because the Internet Explorer engine is not available
```

**Solution:** Use `curl.exe` instead of the PowerShell alias, or switch to CMD.

---

### Windows: PATH Issues

**Symptom:**
```
'python' is not recognized as an internal or external command
```

**Solution:**
1. Open Settings → System → Environment Variables.
2. Edit PATH — add `C:\Python3X\` and `C:\Python3X\Scripts\`.
3. Restart terminal.

---

### Windows: venv Not Persisting Across CMD Windows

**Symptom:**  
Every time you open a new CMD window, `pyyaml` or other imports fail.

**Solution:**  
Always use `run.bat` to open your working session. It activates the `.venv` and keeps the shell open:
```cmd
run.bat
```

---

### Linux/macOS: venv Not Persisting Across Terminal Sessions

**Symptom:**  
Opening a new terminal causes `ModuleNotFoundError` because the venv is no longer active.

**Solution:**  
Use `run.sh` to open an interactive shell with the venv pre-activated:
```bash
./run.sh
```

Or activate manually in each new session:
```bash
source .venv/bin/activate
```

You should see `(.venv)` at the start of your prompt. Keep this terminal open for your session.

---

### Linux: `python3-venv` Missing

**Symptom:**
```
The virtual environment was not created successfully because ensurepip is not available.
```

**Solution:**
```bash
sudo apt-get install python3-venv python3-pip
./setup.sh
```

---

### Linux: Scripts Not Executable

**Symptom:**
```
bash: ./setup.sh: Permission denied
bash: ./run.sh: Permission denied
```

**Solution:**
```bash
chmod +x setup.sh run.sh
./setup.sh
```

---

### macOS: Apple Silicon Platform Mismatch

**Symptom:**
```
Docker platform mismatch
WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64)
```

**Solution:**
```bash
docker build --platform linux/amd64 -t agent-sandbox -f docker/Dockerfile .
```

---

### Linux: `set -e` Causes Silent Script Exit

**Symptom:**  
`setup.sh` exits without error output partway through (e.g., after the Ollama check or model pull step).

**Cause:**  
An older version of `setup.sh` used `set -e`, which causes the script to exit on any non-zero return code — including normal "not found" checks.

**Solution:**  
Use the updated `setup.sh` (April 2026 version) which removes `set -e` and handles each check explicitly.

---

## Getting More Help

### Enable Verbose Logging

```bash
python3 ESIB_AiCodingAgent.py --generate "..." --verbose
python3 ESIB_AiCodingAgent.py --fix script.py --verbose
```

### Check Logs

```
logs/
├── generate_<script>_<timestamp>_logs.log
├── debug_<script>_<timestamp>_logs.log
└── pipeline_run_stats.jsonl
```

### System Health Check

```bash
python3 pre_check.py
```

Shows: Python version, Docker status, Ollama status, model availability, and dependency status.

---

### Report Issues

If problems persist:
1. Run `python3 pre_check.py` and copy the output.
2. Collect the relevant log from `logs/`.
3. Note your OS, Python version, Docker version, and which Ollama models are installed (`ollama list`).
4. Contact your supervisor or team.

---

## Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| Docker not running | Start Docker Desktop (Win/macOS) or `sudo systemctl start docker` (Linux) |
| Ollama not running | `ollama serve` (Linux/macOS) or check system tray (Windows) |
| `qwen3:8b` not found | `ollama pull qwen3:8b` or add `--model qwen2.5-coder:7b` |
| Only qwen2.5-coder available | Always pass `--model qwen2.5-coder:7b` |
| venv not active (Windows) | Run `run.bat` first |
| venv not active (Linux/macOS) | Run `./run.sh` or `source .venv/bin/activate` |
| Scripts not executable (Linux/macOS) | `chmod +x setup.sh run.sh` |
| `python3-venv` missing (Linux) | `sudo apt-get install python3-venv` |
| Docker permission denied (Linux) | `sudo usermod -aG docker $USER` then log out/in |
| Docker platform mismatch (Apple Silicon) | Add `--platform linux/amd64` to docker build |
| Setup fails | Check prerequisites, then run `python3 pre_check.py` |
| Generation timeout | Set `export LLM_TIMEOUT=300` |
| Debug fails / empty code | Try `--model qwen3:8b` or simplify the script |
| Same error 3 times | Try different model or fix manually |
| Permission denied (Linux) | `chmod +x setup.sh run.sh` |
| Network issues | Check firewall and proxy settings |

---

**Last Updated:** April 24, 2026  
**Version:** 1.1.0
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
./setup.sh           # Linux/Mac
```

---

### "Python not found" or "Python version mismatch"

**Symptom:**
```
Python 3.8 or higher required
```

**Solution:**
1. Install Python 3.8+ from [python.org](https://python.org)
2. Ensure Python is in your PATH:
   ```bash
   python --version    # Should show 3.8+
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
# Ubuntu/Debian
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
[X] Docker not running
→ Please start Docker Desktop
```

**Solution:**

**Windows/Mac:**
1. Open Docker Desktop application
2. Wait for "Docker Desktop is running" status
3. Run setup/pre-check again

**Linux:**
```bash
sudo systemctl start docker
sudo systemctl status docker
```

---

### "Permission denied" (Linux)

**Symptom:**
```
permission denied while trying to connect to the Docker daemon
```

**Solution:**
```bash
# Add your user to docker group
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
# Clean Docker cache and rebuild
docker system prune -a
docker build -t agent-sandbox -f docker/Dockerfile .
```

---

## Ollama Issues

### Ollama Not Installed

**Symptom:**
```
[X] Ollama not found
```

**Solution:**

**Windows:**
```powershell
# Download from https://ollama.com/download
# Run installer
# Ollama runs automatically on port 11434
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS:**
```bash
# Download from https://ollama.com/download
# Install .dmg file
```

---

### Ollama Not Running

**Symptom:**
```
[X] Ollama not responding on port 11434
```

**Solution:**

**Windows:**
- Ollama should start automatically
- Check system tray for Ollama icon
- If not running: Start menu → Ollama

**Linux/Mac:**
```bash
# Start Ollama service
ollama serve

# Or in background:
nohup ollama serve > /dev/null 2>&1 &
```

**Check if running:**
```bash
curl http://localhost:11434
# Should return: "Ollama is running"
```

---

### Port 11434 Already in Use

**Symptom:**
```
Error: listen tcp :11434: bind: address already in use
```

**Solution:**
```bash
# Find what's using port 11434
# Windows:
netstat -ano | findstr :11434

# Linux/Mac:
lsof -i :11434

# Kill the process or use different port
export OLLAMA_BASE_URL=http://localhost:11435
```

---

## Model Issues

### Model Not Found

**Symptom:**
```
[X] Model 'qwen3:8b' not found
```

**Solution:**
```bash
# Pull the model
ollama pull qwen3:8b

# If slow, try smaller model first
ollama pull qwen2.5-coder:7b
```

---

### Model Download Fails / Network Error

**Symptom:**
```
Error pulling model: connection timeout
```

**Solution:**

1. **Check internet connection**
   ```bash
   ping ollama.com
   ```

2. **Retry with timeout increase**
   ```bash
   # Linux/Mac
   export OLLAMA_TIMEOUT=300
   ollama pull qwen3:8b
   
   # Windows PowerShell
   $env:OLLAMA_TIMEOUT="300"
   ollama pull qwen3:8b
   ```

3. **Try alternative model**
   ```bash
   ollama pull qwen2.5-coder:7b  # Smaller, faster download
   ```

4. **Use proxy if needed**
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
export LLM_TIMEOUT=300  # 5 minutes

# Or use smaller model
python ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b
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
# Increase timeout
export LLM_TIMEOUT=300

# Or simplify prompt
python ESIB_AiCodingAgent.py --generate "Simple calculator"
```

---

### "Guardrails blocking code"

**Symptom:**
```
[Guardrails] DENY: <reason>
```

**Solution:**

Check `guardrails_config.yaml` and adjust policies:
```yaml
# If false positive, adjust patterns
policies:
  PATH-01:
    enabled: true
    # Check workspace_root matches your system
```

---

### Generated Code Not Running

**Symptom:**
```
Generated code has errors when executed
```

**Solution:**
1. Check if dependencies are installed
2. Try simpler prompt
3. Use `--model qwen3:8b` for better quality
4. Check Docker logs: `docker logs <container_id>`

---

## Debug Mode Issues

### "LLM returns empty code"

**Symptom:**
```
[LLM Parse] Found code: 0 chars
[LLM Parse] JSON valid but corrected_code is empty!
```

**Solution:**
1. **Update to latest debugging.py** (improved prompt)
2. **Try qwen3:8b model:**
   ```bash
   python ESIB_AiCodingAgent.py --fix script.py --model qwen3:8b
   ```
3. **Simplify test case** - start with single-error scripts

---

### "Code failed validation"

**Symptom:**
```
[Probabilistic] Code failed ast.parse validation
```

**Solution:**
1. Check logs for syntax errors
2. Try different model: `--model qwen3:8b`
3. Manually inspect LLM output in logs

---

### "Same error repeated 3 times"

**Symptom:**
```
Error: Same error repeated 3 times
```

**Solution:**
1. The LLM couldn't fix the error
2. Try qwen3:8b: `--model qwen3:8b`
3. Fix manually and report the case

---

## Network Issues

### "Cannot connect to Ollama"

**Symptom:**
```
Failed to connect to http://localhost:11434
```

**Solution:**
```bash
# Check Ollama is running
curl http://localhost:11434

# Check firewall
# Windows: Allow Ollama through Windows Firewall
# Linux: sudo ufw allow 11434
```

---

### "Docker network error"

**Symptom:**
```
Error response from daemon: network not found
```

**Solution:**
```bash
# Recreate Docker network
docker network prune
docker network create agent-network
```

---

## Platform-Specific Issues

### Windows: PowerShell curl Error

**Symptom:**
```
curl : The response content cannot be parsed because the Internet Explorer engine is not available
```

**Solution:**
- **Already fixed in latest code** - uses `curl.exe` instead of PowerShell alias
- Or run from CMD instead of PowerShell

---

### Windows: PATH Issues

**Symptom:**
```
'python' is not recognized as an internal or external command
```

**Solution:**
1. Add Python to PATH:
   - Windows Settings → System → Environment Variables
   - Edit PATH, add: `C:\Python3X\` and `C:\Python3X\Scripts\`
2. Restart terminal

---

### Linux: Permission Denied

**Symptom:**
```
PermissionError: [Errno 13] Permission denied
```

**Solution:**
```bash
# For Docker
sudo usermod -aG docker $USER
# Log out and back in

# For files
chmod +x setup.sh
chmod +x run.sh
```

---

### macOS: Apple Silicon Issues

**Symptom:**
```
Docker platform mismatch
```

**Solution:**
```bash
# Ensure Docker Desktop is ARM64 version
# Or add platform flag:
docker build --platform linux/amd64 -t agent-sandbox -f docker/Dockerfile .
```

---

## Getting More Help

### Enable Verbose Logging

```bash
python ESIB_AiCodingAgent.py --fix script.py --verbose
```

### Check Logs

```
logs/
├── generation_<prompt_hash>_<timestamp>_logs.log
└── debug_<script>_<timestamp>_logs.log
```

### System Health Check

```bash
python pre_check.py
```

Shows:
- Python version
- Docker status
- Ollama status
- Model availability
- Dependencies

---

### Report Issues

If problems persist:
1. Run health check: `python pre_check.py`
2. Collect logs from `logs/` directory
3. Note your system (Windows/Linux/Mac, versions)
4. Contact your supervisor or team

---

## Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| Docker not running | Start Docker Desktop |
| Ollama not running | `ollama serve` |
| Model missing | `ollama pull qwen3:8b` |
| Setup fails | Check prerequisites, run `pre_check.py` |
| Generation timeout | Increase `LLM_TIMEOUT=300` |
| Debug fails | Try `--model qwen3:8b` |
| Permission denied | Add to docker group, check file permissions |
| Network issues | Check firewall, proxy settings |

---

**Last Updated:** April 21, 2026  
**Version:** 1.0.0
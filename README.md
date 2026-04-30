# ESIB AI Coding Agent

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docker Hub](https://img.shields.io/badge/docker%20hub-mariasabbagh1%2Fesib--ai--agent-blue)](https://hub.docker.com/r/mariasabbagh1/esib-ai-agent)
[![Tests](https://github.com/Joedaoud128/FYP/actions/workflows/test.yml/badge.svg)](https://github.com/Joedaoud128/FYP/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/badge/coverage-48%25-brightgreen)](tests/)

> Autonomous LLM agent for proactive code generation and reactive debugging

**Project:** FYP 26/21 - École Supérieure d'Ingénieurs de Beyrouth (USJ)  
**Supervisor:** Mr. Anthony Assi

---

## Overview

ESIB AI Coding Agent is an autonomous AI system that generates Python code from natural language descriptions and automatically debugs broken scripts. The system uses local LLM execution via Ollama, runs code in hardened Docker containers, and implements a novel orchestration architecture with formal handoff protocols.

### Key Features

- 🤖 **Dual-Mode Operation**
  - **Generate Mode:** Natural language → working Python code
  - **Debug Mode:** Broken script → automatically fixed code

- 🔒 **Security-First Design**
  - Hardened Docker sandbox execution
  - Comprehensive guardrails engine
  - Network isolation and resource limits

- 🎯 **Intelligent Architecture**
  - 6-stage ReAct-style generation pipeline
  - Formal Schema A/B handoff protocol
  - Iterative debugging with same-error detection

- 🔄 **Model Flexibility**
  - Support for multiple LLM models
  - Easy model switching via `--model` CLI flag
  - Supported models: `qwen3:8b` (default), `qwen2.5-coder:7b`

- 🚀 **Production-Ready**
  - Pre-built Docker image on Docker Hub
  - One-command setup
  - Comprehensive health checks and structured logging
  - 309 automated tests with CI on every push

---

## Quick Start

**Full documentation:** See [QUICKSTART.md](QUICKSTART.md)

### Prerequisites

1. **Docker Desktop** — [Download here](https://www.docker.com/products/docker-desktop)
2. **Ollama** — [Download here](https://ollama.ai)

### Installation (5 minutes)

**Linux/macOS:**
```bash
git clone https://github.com/Joedaoud128/FYP.git
cd FYP
chmod +x setup.sh run.sh
./setup.sh
./run.sh
python3 pre_check.py     # verify everything is ready
```

**Windows:**
```cmd
git clone https://github.com/Joedaoud128/FYP.git
cd FYP
.\setup.bat
run.bat
python pre_check.py
```

The setup script will:
- ✅ Verify Docker and Ollama are running
- ✅ Create a Python virtual environment (`.venv`)
- ✅ Install Python dependencies
- ✅ Manage AI models intelligently — detects what is already installed and only prompts for what is missing
- ✅ Build the Docker sandbox image
- ✅ Create necessary directories

> **Model prompts during setup:** If only one model is present, setup asks if you want the other. If neither is present, it pulls `qwen3:8b` automatically, then asks about `qwen2.5-coder:7b`. Answer **N** to skip any optional download — you can always pull later.

### Activating the Virtual Environment

Both platforms work the same way: run the activation script at the start of each session, then run `pre_check.py` to confirm everything is healthy before starting work.

**Linux/macOS:**
```bash
# 1. Activate the virtual environment
./run.sh

# 2. Verify the system is healthy
python3 pre_check.py
```

**Windows:**
```cmd
:: 1. Activate the virtual environment
run.bat

:: 2. Verify the system is healthy
python pre_check.py
```

> `run.sh` and `run.bat` activate the `.venv` and open a persistent shell. Run them after setup and at the start of every new session. Always follow with `pre_check.py` — it confirms Docker, Ollama, and the model are all ready before you begin.

### Quick Demo

```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --demo

# Windows
python ESIB_AiCodingAgent.py --demo
```

### Basic Usage

**Generate code:**
```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "Write a script that fetches and displays the latest Microsoft stock price"
python3 ESIB_AiCodingAgent.py --generate "Write a CSV parser"

# Windows
python ESIB_AiCodingAgent.py --generate "Write a script that fetches and displays the latest Microsoft stock price"
python ESIB_AiCodingAgent.py --generate "Write a CSV parser"
```

**Debug code:**
```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --fix path/to/broken_script.py

# Windows
python ESIB_AiCodingAgent.py --fix path\to\broken_script.py
```

---

## Model Selection

The system defaults to `qwen3:8b`. Use `--model` to switch:

| Model | Size | Notes |
|-------|------|-------|
| `qwen3:8b` | ~5.0 GB | **Default** — pulled automatically during setup |
| `qwen2.5-coder:7b` | ~4.7 GB | Optional fallback — pull manually if needed |

```bash
# Linux/macOS — use qwen3:8b explicitly
python3 ESIB_AiCodingAgent.py --generate "Build a REST API" --model qwen3:8b

# Linux/macOS — use qwen2.5-coder (e.g. if qwen3 is unavailable)
python3 ESIB_AiCodingAgent.py --generate "Build a REST API" --model qwen2.5-coder:7b

# Windows — use qwen3:8b explicitly
python ESIB_AiCodingAgent.py --generate "Build a REST API" --model qwen3:8b

# Windows — use qwen2.5-coder (e.g. if qwen3 is unavailable)
python ESIB_AiCodingAgent.py --generate "Build a REST API" --model qwen2.5-coder:7b
```

> **If `qwen3:8b` is not available on your machine**, always add `--model qwen2.5-coder:7b` so the agent uses the correct model. Check available models with `ollama list`.

**Set a session default via environment variable:**
```bash
# Linux/macOS
export OLLAMA_MODEL=qwen3:8b              # use the default model
export OLLAMA_MODEL=qwen2.5-coder:7b      # or the fallback model

# Windows CMD
set OLLAMA_MODEL=qwen3:8b
set OLLAMA_MODEL=qwen2.5-coder:7b

# Windows PowerShell
$env:OLLAMA_MODEL="qwen3:8b"
$env:OLLAMA_MODEL="qwen2.5-coder:7b"
```

---

## Docker Hub Deployment

Our production-ready Docker image is available for faster setup:

**Repository:** [mariasabbagh1/esib-ai-agent](https://hub.docker.com/r/mariasabbagh1/esib-ai-agent)

**Benefits:**
- ✅ Faster setup (~30 seconds vs 2 minutes building locally)
- ✅ Guaranteed identical environment across machines
- ✅ Automatic fallback to local build if pull fails

**Manual pull (optional):**
```bash
docker pull mariasabbagh1/esib-ai-agent:latest
```

> The setup script handles this automatically.

---

## Architecture

### System Overview

```
User Input
    ↓
ESIB_AiCodingAgent.py  (Entry Point — CLI, TeeStream logging, session stats)
    ↓
Orchestrator  (Module 11 — Maria)
    ├── Generation Pipeline  (Module 3 — Joe)
    │   ├── Stage 1: Prompt validation & guardrails
    │   ├── Stage 2: Environment detection
    │   ├── Stage 3: Requirement parsing
    │   ├── Stage 4: ReAct planning (LLM + tools)
    │   ├── Stage 5: Library verification & venv setup
    │   └── Stage 6: Code assembly & syntax repair
    ├── Schema A → Schema B Handoff  (Module 11 — Maria)
    ├── Docker Executor  (Module 11 — Maria)
    │   └── Hardened sandbox execution
    ├── Debugging Service  (Module 4 — Raymond)
    │   └── Iterative self-correction loop
    └── Guardrails Engine  (Module 7 — Elise)
        └── Policy validation & whitelist enforcement
```

### Key Components

**Orchestrator (Module 11)** — Maria: dual-mode coordination, Schema A/B handoff protocol, retry loop with same-error detection, Docker + subprocess execution, structured logging (`agent_logger.py`), error pattern memory (`memory_store.py`).

**Generation (Module 3)** — Joe: 6-stage deterministic pipeline, ReAct-style tool usage at Stage 4, PyPI verification, guardrails integration.

**Debugging (Module 4)** — Raymond: deterministic + probabilistic fix strategies; full debugger service with LLM-based fallback.

**Guardrails (Module 7)** — Elise: command validation, policy-based security checks, whitelist enforcement.

**Docker Execution** — Maria: hardened sandbox with `--network none`, 512 MB RAM / 1 CPU limits, read-only filesystem + tmpfs, two-step volume-based package installs.

---

## Testing

The project includes a comprehensive automated test suite covering all core modules. Tests are split into three layers — **unit**, **integration**, and **system** — and run automatically on every push to `main` via GitHub Actions.

**Full testing guide:** See [TESTING.md](TESTING.md)

### Run the tests

```bash
# Install test dependencies (inside activated virtual environment)
pip install -r requirements-test.txt

# Run all unit and integration tests — no Ollama or Docker required, ~1 second
# Linux/macOS
pytest tests/unit tests/integration -v

# Windows
python -m pytest tests/unit tests/integration -v
```

### Test coverage at a glance

| Layer | Files | Tests | External services needed |
|-------|-------|-------|--------------------------|
| Unit | 6 | 228 | None |
| Integration | 3 | 61 | None |
| System | 3 | 20 | Docker (sandbox), Ollama (LLM tests) |
| **Total** | **12** | **309** | — |

### CI pipeline

Tests run automatically on every push to `main` via GitHub Actions across Python 3.10, 3.11, and 3.13. The pipeline has two stages:

- **Stage 1 — Fast Tests (parallel):** unit + integration tests across the Python matrix (~1 minute)
- **Stage 2 — Specialised jobs:** Docker Security Tests and Guardrails Integration run on every push; Generate Mode and Fix Mode tests are manually triggered (require live Ollama)

```bash
# Run Docker sandbox security tests (requires Docker)
pytest tests/system/test_docker_sandbox.py -v -m system

# Run system tests — CLI sanity only, no LLM needed
pytest tests/system -v -m "system and not slow"
```

---

## Project Structure

```
FYP/
├── ESIB_AiCodingAgent.py           # Main CLI entry point
├── pre_check.py                    # System health check
├── requirements.txt                # Runtime Python dependencies
├── requirements-test.txt           # Testing dependencies
├── pytest.ini                      # Pytest configuration
├── setup.sh / setup.bat            # One-command setup scripts
├── run.sh / run.bat                # Virtual environment activators
│
├── src/                            # Source code modules
│   ├── orchestrator/               # Orchestration core (Module 11)
│   │   ├── orchestrator.py
│   │   ├── orchestrator_handoff.py # Schema A/B handoff & validation
│   │   ├── agent_logger.py         # Structured JSON logger (Module 12)
│   │   └── memory_store.py         # Error pattern memory (Module 10)
│   ├── generation/                 # Code generation (Module 3)
│   │   └── generation.py
│   ├── debugging/                  # Debugging service (Module 4)
│   │   └── debugging.py
│   └── guardrails/                 # Security engine (Module 7)
│       ├── guardrails_engine.py
│       └── guardrails_config.yaml
│
├── docker/                         # Docker sandbox configuration
│   ├── Dockerfile                  # Hardened sandbox image definition
│   └── docker_executor.py          # Docker-based execution engine
│
├── demos/                          # Example scenarios
│   ├── 01_calculator.txt
│   ├── 02_web_scraper.txt
│   └── 03_broken_script.py
│
├── tests/                          # Automated test suite (309 tests)
│   ├── conftest.py                 # Shared fixtures
│   ├── unit/                       # Module-level isolation (228 tests)
│   │   ├── test_handoff_validator.py
│   │   ├── test_environment_preparer.py
│   │   ├── test_memory_store.py
│   │   ├── test_docker_executor_pure.py
│   │   ├── test_agent_logger.py
│   │   └── test_guardrails_engine.py
│   ├── integration/                # Multi-module wiring (61 tests)
│   │   ├── test_process_handoff.py
│   │   ├── test_orchestrator_logic.py
│   │   └── test_guardrails_integration.py
│   └── system/                     # End-to-end CLI (20 tests)
│       ├── test_cli_fix_mode.py
│       ├── test_cli_generate_mode.py
│       └── test_docker_sandbox.py
│
├── .github/                        # CI/CD configuration
│   └── workflows/
│       └── test.yml                # Automated on every push to main
│
└── logs/                           # Session logs & pipeline stats
    ├── agent_events.jsonl          # Structured event logs
    └── pipeline_run_stats.jsonl    # Performance metrics

---

## Usage Examples

### Generate code

```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "Create a web scraper that extracts the top 10 Hacker News stories with titles, URLs, and scores. Save to JSON."
python3 ESIB_AiCodingAgent.py --generate "Read a CSV file with sales data and create a bar chart of revenue by product. Use pandas and matplotlib."

# Windows
python ESIB_AiCodingAgent.py --generate "Create a web scraper that extracts the top 10 Hacker News stories with titles, URLs, and scores. Save to JSON."
python ESIB_AiCodingAgent.py --generate "Read a CSV file with sales data and create a bar chart of revenue by product. Use pandas and matplotlib."
```

### Debug a broken script

```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --fix demos/03_broken_script.py

# Windows
python ESIB_AiCodingAgent.py --fix demos\03_broken_script.py
```

### Use a specific model

```bash
# Linux/macOS
python3 ESIB_AiCodingAgent.py --generate "Build a REST API client" --model qwen2.5-coder:7b
python3 ESIB_AiCodingAgent.py --generate "Build a REST API client" --model qwen3:8b

# Windows
python ESIB_AiCodingAgent.py --generate "Build a REST API client" --model qwen2.5-coder:7b
python ESIB_AiCodingAgent.py --generate "Build a REST API client" --model qwen3:8b
```

---

## Command Reference

```bash
# ── Health check ──────────────────────────────────────────────────────────────
python3 pre_check.py          # Linux/macOS
python pre_check.py           # Windows

# ── Generate — default model (qwen3:8b) ───────────────────────────────────────
python3 ESIB_AiCodingAgent.py --generate "your prompt"    # Linux/macOS
python ESIB_AiCodingAgent.py --generate "your prompt"     # Windows

# ── Generate — specific model ─────────────────────────────────────────────────
python3 ESIB_AiCodingAgent.py --generate "your prompt" --model qwen2.5-coder:7b
python3 ESIB_AiCodingAgent.py --generate "your prompt" --model qwen3:8b

# ── Generate — save to custom path ────────────────────────────────────────────
python3 ESIB_AiCodingAgent.py --generate "your prompt" --output my_script.py

# ── Debug ─────────────────────────────────────────────────────────────────────
python3 ESIB_AiCodingAgent.py --fix script.py
python3 ESIB_AiCodingAgent.py --fix script.py --model qwen2.5-coder:7b

# ── Demo ──────────────────────────────────────────────────────────────────────
python3 ESIB_AiCodingAgent.py --demo
python3 ESIB_AiCodingAgent.py --demo --demo-mode generate
python3 ESIB_AiCodingAgent.py --demo --demo-mode debug

# ── Verbose logging ───────────────────────────────────────────────────────────
python3 ESIB_AiCodingAgent.py --generate "..." --verbose

# ── Help ──────────────────────────────────────────────────────────────────────
python3 ESIB_AiCodingAgent.py --help
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `qwen3:8b` | LLM model to use |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `MAX_DEBUG_ITERATIONS` | `10` | Max debugging attempts |
| `LLM_TIMEOUT` | `180` | LLM call timeout (seconds) |
| `AGENT_WORKSPACE` | (cwd) | Working directory for guardrails |

---

## System Requirements

### Minimum

- **OS:** Windows 10/11, macOS 12+, or Ubuntu 20.04+
- **RAM:** 8 GB
- **Disk:** 15 GB free
- **Docker:** 20.10+
- **Python:** 3.10+
- **Internet:** Required for first-time model download

### Recommended

- **RAM:** 16 GB
- **GPU:** NVIDIA with CUDA (optional — speeds up Ollama inference)

---

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the full guide.

### Quick fixes

**Docker not running:**
```bash
docker ps   # Must return a list (even empty), not an error
# Fix: Open Docker Desktop and wait for it to start
# Linux: sudo systemctl start docker
```

**Ollama not responding:**
```bash
curl http://localhost:11434
# Fix (Linux/macOS): ollama serve
# Fix (Windows): check system tray for Ollama icon
```

**Model not found / only qwen2.5-coder available:**
```bash
ollama list   # Check what is installed

# Run with whichever model is available
python3 ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b   # Linux/macOS
python ESIB_AiCodingAgent.py --generate "..." --model qwen2.5-coder:7b    # Windows

# Or pull qwen3:8b when internet is available
ollama pull qwen3:8b
```

---

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** — Complete setup and usage guide
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Detailed problem resolution
- **[TESTING.md](TESTING.md)** — Test suite architecture, inventory, and how to run

---

## Team

**FYP 26/21 — AI Coding Agent**  
École Supérieure d'Ingénieurs de Beyrouth (Université Saint-Joseph de Beyrouth)

| Name | Role |
|------|------|
| Maria Sabbagh | Orchestrator, Docker Execution, Logging, Memory (Modules 10–12) |
| Joe Anthony Daoud | Code Generation Pipeline (Module 3) |
| Raymond Rached | Debugging Service (Module 4) |
| Elise Nassar | Security & Guardrails (Module 7) |

**Supervisor:** Anthony Assi

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- **École Supérieure d'Ingénieurs de Beyrouth (ESIB / USJ)** — academic support
- **Anthony Assi** — project supervision
- **Ollama** — local LLM execution framework
- **Qwen Team** — qwen2.5-coder and qwen3 models

---

## Project Status

**Status:** ✅ Production Ready (v1.2.0)  
**Demo Date:** May 21, 2026  
**Docker Hub:** [mariasabbagh1/esib-ai-agent](https://hub.docker.com/r/mariasabbagh1/esib-ai-agent)  
**Repository:** [github.com/Joedaoud128/FYP](https://github.com/Joedaoud128/FYP)

---

*Last updated: April 30, 2026*
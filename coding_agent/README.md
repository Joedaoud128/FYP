# ESIB AI Coding Agent

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docker Hub](https://img.shields.io/badge/docker%20hub-mariasabbagh1%2Fesib--ai--agent-blue)](https://hub.docker.com/r/mariasabbagh1/esib-ai-agent)

> Autonomous LLM agent for proactive code generation and reactive debugging

**Project:** FYP 26/21 - École Supérieure d'Ingénieurs de Beyrouth (USJ)  
**Supervisor:** Anthony Assi

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
  - Easy model switching via CLI flag
  - Currently supports: `qwen2.5-coder:7b`, `qwen3:8b`

- 🚀 **Production-Ready**
  - Pre-built Docker image on Docker Hub
  - One-command setup
  - Comprehensive health checks

---

## Quick Start

### Prerequisites

1. **Docker Desktop** - [Download here](https://www.docker.com/products/docker-desktop)
2. **Ollama** - [Download here](https://ollama.ai)

### Installation (5 minutes)

```bash
# Clone the repository
git clone https://github.com/Joedaoud128/FYP.git
cd FYP/coding_agent

# Run setup (downloads models, sets up environment)
./setup.sh              # Linux/Mac
setup.bat               # Windows
```

The setup script will:
- ✅ Verify Docker and Ollama are running
- ✅ Download AI models (~10GB, first time only)
- ✅ Pull pre-built Docker image from Docker Hub
- ✅ Install Python dependencies
- ✅ Create necessary directories

### Quick Demo

```bash
# Run demo scenarios
./run.sh demo           # Linux/Mac
run.bat demo            # Windows
```

### Basic Usage

**Generate code:**
```bash
# Using convenience wrapper
./run.sh generate "Write a web scraper for Hacker News"

# Using direct entry point
python ESIB_AiCodingAgent.py --generate "Write a CSV parser"
```

**Debug code:**
```bash
# Using convenience wrapper
./run.sh debug path/to/broken_script.py

# Using direct entry point
python ESIB_AiCodingAgent.py --fix path/to/broken_script.py
```

**Full documentation:** See [QUICKSTART.md](QUICKSTART.md)

---

## Model Selection

The system supports multiple AI models for different use cases:

| Model | Size | Best For |
|-------|------|----------|
| `qwen2.5-coder:7b` | 4.7GB | Code generation, debugging (default) |
| `qwen3:8b` | 5.0GB | Complex logic, creative solutions |

**Switch models:**
```bash
# Using wrapper
./run.sh generate "Build a REST API" qwen3:8b

# Using direct entry point
python ESIB_AiCodingAgent.py --generate "Build a REST API" --model qwen3:8b
```

**Set default model:**
```bash
export OLLAMA_MODEL=qwen3:8b
python ESIB_AiCodingAgent.py --generate "your prompt"
```

---

## Docker Hub Deployment

Our production-ready Docker image is available for faster setup:

**Repository:** [mariasabbagh1/esib-ai-agent](https://hub.docker.com/r/mariasabbagh1/esib-ai-agent)

**Benefits:**
- ✅ Faster setup (~30 seconds vs 2 minutes building locally)
- ✅ Guaranteed identical environment across machines
- ✅ Automatic fallback to local build if needed

**Manual pull (optional):**
```bash
docker pull mariasabbagh1/esib-ai-agent:latest
```

**Note:** The setup script automatically handles this.

---

## Architecture

### System Overview

```
User Input
    ↓
ESIB_AiCodingAgent.py (Entry Point)
    ↓
Orchestrator (Module 11)
    ├── Generation Pipeline (Joe - Module 3)
    │   ├── Stage 1: Prompt validation
    │   ├── Stage 2: Environment detection
    │   ├── Stage 3: Requirement parsing
    │   ├── Stage 4: ReAct planning (tool usage)
    │   ├── Stage 5: Library verification & venv setup
    │   └── Stage 6: Code assembly
    ├── Docker Executor (Maria - Module 11)
    │   └── Hardened sandbox execution
    ├── Debugging Service (Raymond - Module 4)
    │   └── Iterative error correction
    └── Guardrails Engine (Elise - Module 7)
        └── Policy validation
```

### Key Components

**Orchestrator (Module 11)** - Maria
- Dual-mode pipeline coordination
- Schema A/B handoff protocol
- Retry logic with same-error detection
- Docker and subprocess execution

**Generation (Module 3)** - Joe
- 6-stage deterministic pipeline
- ReAct-style tool usage at Stage 4
- PyPI verification and venv creation
- Guardrails integration

**Debugging (Module 4)** - Raymond
- Deterministic + probabilistic fix strategies
- Path A: Full debugger service
- Path B: Fallback LLM-based debugging
- Hybrid validation approach

**Guardrails (Module 7)** - Elise
- Command validation engine
- Policy-based security checks
- Whitelist enforcement

**Docker Execution** - Maria
- Custom hardened sandbox
- Network isolation (`--network none`)
- Resource limits (512MB RAM, 1 CPU)
- Read-only filesystem with tmpfs

---

## Project Structure

```
coding_agent/
├── src/
│   ├── orchestrator/          # Orchestration & coordination
│   │   ├── orchestrator.py
│   │   ├── orchestrator_handoff.py
│   │   ├── agent_logger.py
│   │   └── memory_store.py
│   ├── generation/            # Code generation pipeline
│   │   └── generation.py
│   ├── debugging/             # Debugging service
│   │   ├── debugging.py
│   │   └── phase4/            # Raymond's debugger
│   └── guardrails/            # Security & validation
│       ├── guardrails_engine.py
│       └── guardrails_config.yaml
├── docker/
│   └── Dockerfile             # Hardened sandbox image
├── demos/                     # Example scenarios
│   ├── 01_calculator.txt
│   ├── 02_web_scraper.txt
│   └── 03_broken_script.py
├── docs/                      # Documentation
│   ├── DOCKER_HUB_GUIDE.md
│   └── IMPLEMENTATION_SUMMARY.md
├── ESIB_AiCodingAgent.py      # Main entry point
├── setup.sh / setup.bat       # Setup scripts
├── run.sh                     # Convenience wrapper
├── pre_check.py               # Health check
├── requirements.txt           # Python dependencies
├── QUICKSTART.md              # User guide
└── README.md                  # This file
```

---

## Usage Examples

### Example 1: Web Scraper

```bash
./run.sh generate "Create a web scraper that extracts the top 10 Hacker News stories with titles, URLs, and scores. Save to JSON."
```

**Output:** `generated_code/script.py` with fully functional scraper

### Example 2: Data Analysis

```bash
./run.sh generate "Read a CSV file with sales data (date, product, quantity, price) and create a bar chart of revenue by product. Use pandas and matplotlib."
```

**Output:** Complete data analysis script with visualization

### Example 3: Debugging

```bash
./run.sh debug demos/03_broken_script.py
```

**Output:** Fixed script with all errors resolved

### Example 4: Model Comparison

```bash
# Generate with default model
./run.sh generate "Build a REST API client for JSONPlaceholder" qwen2.5-coder:7b

# Generate with alternative model
./run.sh generate "Build a REST API client for JSONPlaceholder" qwen3:8b

# Compare outputs
diff generated_code/version1.py generated_code/version2.py
```

---

## Command Reference

### Setup & Health Check

```bash
./run.sh setup          # Run setup (first time)
./run.sh check          # Verify system health
```

### Code Generation

```bash
# Default model
./run.sh generate 'prompt'
python ESIB_AiCodingAgent.py --generate 'prompt'

# Specific model
./run.sh generate 'prompt' qwen3:8b
python ESIB_AiCodingAgent.py --generate 'prompt' --model qwen3:8b

# Save to custom location
python ESIB_AiCodingAgent.py --generate 'prompt' --output my_script.py
```

### Debugging

```bash
# Default model
./run.sh debug script.py
python ESIB_AiCodingAgent.py --fix script.py

# Specific model
./run.sh debug script.py qwen3:8b
python ESIB_AiCodingAgent.py --fix script.py --model qwen3:8b
```

### Demos

```bash
./run.sh demo           # Run all demo scenarios
```

### Help

```bash
./run.sh help
python ESIB_AiCodingAgent.py --help
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | LLM model to use |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `MAX_DEBUG_ITERATIONS` | `10` | Max debugging attempts |
| `DEBUG_TIMEOUT` | `30` | Debugging timeout (seconds) |

### Custom Configuration

```bash
# Set model
export OLLAMA_MODEL=qwen3:8b

# Use remote Ollama instance
export OLLAMA_BASE_URL=http://192.168.1.100:11434

# Adjust debugging limits
export MAX_DEBUG_ITERATIONS=15
export DEBUG_TIMEOUT=60
```

---

## System Requirements

### Minimum

- **OS:** Windows 10/11, macOS 12+, or Linux (Ubuntu 20.04+)
- **RAM:** 8GB
- **Disk:** 15GB free space
- **Docker:** Version 20.10+
- **Python:** 3.10+
- **Internet:** Required for first-time model download

### Recommended

- **RAM:** 16GB
- **Disk:** 20GB+ free space
- **GPU:** NVIDIA GPU with CUDA support (optional, for faster inference)

---

## Testing

### Health Check

```bash
./run.sh check
```

**Expected output:**
```
✅ Docker Engine         Docker is running
✅ Ollama Service        Ollama is running on port 11434
✅ AI Models             Both models available
✅ Docker Image          Docker image exists
✅ Python Dependencies   Dependencies installed

System is ready to run!
```

### Run Test Suite

```bash
# Unit tests (if available)
pytest tests/

# Integration test via demo
./run.sh demo
```

---

## Troubleshooting

### Common Issues

**Docker not running**
```bash
# Solution: Start Docker Desktop
docker ps  # Should show empty list, not error
```

**Ollama not responding**
```bash
# Linux/Mac: Start Ollama
ollama serve

# Windows: Ollama should auto-start; reinstall if needed

# Test
curl http://localhost:11434/api/tags
```

**Model not found**
```bash
# Download manually
ollama pull qwen2.5-coder:7b
ollama pull qwen3:8b

# Verify
ollama list
```

**Docker build fails**
```bash
# Check disk space
df -h  # Need 2GB+ free

# Build with verbose output
docker build -t mariasabbagh1/esib-ai-agent:latest -f docker/Dockerfile .
```

**For more troubleshooting:** See [QUICKSTART.md](QUICKSTART.md) troubleshooting section

---

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Complete setup and usage guide
- **[DOCKER_HUB_GUIDE.md](docs/DOCKER_HUB_GUIDE.md)** - Docker Hub deployment details
- **[IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md)** - Technical implementation overview

---

## Team

**FYP 26/21 - AI Coding Agent**  
École Supérieure d'Ingénieurs de Beyrouth (Université Saint-Joseph de Beyrouth)

- **Maria Sabbagh** - Orchestrator & Docker Execution (Module 11)
- **Joe Anthony Daoud** - Code Generation Pipeline (Module 3)
- **Raymond Rached** - Debugging Service (Module 4)
- **Elise Nassar** - Security & Guardrails (Module 7)

**Supervisor:** Anthony Assi

---

## Contributing

This is an academic final year project. For questions or collaboration:

1. Open an issue on GitHub
2. Contact the team via university email

---

## License

MIT License - See [LICENSE](LICENSE) file for details

---

## Acknowledgments

- **École Supérieure d'Ingénieurs de Beyrouth (ESIB)** - Academic support
- **Université Saint-Joseph de Beyrouth (USJ)** - Resources and guidance
- **Anthony Assi** - Project supervision and technical guidance
- **Ollama** - Local LLM execution framework
- **Qwen Team** - qwen2.5-coder and qwen3 models

---

## Citation

If you use this work in your research, please cite:

```bibtex
@project{esib-ai-agent-2026,
  title={AI Coding Agent: An Autonomous LLM Agent for Proactive Code Generation and Reactive Debugging},
  author={Sabbagh, Maria and Daoud, Joe Anthony and Rached, Raymond and Nassar, Elise},
  year={2026},
  school={École Supérieure d'Ingénieurs de Beyrouth, Université Saint-Joseph de Beyrouth},
  supervisor={Assi, Anthony},
  type={Final Year Project},
  number={FYP 26/21}
}
```

---

## Project Status

**Status:** ✅ Production Ready (v1.0.0)  
**Demo Date:** May 12, 2026  
**Docker Hub:** [mariasabbagh1/esib-ai-agent](https://hub.docker.com/r/mariasabbagh1/esib-ai-agent)  
**Repository:** [github.com/Joedaoud128/FYP](https://github.com/Joedaoud128/FYP)

---

*Last updated: April 18, 2026*

#!/usr/bin/env python3
"""
pre_check.py - System Health Check
===================================
Quick verification that all components are ready.
Does NOT fix problems - just reports status.

For setup/installation, use setup.sh instead.
"""

import subprocess
import sys


def check_docker():
    """Check if Docker is running"""
    try:
        subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            check=True,
            timeout=5
        )
        return True, "Docker is running"
    except subprocess.CalledProcessError:
        return False, "Docker command failed - is Docker Desktop running?"
    except FileNotFoundError:
        return False, "Docker not installed - install from docker.com"
    except subprocess.TimeoutExpired:
        return False, "Docker not responding - restart Docker Desktop"


def check_ollama():
    """Check if Ollama is accessible"""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            return True, "Ollama is running on port 11434"
        return False, "Ollama is not responding on port 11434"
    except FileNotFoundError:
        return False, "curl not found - cannot check Ollama (install curl or check manually)"
    except subprocess.TimeoutExpired:
        return False, "Ollama not responding - start with 'ollama serve'"


def check_models():
    """Check if required models are available"""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True,
            timeout=5,
            text=True
        )
        models_found = []
        if "qwen2.5-coder:7b" in result.stdout:
            models_found.append("qwen2.5-coder:7b")
        if "qwen3:8b" in result.stdout:
            models_found.append("qwen3:8b")
        
        if len(models_found) == 2:
            return True, f"Both models available: {', '.join(models_found)}"
        elif len(models_found) == 1:
            return True, f"Model available: {models_found[0]} (other model optional)"
        else:
            return False, "No models found - run setup.sh to download"
    except:
        return False, "Cannot check models - verify Ollama is running"


def check_docker_image():
    """Check if agent-sandbox image exists"""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", "agent-sandbox"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip():
            return True, "Docker image 'agent-sandbox' exists"
        return False, "Docker image not built - run setup.sh"
    except:
        return False, "Cannot check Docker images"


def check_python_deps():
    """Check if Python dependencies are installed"""
    try:
        import yaml
        return True, "Python dependencies installed (pyyaml found)"
    except ImportError:
        return False, "Missing dependencies - run: pip install -r requirements.txt"


def main():
    print("=" * 70)
    print("ESIB AI Coding Agent - Health Check")
    print("=" * 70)
    print()
    
    checks = [
        ("Docker Engine", check_docker),
        ("Ollama Service", check_ollama),
        ("AI Models", check_models),
        ("Docker Image", check_docker_image),
        ("Python Dependencies", check_python_deps),
    ]
    
    all_passed = True
    
    for name, check_func in checks:
        passed, message = check_func()
        status = "✅" if passed else "❌"
        print(f"{status} {name:20} {message}")
        if not passed:
            all_passed = False
    
    print()
    print("=" * 70)
    
    if all_passed:
        print("✅ System is ready to run!")
        print()
        print("Try:")
        print("  ./run.sh demo")
        print("  ./run.sh generate 'your prompt'")
        print("  python ESIB_AiCodingAgent.py --generate 'your prompt'")
        return 0
    else:
        print("❌ System is not ready")
        print()
        print("To fix: ./setup.sh")
        return 1


if __name__ == "__main__":
    sys.exit(main())

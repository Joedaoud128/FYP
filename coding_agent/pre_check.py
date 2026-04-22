#!/usr/bin/env python3
"""
pre_check.py - System Health Check
===================================
Quick verification that all components are ready.
Does NOT fix problems - just reports status.

For setup/installation, use setup.bat or setup.sh instead.
"""

import subprocess
import sys
import platform
import shutil
import os


def check_python():
    """Check Python version"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor} (3.8+ required)"


def check_disk_space():
    """Check available disk space"""
    try:
        free_bytes = shutil.disk_usage("/").free
        free_gb = free_bytes / (1024 ** 3)
        if free_gb < 10:
            return False, f"Low disk space: {free_gb:.1f}GB free (need 10GB+)"
        return True, f"{free_gb:.1f}GB free"
    except Exception:
        return False, "Could not check disk space"


def check_docker():
    """Check if Docker is running"""
    try:
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True, "Docker is running"
        return False, "Docker command failed - is Docker Desktop running?"
    except FileNotFoundError:
        return False, "Docker not installed - install from docker.com"
    except subprocess.TimeoutExpired:
        return False, "Docker not responding - restart Docker Desktop"
    except Exception as e:
        return False, f"Docker error: {str(e)[:50]}"


def check_ollama():
    """Check if Ollama is accessible"""
    # Try multiple methods to check Ollama
    try:
        # Try curl first (most reliable)
        curl_cmd = "curl.exe" if platform.system() == "Windows" else "curl"
        result = subprocess.run(
            [curl_cmd, "-s", "http://localhost:11434/api/tags"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout:
            return True, "Ollama is running on port 11434"
    except:
        pass
    
    # Try Python urllib as fallback
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            if "models" in data:
                return True, "Ollama is running on port 11434"
    except:
        pass
    
    return False, "Ollama is not responding on port 11434"


def check_models():
    """Check if required models are available"""
    try:
        curl_cmd = "curl.exe" if platform.system() == "Windows" else "curl"
        result = subprocess.run(
            [curl_cmd, "-s", "http://localhost:11434/api/tags"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if not result.stdout:
            return False, "Cannot check models - Ollama not responding"
        
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
            return False, "No models found - run setup.bat to download"
    except Exception as e:
        return False, f"Cannot check models: {str(e)[:50]}"


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
        return False, "Docker image not built - run setup.bat"
    except Exception:
        return False, "Cannot check Docker images"


def check_python_deps():
    """Check if Python dependencies are installed"""
    try:
        import yaml
        # Check psutil (optional)
        try:
            import psutil
            return True, "All dependencies installed (pyyaml, psutil)"
        except ImportError:
            return True, "Core dependencies installed (pyyaml)"
    except ImportError:
        return False, "Missing pyyaml - run: pip install -r requirements.txt"


def check_venv():
    """Check if virtual environment exists and is activated"""
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    venv_path = os.environ.get("VIRTUAL_ENV", "")
    if venv_path:
        return True, f"Virtual environment active: {os.path.basename(venv_path)}"
    elif in_venv:
        return True, "Virtual environment active"
    else:
        return False, "Not in virtual environment (run .venv\\Scripts\\activate on Windows)"


def main():
    print("=" * 70)
    print("ESIB AI Coding Agent - Health Check")
    print("=" * 70)
    print()
    
    # System info
    print(f"System: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print()
    
    checks = [
        ("Python Version", check_python),
        ("Virtual Environment", check_venv),
        ("Disk Space", check_disk_space),
        ("Docker Engine", check_docker),
        ("Ollama Service", check_ollama),
        ("AI Models", check_models),
        ("Docker Image", check_docker_image),
        ("Python Dependencies", check_python_deps),
    ]
    
    all_passed = True
    warnings = []
    
    for name, check_func in checks:
        passed, message = check_func()
        status = "✅" if passed else "❌" if "not" in message.lower() or "missing" in message.lower() else "⚠️"
        
        # Handle warnings differently
        if not passed and ("Low disk" in message or "optional" in message):
            warnings.append(f"{name}: {message}")
            status = "⚠️"
            passed = True  # Don't fail for warnings
        
        print(f"{status} {name:20} {message}")
        if not passed:
            all_passed = False
    
    print()
    print("=" * 70)
    
    if warnings:
        print("⚠️ Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()
    
    if all_passed:
        print("✅ System is ready to run!")
        print()
        print("Quick start:")
        print("  run.bat demo")
        print("  run.bat generate 'your prompt'")
        print("  python ESIB_AiCodingAgent.py --generate 'your prompt'")
        return 0
    else:
        print("❌ System is not ready")
        print()
        print("To fix issues:")
        print("  1. Run: setup.bat")
        print("  2. If setup fails, see TROUBLESHOOTING.md")
        print("  3. Ensure Docker Desktop is running")
        print("  4. Ensure Ollama is running (check system tray)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
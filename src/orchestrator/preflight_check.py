#!/usr/bin/env python3
"""
preflight_check.py — Pre-Demo Connectivity & Readiness Checker
===============================================================
Run this BEFORE attempting the full pipeline to verify:
  1. Ollama is reachable via SSH tunnel (localhost:11434)
  2. The correct model (qwen2.5-coder:7b) is available
  3. All Python modules can be imported
  4. Docker is available 
  5. Guardrails engine loads correctly
  6. A simple LLM call works end-to-end

Usage:
    python preflight_check.py
"""

import sys
import os
import json
import urllib.request
import urllib.error
import subprocess

# Setup path for imports from sibling modules
_HERE = os.path.dirname(os.path.abspath(__file__))
for _subdir in ["../generation", "../debugging", "../guardrails", "."]:
    _p = os.path.abspath(os.path.join(_HERE, _subdir))
    if _p not in sys.path:
        sys.path.insert(0, _p)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EXPECTED_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = []


def check(name, func):
    try:
        ok, msg = func()
        symbol = PASS if ok else FAIL
        results.append((name, ok, msg))
        print(f"  {symbol} {name}: {msg}")
        return ok
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"  {FAIL} {name}: {e}")
        return False


def check_ollama_reachable():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
        return True, f"Ollama responding at {OLLAMA_URL}"
    except Exception as e:
        return False, (
            f"Cannot reach Ollama at {OLLAMA_URL}. "
            f"Ensure SSH tunnel is active: ssh -R 11434:localhost:11434 <vm>"
        )


def check_model_available():
    try:
        # Use curl instead of urllib as urllib has issues with SSH tunnels
        result = subprocess.run(
            ["curl", "-s", f"{OLLAMA_URL}/api/tags"],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        models = [m["name"] for m in data.get("models", [])]
        base = EXPECTED_MODEL.split(":")[0]
        found = any(base in m for m in models)
        if found:
            return True, f"Model '{EXPECTED_MODEL}' found"
        else:
            return False, (
                f"Model '{EXPECTED_MODEL}' not found. "
                f"Available: {models}. "
                f"Run: ollama pull {EXPECTED_MODEL}"
            )
    except Exception as e:
        return False, f"Could not check models: {e}"


def check_llm_call():
    try:
        payload = json.dumps({
            "model": EXPECTED_MODEL,
            "messages": [
                {"role": "user", "content": "Reply with exactly: HELLO"}
            ],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 10},
        })
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", f"{OLLAMA_URL}/api/chat",
             "-H", "Content-Type: application/json",
             "-d", payload,
             "--max-time", "30"],
            capture_output=True, text=True, timeout=35
        )
        data = json.loads(result.stdout)
        reply = data.get("message", {}).get("content", "").strip()
        if reply:
            return True, f"LLM responded: '{reply[:50]}'"
        return False, "LLM returned empty response"
    except Exception as e:
        return False, f"LLM call failed: {e}"


def check_import(module_name, display_name=None):
    def _check():
        try:
            __import__(module_name)
            return True, "importable"
        except ImportError as e:
            return False, f"import failed: {e}"
    return check(display_name or module_name, _check)


def check_docker():
    import subprocess
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return True, "Docker daemon running"
        return False, "Docker installed but daemon not running"
    except FileNotFoundError:
        return False, "Docker not installed (optional for demo)"
    except Exception as e:
        return False, f"Docker check failed: {e}"


def check_guardrails():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        guardrails_dir = os.path.abspath(os.path.join(here, "..", "guardrails"))
        cfg = os.path.join(guardrails_dir, "guardrails_config.yaml")
        if not os.path.exists(cfg):
            return False, f"guardrails_config.yaml not found in {guardrails_dir}"

        sys.path.insert(0, guardrails_dir)
        from guardrails_engine import GuardrailsEngine
        engine = GuardrailsEngine(cfg)

        # Quick test
        result = engine.validate({
            "caller_service": "test",
            "raw_command": "python -V",
            "working_dir": "/tmp",
        })
        if result["status"] == "PASS":
            return True, "Engine loaded, test command PASSED"
        return False, f"Engine loaded but test failed: {result}"
    except Exception as e:
        return False, f"Failed: {e}"


def main():
    print(f"\n{'='*60}")
    print(f"  AI Coding Agent — Pre-Flight Check")
    print(f"  Ollama URL: {OLLAMA_URL}")
    print(f"  Expected Model: {EXPECTED_MODEL}")
    print(f"{'='*60}\n")

    print("[1/6] Ollama Connectivity")
    check("Ollama reachable", check_ollama_reachable)

    print("\n[2/6] Model Availability")
    check("Model available", check_model_available)

    print("\n[3/6] LLM End-to-End Call")
    check("LLM chat works", check_llm_call)

    print("\n[4/6] Python Imports")
    check_import("yaml", "PyYAML")
    check_import("guardrails_engine", "guardrails_engine.py")

    print("\n[5/6] Docker (optional)")
    check("Docker", check_docker)

    print("\n[6/6] Guardrails Engine")
    check("Guardrails validation", check_guardrails)

    # Summary
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f" ({failed} failed)")
    else:
        print(" — All clear! Ready for demo.")
    print(f"{'='*60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

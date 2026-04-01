#!/usr/bin/env python3
"""
pre_check.py — Pre-Demo Connectivity & Readiness Checker (v2)
====================================================================
Run this BEFORE the full pipeline to verify every system dependency.

Checks (updated for host-based production setup):
  1.  Ollama reachable via SSH tunnel (localhost:11434)
  2.  Required model available (qwen2.5-coder:7b)
  3.  LLM end-to-end call works
  4.  Required Python modules importable
  5.  Docker daemon running
  6.  Docker security flags supported (--tmpfs, --cap-drop, --pids-limit)
  7.  agent-sandbox Docker image built
  8.  Guardrails engine loads and passes a test command
  9.  ESIB_AiCodingAgent.py is present and importable
  10. Workspace write permissions OK

Changes from v1:
  - Added Docker image existence check (Check 7)
  - Added security flag smoke-test (Check 6): verifies --tmpfs nosuid,
    --cap-drop ALL, --security-opt no-new-privileges, --pids-limit, --user
    are all accepted by the local Docker daemon
  - Added ESIB_AiCodingAgent.py presence check (Check 9)
  - Added workspace write-permission check (Check 10)
  - Restructured output to show version info and environment context
  - Added RUNNING_IN_DOCKER env-var detection for container-aware output
  - Exit code 2 when only optional checks fail (Docker), 1 for critical

Usage:
    python pre_check.py
    python pre_check.py --strict    # fail on ANY check, including optional
"""

import sys
import os
import json
import urllib.request
import subprocess
import tempfile
import argparse

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
for _subdir in [".", "src/orchestrator", "src/generation", "src/debugging", "src/guardrails"]:
    _p = os.path.abspath(os.path.join(_HERE, _subdir))
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Configuration ──────────────────────────────────────────────────────────────
OLLAMA_URL     = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
EXPECTED_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
SANDBOX_IMAGE  = os.environ.get("SANDBOX_IMAGE", "agent-sandbox")
IN_DOCKER      = bool(os.environ.get("RUNNING_IN_DOCKER"))

# ── ANSI colours ───────────────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty() and not IN_DOCKER
PASS  = "\033[92m✓\033[0m" if _USE_COLOR else "[PASS]"
FAIL  = "\033[91m✗\033[0m" if _USE_COLOR else "[FAIL]"
WARN  = "\033[93m⚠\033[0m" if _USE_COLOR else "[WARN]"
SKIP  = "\033[90m–\033[0m" if _USE_COLOR else "[SKIP]"

results: list[tuple[str, bool, bool, str]] = []  # (name, ok, critical, msg)


# ── Check runner ──────────────────────────────────────────────────────────────
def check(name: str, func, critical: bool = True, optional: bool = False):
    """
    Run a check function and record the result.
    critical=True  → failure blocks the demo
    optional=True  → shown as WARN instead of FAIL on failure
    """
    try:
        ok, msg = func()
    except Exception as exc:
        ok, msg = False, str(exc)

    if ok:
        symbol = PASS
    elif optional:
        symbol = WARN
    else:
        symbol = FAIL

    results.append((name, ok, critical and not optional, msg))
    print(f"  {symbol} {name}: {msg}")
    return ok


# ── Individual check functions ─────────────────────────────────────────────────

def check_ollama_reachable():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            json.loads(resp.read())
        return True, f"Ollama responding at {OLLAMA_URL}"
    except Exception:
        return False, (
            f"Cannot reach Ollama at {OLLAMA_URL}. "
            "Ensure SSH tunnel is active: ssh -R 11434:localhost:11434 <vm-ip>"
        )


def check_model_available():
    try:
        result = subprocess.run(
            ["curl", "-s", f"{OLLAMA_URL}/api/tags"],
            capture_output=True, text=True, timeout=10
        )
        data   = json.loads(result.stdout)
        models = [m["name"] for m in data.get("models", [])]
        base   = EXPECTED_MODEL.split(":")[0]
        found  = any(base in m for m in models)
        if found:
            return True, f"Model '{EXPECTED_MODEL}' found"
        return False, (
            f"Model '{EXPECTED_MODEL}' not found. "
            f"Available: {models or '(none)'}. "
            f"Run: ollama pull {EXPECTED_MODEL}"
        )
    except Exception as exc:
        return False, f"Could not check models: {exc}"


def check_llm_call():
    try:
        payload = json.dumps({
            "model":   EXPECTED_MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: HELLO"}],
            "stream":  False,
            "options": {"temperature": 0.0, "num_predict": 10},
        })
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", f"{OLLAMA_URL}/api/chat",
             "-H", "Content-Type: application/json",
             "-d", payload, "--max-time", "30"],
            capture_output=True, text=True, timeout=35
        )
        data  = json.loads(result.stdout)
        reply = data.get("message", {}).get("content", "").strip()
        if reply:
            return True, f"LLM responded: '{reply[:50]}'"
        return False, "LLM returned empty response"
    except Exception as exc:
        return False, f"LLM call failed: {exc}"


def check_python_import(module_name: str):
    try:
        __import__(module_name)
        return True, "importable"
    except ImportError as exc:
        return False, f"import failed: {exc}"


def check_docker_daemon():
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=8)
        if r.returncode == 0:
            return True, "Docker daemon running"
        return False, "Docker installed but daemon not responding"
    except FileNotFoundError:
        return False, "Docker not installed"
    except Exception as exc:
        return False, f"Docker check failed: {exc}"


def check_docker_security_flags():
    """
    Smoke-test that the local Docker daemon accepts all hardened runtime flags
    from the docker_security_report (section 3.2).

    We run a minimal container with every security flag applied; if Docker
    rejects any flag the check fails with the offending flag name.

    Flags tested:
      --read-only, --network none, --cap-drop ALL,
      --security-opt no-new-privileges,
      --pids-limit 100, --user 1000:1000,
      --tmpfs /workspace:rw,noexec,nosuid,size=100m,
      --memory 512m, --memory-swap 512m, --cpus 1
    """
    try:
        cmd = [
            "docker", "run", "--rm",
            "--read-only",
            "--network", "none",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges=true",
            "--pids-limit", "100",
            "--user", "1000:1000",
            "--tmpfs", "/workspace:rw,noexec,nosuid,size=100m",
            "--memory", "512m",
            "--memory-swap", "512m",
            "--cpus", "1",
            "alpine",          # tiny image; must exist on host
            "echo", "security-flags-ok",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and "security-flags-ok" in r.stdout:
            return True, "All hardened Docker security flags accepted"
        return False, f"Flag test failed (rc={r.returncode}): {r.stderr.strip()[:200]}"
    except FileNotFoundError:
        return False, "Docker not available — cannot test security flags"
    except subprocess.TimeoutExpired:
        return False, "Security flag test timed out"
    except Exception as exc:
        return False, f"Security flag test error: {exc}"


def check_sandbox_image():
    """Verify the agent-sandbox Docker image has been built."""
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", SANDBOX_IMAGE],
            capture_output=True, timeout=10
        )
        if r.returncode == 0:
            return True, f"Image '{SANDBOX_IMAGE}' found"
        return False, (
            f"Image '{SANDBOX_IMAGE}' not found. "
            f"Build it: docker build -t {SANDBOX_IMAGE} ."
        )
    except FileNotFoundError:
        return False, "Docker not available"
    except Exception as exc:
        return False, f"Image check failed: {exc}"


def check_guardrails():
    try:
        guardrails_dir = os.path.abspath(os.path.join(_HERE, "..", "guardrails"))
        cfg_candidates = [
            os.path.join(_HERE, "guardrails_config.yaml"),
            os.path.join(_HERE, "src", "guardrails", "guardrails_config.yaml"), 
        ]
        cfg = next((c for c in cfg_candidates if os.path.exists(c)), None)
        if not cfg:
            return False, "guardrails_config.yaml not found"

        sys.path.insert(0, os.path.dirname(cfg))
        from guardrails_engine import GuardrailsEngine
        engine = GuardrailsEngine(cfg)
        result = engine.validate({
            "caller_service": "preflight",
            "raw_command":    "python -V",
            "working_dir":    tempfile.gettempdir(),
        })
        if result["status"] == "PASS":
            return True, "Engine loaded; test command validated OK"
        return False, f"Engine loaded but test command failed: {result}"
    except Exception as exc:
        return False, f"Guardrails check failed: {exc}"


def check_esib_agent_present():
    """Verify ESIB_AiCodingAgent.py exists in the same directory."""
    esib_path = os.path.join(_HERE, "ESIB_AiCodingAgent.py")
    if os.path.isfile(esib_path):
        return True, f"Found at {esib_path}"
    return False, (
        f"ESIB_AiCodingAgent.py not found in {_HERE}. "
        "This is the main entry point — ensure it is present."
    )


def check_workspace_writable():
    """Verify the process can create files in the working directory."""
    try:
        with tempfile.NamedTemporaryFile(dir=_HERE, delete=True) as tmp:
            tmp.write(b"preflight-write-test")
        return True, f"Write access confirmed in {_HERE}"
    except Exception as exc:
        return False, f"Cannot write to working directory: {exc}"


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Coding Agent — Pre-flight Check v2")
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero if ANY check fails, including optional ones."
    )
    args = parser.parse_args()

    print(f"\n{'='*65}")
    print(f"  AI Coding Agent — Pre-Flight Check v2")
    print(f"  FYP_26_21 | {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Ollama URL     : {OLLAMA_URL}")
    print(f"  Expected model : {EXPECTED_MODEL}")
    print(f"  Sandbox image  : {SANDBOX_IMAGE}")
    print(f"  Environment    : {'Docker container' if IN_DOCKER else 'host'}")
    print(f"{'='*65}\n")

    # ── 1. Ollama ──────────────────────────────────────────────────────────────
    print("[1/10] Ollama Connectivity")
    check("Ollama reachable", check_ollama_reachable, critical=True)

    # ── 2. Model ───────────────────────────────────────────────────────────────
    print("\n[2/10] Model Availability")
    check("Model available", check_model_available, critical=True)

    # ── 3. LLM call ───────────────────────────────────────────────────────────
    print("\n[3/10] LLM End-to-End Call")
    check("LLM chat works", check_llm_call, critical=True)

    # ── 4. Python imports ─────────────────────────────────────────────────────
    print("\n[4/10] Python Imports")
    check("PyYAML",              lambda: check_python_import("yaml"),              critical=True)
    check("guardrails_engine",   lambda: check_python_import("guardrails_engine"), critical=True)
    check("orchestrator",        lambda: check_python_import("orchestrator"),       critical=True)

    # ── 5. Docker daemon ──────────────────────────────────────────────────────
    print("\n[5/10] Docker Daemon")
    docker_ok = check("Docker daemon", check_docker_daemon, critical=False, optional=False)

    # ── 6. Docker security flags ──────────────────────────────────────────────
    print("\n[6/10] Docker Security Flags (section 3.2 hardening)")
    if docker_ok:
        check(
            "Security flags accepted",
            check_docker_security_flags,
            critical=False,
            optional=False,
        )
    else:
        print(f"  {SKIP} Security flags — skipped (Docker not available)")

    # ── 7. Sandbox image ──────────────────────────────────────────────────────
    print("\n[7/10] Docker Sandbox Image")
    if docker_ok:
        check("agent-sandbox image", check_sandbox_image, critical=False, optional=False)
    else:
        print(f"  {SKIP} Sandbox image — skipped (Docker not available)")

    # ── 8. Guardrails ─────────────────────────────────────────────────────────
    print("\n[8/10] Guardrails Engine")
    check("Guardrails validation", check_guardrails, critical=True)

    # ── 9. ESIB entry point ───────────────────────────────────────────────────
    print("\n[9/10] ESIB_AiCodingAgent.py Entry Point")
    check("ESIB agent script present", check_esib_agent_present, critical=True)

    # ── 10. Workspace write ───────────────────────────────────────────────────
    print("\n[10/10] Workspace Write Permissions")
    check("Workspace writable", check_workspace_writable, critical=True)

    # ── Summary ───────────────────────────────────────────────────────────────
    total    = len(results)
    passed   = sum(1 for _, ok, _, _ in results if ok)
    failed   = total - passed
    critical = sum(1 for _, ok, crit, _ in results if not ok and crit)
    optional = sum(1 for _, ok, crit, _ in results if not ok and not crit)

    print(f"\n{'='*65}")
    print(f"  Results  : {passed}/{total} passed", end="")
    if failed:
        parts = []
        if critical:
            parts.append(f"{critical} critical failed")
        if optional:
            parts.append(f"{optional} optional failed")
        print(f"  ({', '.join(parts)})")
    else:
        print("  — All clear! Ready to run ESIB_AiCodingAgent.py")

    if critical:
        print("\n  ✗ Critical failures detected. Resolve before running the agent.")
    elif optional and not args.strict:
        print("\n  ⚠ Optional checks failed (Docker). Agent may run in subprocess mode.")
    print(f"{'='*65}\n")

    if critical:
        return 1
    if optional and args.strict:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

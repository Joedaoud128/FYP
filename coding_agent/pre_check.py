#!/usr/bin/env python3
"""
pre_check.py — Environment Setup + Pre-Demo Readiness Checker (v3)
====================================================================
Two distinct responsibilities are kept clearly separated:

  SETUP ACTIONS  (--setup flag)
  ─────────────────────────────
  One-time actions that configure the environment before it can be used.
  Run once after cloning the repo, or whenever dependencies change.

  S1. Python version ≥ 3.11 enforced (hard requirement from proposal §3.3)
  S2. Docker daemon running           (required for sandbox image build)
  S3. pyyaml installed                (only pip dependency; auto-installed)
  S4. agent-sandbox image built       (auto-built if absent)

  READINESS CHECKS  (default mode)
  ─────────────────────────────────
  Passive verification that every system dependency is ready.
  Run before every demo to confirm nothing has regressed.

  1.  Ollama reachable at localhost:11434
  2.  Required model available (qwen2.5-coder:7b)
  3.  LLM end-to-end call works
  4.  Required Python modules importable (PyYAML, guardrails_engine, orchestrator)
  5.  Docker daemon running
  6.  Docker security flags supported (--tmpfs, --cap-drop, --pids-limit)
  7.  agent-sandbox Docker image built
  8.  Guardrails engine loads and passes a test command
  9.  ESIB_AiCodingAgent.py is present
  10. Workspace write permissions OK

Usage:
    python pre_check.py              # readiness checks only (pre-demo)
    python pre_check.py --setup      # run setup actions, then readiness checks
    python pre_check.py --strict     # fail on ANY check, including optional
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

# ── Setup constants ────────────────────────────────────────────────────────────
DOCKERFILE_DIR = _HERE          # Dockerfile lives alongside pre_check.py
MIN_PYTHON     = (3, 11)        # minimum version from proposal §3.3

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



# ═════════════════════════════════════════════════════════════════════════════
# SETUP ACTIONS  (--setup flag only)
# These functions PERFORM actions (install, build) rather than merely verify.
# They are called once before the readiness checks when --setup is passed.
# ═════════════════════════════════════════════════════════════════════════════

def setup_check_python_version():
    """
    S1 — Enforce Python ≥ 3.11 (hard requirement, proposal §3.3).
    This is a gate: if Python is too old, setup stops immediately because
    nothing else will work correctly.
    """
    major, minor = sys.version_info.major, sys.version_info.minor
    if (major, minor) >= MIN_PYTHON:
        return True, f"Python {major}.{minor}.{sys.version_info.micro} — meets requirement (≥ 3.11)"
    return False, (
        f"Python {major}.{minor} is too old. "
        f"This project requires Python ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]}. "
        f"Please upgrade your Python interpreter."
    )


def setup_check_docker_daemon():
    """
    S2 — Docker daemon must be running before the image can be built.
    Reuses the same logic as the readiness check but is called in setup
    context so failures are reported as setup blockers, not readiness warnings.
    """
    return check_docker_daemon()


def setup_ensure_pyyaml():
    """
    S3 — Ensure pyyaml is installed; auto-install if missing.
    pyyaml is the only pip dependency of the project (guardrails_engine.py
    imports yaml). Installing it here means the readiness check for
    guardrails will pass without manual intervention.
    """
    try:
        import yaml  # noqa: F401
        import importlib.metadata
        version = importlib.metadata.version("pyyaml")
        return True, f"pyyaml {version} already installed"
    except (ImportError, Exception):
        pass

    print("    → pyyaml not found. Installing...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyyaml>=6.0",
             "--quiet", "--disable-pip-version-check"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return True, "pyyaml installed successfully"
        return False, f"pip install pyyaml failed: {result.stderr.strip()[:200]}"
    except subprocess.TimeoutExpired:
        return False, "pip install timed out after 60s"
    except Exception as exc:
        return False, f"pip install failed: {exc}"


def setup_ensure_sandbox_image():
    """
    S4 — Build the agent-sandbox Docker image if it does not already exist.
    The Dockerfile must be present in the same directory as pre_check.py.
    Building is skipped (with a PASS) if the image already exists so that
    repeated --setup runs are fast.
    """
    # First confirm Docker is available
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=8, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False, "Docker not available — cannot build sandbox image"

    # Check whether image already exists
    inspect = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        capture_output=True, timeout=10,
    )
    if inspect.returncode == 0:
        return True, f"Image '{SANDBOX_IMAGE}' already exists — skipping build"

    # Image missing: build it
    dockerfile = os.path.join(DOCKERFILE_DIR, "Dockerfile")
    if not os.path.isfile(dockerfile):
        return False, (
            f"Dockerfile not found at {dockerfile}. "
            "Cannot build agent-sandbox image."
        )

    print(f"    → Building '{SANDBOX_IMAGE}' from {dockerfile} (this may take a minute)...")
    try:
        build = subprocess.run(
            ["docker", "build", "-t", SANDBOX_IMAGE, DOCKERFILE_DIR],
            capture_output=True, text=True, timeout=300,
        )
        if build.returncode == 0:
            return True, f"Image '{SANDBOX_IMAGE}' built successfully"
        return False, (
            f"docker build failed (rc={build.returncode}):\n"
            f"{build.stderr.strip()[:400]}"
        )
    except subprocess.TimeoutExpired:
        return False, "docker build timed out after 300s"
    except Exception as exc:
        return False, f"docker build error: {exc}"


def run_setup():
    """
    Execute all setup actions in order.
    Returns True if all critical setup steps passed, False otherwise.
    Prints a clear header/footer distinguishing setup from readiness checks.
    """
    print(f"\n{'='*65}")
    print(f"  SETUP ACTIONS  (--setup)")
    print(f"{'='*65}\n")

    setup_results = []

    def setup_step(label, func, critical=True):
        try:
            ok, msg = func()
        except Exception as exc:
            ok, msg = False, str(exc)
        symbol = PASS if ok else (FAIL if critical else WARN)
        print(f"  {symbol} {label}: {msg}")
        setup_results.append((label, ok, critical))
        return ok

    # S1 — Python version (gate: stop immediately if too old)
    py_ok = setup_step("S1 Python ≥ 3.11", setup_check_python_version, critical=True)
    if not py_ok:
        print(f"\n  ✗ Python version check failed. Upgrade Python before continuing.")
        print(f"{'='*65}\n")
        return False

    # S2 — Docker daemon
    docker_ok = setup_step("S2 Docker daemon running", setup_check_docker_daemon, critical=True)

    # S3 — pyyaml (non-fatal if Docker is down, can still install)
    setup_step("S3 pyyaml installed", setup_ensure_pyyaml, critical=True)

    # S4 — sandbox image (only if Docker is up)
    if docker_ok:
        setup_step("S4 agent-sandbox image", setup_ensure_sandbox_image, critical=False)
    else:
        print(f"  {SKIP} S4 agent-sandbox image — skipped (Docker not available)")

    # Summary
    passed  = sum(1 for _, ok, _ in setup_results if ok)
    failed  = sum(1 for _, ok, crit in setup_results if not ok and crit)
    total   = len(setup_results)

    print(f"\n  Setup: {passed}/{total} steps passed", end="")
    if failed:
        print(f"  ({failed} critical failed)")
    else:
        print("  — environment is ready")
    print(f"{'='*65}\n")

    return failed == 0


# ── Individual check functions ─────────────────────────────────────────────────

def check_ollama_reachable():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            json.loads(resp.read())
        return True, f"Ollama responding at {OLLAMA_URL}"
    except Exception:
        return False, (
            f"Cannot reach Ollama at {OLLAMA_URL}. "
            "Ensure Ollama is running locally: `ollama serve`"
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
        from pathlib import Path

        # Resolve all candidates to absolute, symlink-collapsed paths so
        # os.path.exists() is reliable regardless of CWD or symlinks.
        cfg_candidates = [
            Path(_HERE) / "guardrails_config.yaml",                          # flat layout (production)
            Path(_HERE) / ".." / "guardrails" / "guardrails_config.yaml",    # microservice layout
            Path(_HERE) / "src" / "guardrails" / "guardrails_config.yaml",   # src layout
        ]
        cfg_path = next((p.resolve() for p in cfg_candidates if p.exists()), None)
        if cfg_path is None:
            searched = [str(p.resolve()) for p in cfg_candidates]
            return False, f"guardrails_config.yaml not found. Searched: {searched}"

        cfg = str(cfg_path)

        # Guarantee _HERE and the config's directory are both importable,
        # regardless of which candidate matched.
        for import_dir in (_HERE, str(cfg_path.parent)):
            if import_dir not in sys.path:
                sys.path.insert(0, import_dir)

        # Force a fresh import in case a previous failed attempt was cached.
        sys.modules.pop("guardrails_engine", None)
        from guardrails_engine import GuardrailsEngine

        engine = GuardrailsEngine(cfg)
        result = engine.validate({
            "caller_service": "preflight",
            "raw_command":    "python -V",
            "working_dir":    tempfile.gettempdir(),
        })
        if result["status"] == "PASS":
            return True, f"Engine loaded from {cfg}; test command validated OK"
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
    parser = argparse.ArgumentParser(
        description="AI Coding Agent — Environment Setup + Pre-flight Check v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python pre_check.py           # readiness checks only (pre-demo)\n"
            "  python pre_check.py --setup   # setup actions + readiness checks\n"
            "  python pre_check.py --strict  # fail on ANY check"
        ),
    )
    parser.add_argument(
        "--setup", action="store_true",
        help=(
            "Run setup actions first (install pyyaml, build Docker image) "
            "then proceed with readiness checks. Safe to run repeatedly."
        ),
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero if ANY check fails, including optional ones."
    )
    args = parser.parse_args()

    # ── Setup phase (--setup only) ─────────────────────────────────────────────
    if args.setup:
        setup_ok = run_setup()
        if not setup_ok:
            print("  Setup did not complete successfully. Fix the issues above, then re-run.")
            return 1
        print("  Proceeding to readiness checks...\n")

    print(f"\n{'='*65}")
    print(f"  AI Coding Agent — Pre-Flight Check v3  (setup={getattr(args, 'setup', False)})")
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
        print("  — All clear! System is ready. Run: python ESIB_AiCodingAgent.py --demo")

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
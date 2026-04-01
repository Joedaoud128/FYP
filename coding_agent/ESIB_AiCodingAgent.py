#!/usr/bin/env python3
"""
ESIB_AiCodingAgent.py — AI Coding Agent Main Entry Point
=========================================================
Replaces demo_e2e.py as the canonical entry point for the AI Coding Agent.

This script is designed to run both on the host and inside a Docker
container. It exposes the full dual-mode interface specified in the FYP
project description (FYP_26_21) and produces structured logs to stdout
so that Docker log capture (docker logs <container>) works out of the box.

Usage:
    # Generate Mode — natural language to working Python script
    python ESIB_AiCodingAgent.py --generate "write a script that fetches the latest AAPL stock price"

    # Debug Mode — fix an existing broken script
    python ESIB_AiCodingAgent.py --fix mybrokencode.py

    # Demo Mode — run built-in Generate + Debug demos (no args needed)
    python ESIB_AiCodingAgent.py --demo

    # Demo Mode — only one mode
    python ESIB_AiCodingAgent.py --demo --demo-mode generate
    python ESIB_AiCodingAgent.py --demo --demo-mode debug

    # Verbose logging
    python ESIB_AiCodingAgent.py --generate "..." --verbose

    # Save generated script to a custom path
    python ESIB_AiCodingAgent.py --generate "..." --output /path/to/output.py

FYP Reference:
    Phase 5 — "This mode will be invoked with a specific target file
    (e.g., python ESIBaiAgent.py --fix mybrokencode.py)."
    Phase 6 — "Integrate both Generate Mode and Debug Mode into a single
    command-line tool."
"""

import os
import sys
import argparse
import logging
import tempfile
import time
from datetime import datetime
from pathlib import Path

# ── Ensure sibling modules are importable ─────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
for _subdir in [".", "src/orchestrator", "src/generation", "src/debugging", "src/guardrails"]:
    _p = os.path.abspath(os.path.join(_HERE, _subdir))
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Agent metadata ─────────────────────────────────────────────────────────────
AGENT_NAME    = "ESIB AI Coding Agent"
AGENT_VERSION = "1.0.0"
FYP_CODE      = "FYP_26_21"
LOGS_DIR      = Path(_HERE) / "logs"


# ── TeeStream — mirrors stdout to terminal + log file simultaneously ───────────
class _TeeStream:
    """
    Wraps an output stream so every write goes to both the original
    stream (terminal) and a log file at the same time.
    Used to capture all print() output alongside logging records
    without modifying any pipeline module.
    """
    def __init__(self, original, file_handle):
        self._orig = original
        self._file = file_handle

    def write(self, data: str):
        self._orig.write(data)
        self._file.write(data)
        self._file.flush()

    def flush(self):
        self._orig.flush()
        self._file.flush()

    def fileno(self):
        return self._orig.fileno()

    def isatty(self):
        return getattr(self._orig, "isatty", lambda: False)()

    def __getattr__(self, name):
        return getattr(self._orig, name)

# ── Logging setup — structured for Docker log capture ─────────────────────────
def _setup_logging(verbose: bool = False) -> logging.Logger:
    """
    Configure root logger so all pipeline modules (orchestrator, generation,
    debugging, guardrails) write to the same stream.

    When called after sys.stdout has been replaced with a _TeeStream, the
    StreamHandler automatically writes every log record to both the terminal
    and the open log file — no separate FileHandler required.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)   # sys.stdout may be _TeeStream here
    handler.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)-20s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    # Remove any handlers set up before (e.g. by orchestrator.py on import)
    root.handlers.clear()
    root.addHandler(handler)

    return logging.getLogger("ESIBAgent")


# ── Pretty-print helpers ───────────────────────────────────────────────────────

def _banner(title: str, width: int = 70) -> str:
    return f"\n{'='*width}\n  {title}\n{'='*width}"


def _section(title: str, width: int = 70) -> str:
    return f"\n{'-'*width}\n  {title}\n{'-'*width}"


def _print_result(mode: str, result: dict, start_time: float) -> None:
    """Print a human-readable summary of an orchestrator result."""
    elapsed  = time.time() - start_time
    status   = result.get("status", "unknown").upper()
    symbol   = "✓" if status == "SUCCESS" else "✗"
    task_id  = result.get("task_id", "N/A")

    print(_section(f"{symbol}  {mode.upper()} MODE — {status}  (task: {task_id}, {elapsed:.1f}s)"))

    if status == "SUCCESS":
        stdout = result.get("stdout", "").strip()
        if stdout:
            print(f"\n  --- Output ---\n{stdout}\n  --- End Output ---")

        if result.get("script_path"):
            print(f"\n  Generated script : {result['script_path']}")
        if result.get("fixed_script_path") and result["fixed_script_path"] != result.get("script_path"):
            print(f"  Fixed script     : {result['fixed_script_path']}")
        if result.get("iterations"):
            print(f"  Debug iterations : {result['iterations']}")
        if result.get("fix_method"):
            print(f"  Fix method       : {result['fix_method']}")
        if result.get("execution_time"):
            print(f"  Execution time   : {result['execution_time']:.2f}s")
        if result.get("functions"):
            print(f"  Functions        : {result['functions']}")
        if result.get("classes"):
            print(f"  Classes          : {result['classes']}")
    else:
        error = result.get("error", "Unknown error")
        print(f"\n  Error : {error}")
        if result.get("stderr"):
            print(f"\n  Stderr (truncated):\n{result['stderr'][:500]}")
        if result.get("stage"):
            print(f"  Failed at stage  : {result['stage']}")
        if result.get("iterations"):
            print(f"  Iterations tried : {result['iterations']}")


# ── Mode implementations ───────────────────────────────────────────────────────

def run_generate(prompt: str, output_path: str | None = None, logger: logging.Logger | None = None) -> dict:
    """
    Generate Mode: natural language → code → execute → debug if needed.
    Maps to: python ESIB_AiCodingAgent.py --generate "<prompt>"
    """
    from orchestrator import Orchestrator

    logger = logger or logging.getLogger("ESIBAgent.generate")
    logger.info("Generate Mode started")
    logger.info("Prompt: %s", prompt)

    start = time.time()
    print(_section(f"Generate Mode  |  {datetime.now().strftime('%H:%M:%S')}"))
    print(f"  Prompt : {prompt}\n")

    orch   = Orchestrator()
    result = orch.run_generate(prompt)

    # Optionally copy the generated script to a user-specified path
    if output_path and result.get("status") == "success" and result.get("script_path"):
        try:
            import shutil
            shutil.copy2(result["script_path"], output_path)
            result["output_path"] = output_path
            logger.info("Generated script saved to: %s", output_path)
        except Exception as e:
            logger.warning("Could not copy script to output path: %s", e)

    _print_result("generate", result, start)
    return result


def run_fix(script_path: str, logger: logging.Logger | None = None) -> dict:
    """
    Debug Mode: debug an existing broken script.
    Maps to: python ESIB_AiCodingAgent.py --fix mybrokencode.py
    """
    from orchestrator import Orchestrator

    logger = logger or logging.getLogger("ESIBAgent.debug")

    if not os.path.isfile(script_path):
        print(f"\n  ERROR: Script not found: {script_path}")
        return {"status": "error", "error": f"Script not found: {script_path}"}

    abs_path = os.path.abspath(script_path)
    logger.info("Debug Mode started")
    logger.info("Target script: %s", abs_path)

    start = time.time()
    print(_section(f"Debug Mode  |  {datetime.now().strftime('%H:%M:%S')}"))
    print(f"  Script : {abs_path}\n")

    orch   = Orchestrator()
    result = orch.run_debug(abs_path)

    _print_result("debug", result, start)
    return result


def run_demo(demo_mode: str = "both", logger: logging.Logger | None = None) -> dict:
    """
    Demo Mode: run built-in demo scenarios.
    Preserves the demo_e2e.py experience for presentations.
    """
    logger = logger or logging.getLogger("ESIBAgent.demo")
    results = {}

    # ── Demo Generate ──────────────────────────────────────────────────────────
    if demo_mode in ("generate", "both"):
        demo_prompt = (
            "Write a Python script that prints the first 20 Fibonacci numbers "
            "and their sum."
        )
        logger.info("Demo: running Generate Mode with built-in prompt")
        results["generate"] = run_generate(demo_prompt, logger=logger)

    # ── Demo Debug ─────────────────────────────────────────────────────────────
    if demo_mode in ("debug", "both"):
        broken_code = '''\
"""Demo broken script — has a missing import (numpy)."""
import math

def calculate_stats(numbers):
    """Calculate statistics using numpy."""
    import numpy as np
    arr = np.array(numbers)
    return {
        "mean":     float(np.mean(arr)),
        "std":      float(np.std(arr)),
        "total":    float(np.sum(arr)),
        "sqrt_sum": math.sqrt(float(np.sum(arr))),
    }

if __name__ == "__main__":
    data = list(range(1, 11))
    print("Input:", data)
    stats = calculate_stats(data)
    for k, v in stats.items():
        print(f"  {k}: {v:.4f}")
'''
        tmp_dir    = tempfile.mkdtemp(prefix="esib_demo_")
        broken_path = os.path.join(tmp_dir, "broken_stats.py")
        with open(broken_path, "w") as fh:
            fh.write(broken_code)

        logger.info("Demo: running Debug Mode with built-in broken script")
        print(f"\n  [Demo] Created broken script at: {broken_path}")
        print(f"  [Demo] Known issue: 'numpy' not installed\n")
        results["debug"] = run_fix(broken_path, logger=logger)

    return results


# ── Summary printer ────────────────────────────────────────────────────────────

def _print_summary(results: dict, total_elapsed: float) -> int:
    """Print final summary table and return exit code (0 = all OK)."""
    print(_banner(f"SUMMARY  |  total time: {total_elapsed:.1f}s"))
    all_ok = True
    for mode, result in results.items():
        status = result.get("status", "unknown").upper()
        symbol = "✓" if status == "SUCCESS" else "✗"
        print(f"\n  {symbol}  {mode.title():10s} : {status}")
        if status == "SUCCESS":
            if mode == "generate" and result.get("script_path"):
                print(f"       Script   : {result['script_path']}")
            if mode == "debug":
                fixed = result.get("fixed_script_path")
                orig  = result.get("script_path")
                if fixed and fixed != orig:
                    print(f"       Fixed    : {fixed}")
                if result.get("fix_method"):
                    print(f"       Method   : {result['fix_method']}")
        else:
            all_ok = False
            print(f"       Error    : {result.get('error', 'unknown')}")
    print()
    return 0 if all_ok else 1


# ── Log filename derivation ────────────────────────────────────────────────────
def _derive_log_filename(args: argparse.Namespace, results: dict, ts: str) -> str:
    """
    Build a descriptive log filename from the run mode and result.

    Patterns:
        generate_<script>_<ts>_logs.log   — generate mode
        debug_<script>_<ts>_logs.log      — fix/debug mode
        demo_<script>_<ts>_logs.log       — demo mode
        session_<ts>_logs.log             — fallback
    """
    if getattr(args, "generate", None):
        script_path = (results.get("generate") or {}).get("script_path")
        stem = Path(script_path).stem if script_path else "generate"
        return f"generate_{stem}_{ts}_logs.log"

    if getattr(args, "fix", None):
        return f"debug_{Path(args.fix).stem}_{ts}_logs.log"

    if getattr(args, "demo", False):
        gen_path = (results.get("generate") or {}).get("script_path")
        stem = Path(gen_path).stem if gen_path else "demo"
        return f"demo_{stem}_{ts}_logs.log"

    return f"session_{ts}_logs.log"


# ── CLI argument parser ────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ESIB_AiCodingAgent.py",
        description=(
            f"{AGENT_NAME} v{AGENT_VERSION} ({FYP_CODE})\n"
            "Dual-mode AI coding agent: Generate new code or fix broken scripts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ESIB_AiCodingAgent.py --generate "write a script that plots a sine wave"
  python ESIB_AiCodingAgent.py --fix mybrokencode.py
  python ESIB_AiCodingAgent.py --demo
  python ESIB_AiCodingAgent.py --demo --demo-mode generate
        """,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--generate", "-g",
        metavar="PROMPT",
        help="Generate Mode: provide a natural language description of the script to create.",
    )
    mode_group.add_argument(
        "--fix", "-f",
        metavar="SCRIPT",
        help="Debug Mode: path to a broken Python script to fix.",
    )
    mode_group.add_argument(
        "--demo",
        action="store_true",
        help="Demo Mode: run built-in Generate + Debug demonstrations.",
    )

    parser.add_argument(
        "--demo-mode",
        choices=["generate", "debug", "both"],
        default="both",
        help="Which demo to run (only used with --demo). Default: both.",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="PATH",
        default=None,
        help="(Generate Mode only) Copy the generated script to this path.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG-level logging from all pipeline modules.",
    )

    return parser


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = _build_parser()
    args   = parser.parse_args()

    # ── Session log setup ─────────────────────────────────────────────────────
    # Open a temp log file before anything is printed so the banner and all
    # subsequent output (print + logging from every pipeline module) is captured.
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _session_ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    _temp_log     = LOGS_DIR / f"session_{_session_ts}_logs.log"
    _log_fh       = _temp_log.open("w", encoding="utf-8")
    _orig_stdout  = sys.stdout
    sys.stdout    = _TeeStream(_orig_stdout, _log_fh)  # captures all print() output

    # _setup_logging creates StreamHandler(sys.stdout) which now points at
    # _TeeStream → every logger.info/warning/error also lands in the log file.
    logger = _setup_logging(verbose=args.verbose)

    wall_start = time.time()
    results    = {}
    exit_code  = 0

    try:
        # Header
        print(_banner(
            f"{AGENT_NAME} v{AGENT_VERSION}  |  {FYP_CODE}  |  "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ))

        # Log environment info (useful when running inside Docker)
        logger.info("Python     : %s", sys.version.split()[0])
        logger.info("Working dir: %s", os.getcwd())
        logger.info("Script dir : %s", _HERE)
        if os.environ.get("RUNNING_IN_DOCKER"):
            logger.info("Environment: Docker container")
        else:
            logger.info("Environment: host")

        # ── Dispatch ──────────────────────────────────────────────────────────
        if args.generate:
            results["generate"] = run_generate(
                prompt=args.generate,
                output_path=args.output,
                logger=logger,
            )

        elif args.fix:
            results["debug"] = run_fix(
                script_path=args.fix,
                logger=logger,
            )

        elif args.demo:
            results = run_demo(
                demo_mode=args.demo_mode,
                logger=logger,
            )

        # ── Summary & exit code ───────────────────────────────────────────────
        exit_code = _print_summary(results, time.time() - wall_start)

    except KeyboardInterrupt:
        print("\n\n  [Interrupted by user]")
        exit_code = 130

    except Exception as exc:
        logger.exception("Unhandled exception in agent main: %s", exc)
        exit_code = 1

    finally:
        # Restore stdout before renaming so the "saved to" message goes to
        # the terminal only (log file is already fully written at this point).
        sys.stdout = _orig_stdout
        _log_fh.flush()
        _log_fh.close()

        _final_name = _derive_log_filename(args, results, _session_ts)
        _final_path = LOGS_DIR / _final_name
        try:
            _temp_log.rename(_final_path)
        except OSError:
            _final_path = _temp_log   # keep temp name if rename fails
        print(f"\n[Log] Session log saved to: {_final_path}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

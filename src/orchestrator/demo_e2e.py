#!/usr/bin/env python3
"""
demo_e2e.py — End-to-End Demo Runner
=====================================
Demonstrates the full pipeline in both modes:
  Mode 1: Generate Mode — natural language → code → execute → debug if needed
  Mode 2: Debug Mode    — broken script → debug loop → fixed script

Usage:
    python demo_e2e.py                     # Run both demos
    python demo_e2e.py --mode generate     # Generate Mode only
    python demo_e2e.py --mode debug        # Debug Mode only
    python demo_e2e.py --prompt "Write a script that prints the first 20 fibonacci numbers"
"""

import os
import sys
import argparse
import tempfile
from datetime import datetime

# Ensure current directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def demo_generate(prompt=None):
    """Run Generate Mode demo."""
    from orchestrator import Orchestrator

    if prompt is None:
        prompt = "Write a Python script that prints the first 20 Fibonacci numbers"

    print(f"\n{'='*70}")
    print(f"  DEMO: Generate Mode")
    print(f"  Prompt: {prompt}")
    print(f"  Time: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*70}\n")

    orch = Orchestrator()
    result = orch.run_generate(prompt)

    print(f"\n{'='*70}")
    print(f"  GENERATE MODE RESULT: {result.get('status', 'unknown').upper()}")
    print(f"{'='*70}")

    if result.get("status") == "success":
        print(f"  Script: {result.get('script_path', 'N/A')}")
        print(f"  Functions: {result.get('functions', [])}")
        print(f"  Classes: {result.get('classes', [])}")
        print(f"  Execution Time: {result.get('execution_time', 'N/A'):.2f}s")
        print(f"\n  Output:\n{result.get('stdout', '(no output)')}")
    else:
        print(f"  Error: {result.get('error', 'Unknown')}")
        if result.get("stderr"):
            print(f"  Stderr: {result['stderr'][:300]}")

    return result


def demo_debug():
    """Run Debug Mode demo with a deliberately broken script."""
    from orchestrator import Orchestrator

    # Create a broken script with a missing import
    broken_code = '''"""Demo broken script — has a missing import."""
import math

def calculate_stats(numbers):
    """Calculate stats using numpy (not installed)."""
    import numpy as np
    arr = np.array(numbers)
    return {
        "mean": np.mean(arr),
        "std": np.std(arr),
        "sum": np.sum(arr),
        "sqrt_sum": math.sqrt(np.sum(arr)),
    }

if __name__ == '__main__':
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    print("Input:", data)
    result = calculate_stats(data)
    print("Stats:", result)
'''

    # Write to a temp file
    tmp_dir = tempfile.mkdtemp(prefix="demo_debug_")
    script_path = os.path.join(tmp_dir, "broken_stats.py")
    with open(script_path, "w") as f:
        f.write(broken_code)

    print(f"\n{'='*70}")
    print(f"  DEMO: Debug Mode")
    print(f"  Script: {script_path}")
    print(f"  Known issue: missing 'numpy' package")
    print(f"  Time: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*70}\n")

    orch = Orchestrator()
    result = orch.run_debug(script_path)

    print(f"\n{'='*70}")
    print(f"  DEBUG MODE RESULT: {result.get('status', 'unknown').upper()}")
    print(f"{'='*70}")

    if result.get("status") == "success":
        print(f"  Original Script: {result.get('script_path', 'N/A')}")
        if result.get('fixed_script_path') and result.get('fixed_script_path') != result.get('script_path'):
            print(f"  Fixed Script: {result.get('fixed_script_path', 'N/A')}")
        print(f"  Debug Iterations: {result.get('iterations', '?')}")
        if result.get('fix_method'):
            print(f"  Fix Method: {result.get('fix_method')}")
        print(f"\n  Output:\n{result.get('stdout', '(no output)')}")
    else:
        print(f"  Error: {result.get('error', 'Unknown')}")
        print(f"  Iterations Attempted: {result.get('iterations', '?')}")

    return result


def main():
    parser = argparse.ArgumentParser(description="End-to-End Demo Runner")
    parser.add_argument(
        "--mode", choices=["generate", "debug", "both"],
        default="both", help="Which demo to run"
    )
    parser.add_argument(
        "--prompt", type=str, default=None,
        help="Custom prompt for Generate Mode"
    )
    args = parser.parse_args()

    print(f"\n{'#'*70}")
    print(f"  AI Coding Agent — End-to-End Demo")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}")

    results = {}

    if args.mode in ("generate", "both"):
        results["generate"] = demo_generate(args.prompt)

    if args.mode in ("debug", "both"):
        results["debug"] = demo_debug()

    # Final summary
    print(f"\n{'#'*70}")
    print(f"  DEMO SUMMARY")
    print(f"{'#'*70}")
    for mode, result in results.items():
        status = result.get("status", "unknown").upper()
        symbol = "✓" if status == "SUCCESS" else "✗"
        print(f"  {symbol} {mode.title()} Mode: {status}")
        
        if status == "SUCCESS":
            if mode == "generate":
                script = result.get("script_path", "N/A")
                print(f"      Generated: {script}")
            elif mode == "debug":
                original = result.get("script_path", "N/A")
                fixed = result.get("fixed_script_path")
                print(f"      Original: {original}")
                if fixed and fixed != original:
                    print(f"      Fixed: {fixed}")
                if result.get('fix_method'):
                    print(f"      Method: {result.get('fix_method')}")
    print()

    all_ok = all(r.get("status") == "success" for r in results.values())
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

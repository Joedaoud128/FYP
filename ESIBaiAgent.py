from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.app.service import SelfCorrectionService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 5 debug entrypoint for Phase 4/5 self-correction workflow.")
    parser.add_argument("--fix", dest="target_file", required=True, help="Python file to execute and auto-fix.")
    parser.add_argument("--python", dest="python_executable", default=sys.executable, help="Python executable path.")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="llama3.2")
    parser.add_argument("--disable-llm-fallback", action="store_true")
    parser.add_argument("--check-runtime", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    service = SelfCorrectionService(
        python_executable=args.python_executable,
        workspace_root=str(PROJECT_ROOT),
        use_llm_fallback=not args.disable_llm_fallback,
        ollama_base_url=args.ollama_url,
        ollama_model=args.ollama_model,
        max_iterations=args.max_iterations,
        run_timeout_seconds=args.timeout,
    )

    if args.check_runtime and not service.is_runtime_healthy():
        print(
            json.dumps(
                {
                    "mode": "debug",
                    "runtime_healthy": False,
                    "message": "Local Ollama runtime is unavailable.",
                },
                indent=2,
            )
        )
        return 2

    result = service.run_target_file(args.target_file)
    outcome = service.to_outcome(result)

    print(
        json.dumps(
            {
                "mode": "debug",
                "success": outcome.success,
                "attempts": outcome.attempts,
                "failure_reason": outcome.failure_reason,
                "final_exit_code": outcome.final_exit_code,
                "final_stderr": outcome.final_stderr,
                "llm_fallback_used": result.llm_fallback_used,
            },
            indent=2,
        )
    )

    return 0 if outcome.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

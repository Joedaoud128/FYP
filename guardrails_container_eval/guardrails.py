
from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------
# CONFIG
# ---------------------------

WORKSPACE_ROOT = Path(os.environ.get("AGENT_WORKSPACE", os.getcwd())).resolve()
DENY_TOKENS = {";", "|", "&&", ">", ">>"}  # hard deny anywhere
MAX_FIND_DEPTH = 4
MAX_HEAD_TAIL_N = 5000
SAFE_PIP_PACKAGE_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")

@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    normalized_argv: Optional[List[str]] = None

# ---------------------------
# HELPERS
# ---------------------------

def _has_deny_tokens(argv: List[str]) -> bool:
    return any(tok in DENY_TOKENS for tok in argv)

def _is_within_workspace(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(WORKSPACE_ROOT)
        return True
    except Exception:
        return False

def _validate_path_arg(p: str) -> Tuple[bool, str, Optional[Path]]:
    if not p.strip():
        return False, "Empty path argument.", None
    if ".." in Path(p).parts:
        return False, "Path traversal ('..') is not allowed.", None

    candidate = (WORKSPACE_ROOT / p) if not os.path.isabs(p) else Path(p)
    if not _is_within_workspace(candidate):
        return False, f"Path escapes workspace: {p}", None
    return True, "OK", candidate.resolve(strict=False)

def _validate_int(s: str, lo: int, hi: int) -> Tuple[bool, str, Optional[int]]:
    try:
        n = int(s)
    except ValueError:
        return False, f"Expected integer, got '{s}'.", None
    if not (lo <= n <= hi):
        return False, f"Integer out of range [{lo}, {hi}]: {n}", None
    return True, "OK", n

# ---------------------------
# VALIDATORS (STRICT SHAPES)
# ---------------------------

def v_python(argv: List[str]) -> Decision:
    # python -V
    if argv == ["python", "-V"]:
        return Decision(True, "Allowed: python -V", argv)

    # python script.py
    if len(argv) == 2 and argv[0] == "python":
        ok, msg, p = _validate_path_arg(argv[1])
        if not ok:
            return Decision(False, msg)
        if p.suffix != ".py":
            return Decision(False, "Only .py scripts can be executed.")
        return Decision(True, "Allowed: python <script.py>", ["python", str(p)])

    # python -m py_compile file.py
    if len(argv) == 4 and argv[:3] == ["python", "-m", "py_compile"]:
        ok, msg, p = _validate_path_arg(argv[3])
        if not ok:
            return Decision(False, msg)
        if p.suffix != ".py":
            return Decision(False, "py_compile target must be a .py file.")
        return Decision(True, "Allowed: python -m py_compile <file.py>",
                        ["python", "-m", "py_compile", str(p)])

    # python -m pip install <package>
    if len(argv) == 5 and argv[:4] == ["python", "-m", "pip", "install"]:
        package_name = argv[4]
        if not SAFE_PIP_PACKAGE_RE.match(package_name):
            return Decision(False, "pip install package token contains unsupported characters.")
        return Decision(
            True,
            "Allowed: python -m pip install <package>",
            ["python", "-m", "pip", "install", package_name],
        )

    return Decision(False, "Blocked: python command shape not in allowlist.")

def v_pwd(argv: List[str]) -> Decision:
    return Decision(True, "Allowed: pwd", ["pwd"]) if argv == ["pwd"] else Decision(False, "Blocked: pwd takes no args.")

def v_ls(argv: List[str]) -> Decision:
    if argv == ["ls"]:
        return Decision(True, "Allowed: ls", argv)
    if argv == ["ls", "-la"]:
        return Decision(True, "Allowed: ls -la", argv)
    return Decision(False, "Blocked: only 'ls' or 'ls -la' are allowed.")

def v_cat(argv: List[str]) -> Decision:
    if len(argv) != 2 or argv[0] != "cat":
        return Decision(False, "Blocked: allowed shape is 'cat <file>'.")
    ok, msg, p = _validate_path_arg(argv[1])
    if not ok:
        return Decision(False, msg)
    if p.is_dir():
        return Decision(False, "Blocked: cat requires a file, not a directory.")
    return Decision(True, "Allowed: cat <file>", ["cat", str(p)])

def v_head(argv: List[str]) -> Decision:
    if len(argv) != 4 or argv[:2] != ["head", "-n"]:
        return Decision(False, "Blocked: allowed shape is 'head -n N <file>'.")
    okn, msgn, n = _validate_int(argv[2], 1, MAX_HEAD_TAIL_N)
    if not okn:
        return Decision(False, msgn)
    ok, msg, p = _validate_path_arg(argv[3])
    if not ok:
        return Decision(False, msg)
    if p.is_dir():
        return Decision(False, "Blocked: head requires a file, not a directory.")
    return Decision(True, "Allowed: head -n N <file>", ["head", "-n", str(n), str(p)])

def v_tail(argv: List[str]) -> Decision:
    if len(argv) != 4 or argv[:2] != ["tail", "-n"]:
        return Decision(False, "Blocked: allowed shape is 'tail -n N <file>'.")
    okn, msgn, n = _validate_int(argv[2], 1, MAX_HEAD_TAIL_N)
    if not okn:
        return Decision(False, msgn)
    ok, msg, p = _validate_path_arg(argv[3])
    if not ok:
        return Decision(False, msg)
    if p.is_dir():
        return Decision(False, "Blocked: tail requires a file, not a directory.")
    return Decision(True, "Allowed: tail -n N <file>", ["tail", "-n", str(n), str(p)])

def v_wc(argv: List[str]) -> Decision:
    if len(argv) != 3 or argv[:2] != ["wc", "-l"]:
        return Decision(False, "Blocked: allowed shape is 'wc -l <file>'.")
    ok, msg, p = _validate_path_arg(argv[2])
    if not ok:
        return Decision(False, msg)
    if p.is_dir():
        return Decision(False, "Blocked: wc -l requires a file, not a directory.")
    return Decision(True, "Allowed: wc -l <file>", ["wc", "-l", str(p)])

def v_stat(argv: List[str]) -> Decision:
    if len(argv) != 2 or argv[0] != "stat":
        return Decision(False, "Blocked: allowed shape is 'stat <path>'.")
    ok, msg, p = _validate_path_arg(argv[1])
    if not ok:
        return Decision(False, msg)
    return Decision(True, "Allowed: stat <path>", ["stat", str(p)])

def v_grep(argv: List[str]) -> Decision:
    # grep -n pattern file
    if len(argv) == 4 and argv[:2] == ["grep", "-n"]:
        pattern = argv[2]
        ok, msg, p = _validate_path_arg(argv[3])
        if not ok:
            return Decision(False, msg)
        if p.is_dir():
            return Decision(False, "Blocked: grep -n requires a file.")
        return Decision(True, "Allowed: grep -n <pattern> <file>", ["grep", "-n", pattern, str(p)])

    # grep -R -n pattern path
    if len(argv) == 5 and argv[:3] == ["grep", "-R", "-n"]:
        pattern = argv[3]
        ok, msg, p = _validate_path_arg(argv[4])
        if not ok:
            return Decision(False, msg)
        return Decision(True, "Allowed: grep -R -n <pattern> <path>", ["grep", "-R", "-n", pattern, str(p)])

    return Decision(False, "Blocked: grep command shape not in allowlist.")

def v_find(argv: List[str]) -> Decision:
    # find path -maxdepth N -type f
    if len(argv) != 6 or argv[0] != "find" or argv[2] != "-maxdepth" or argv[4:] != ["-type", "f"]:
        return Decision(False, "Blocked: allowed shape is 'find <path> -maxdepth N -type f'.")
    ok, msg, p = _validate_path_arg(argv[1])
    if not ok:
        return Decision(False, msg)
    okn, _, n = _validate_int(argv[3], 0, MAX_FIND_DEPTH)
    if not okn:
        return Decision(False, f"Blocked: find maxdepth must be <= {MAX_FIND_DEPTH}.")
    return Decision(True, "Allowed: find <path> -maxdepth N -type f",
                    ["find", str(p), "-maxdepth", str(n), "-type", "f"])

def v_mkdir(argv: List[str]) -> Decision:
    if len(argv) != 3 or argv[:2] != ["mkdir", "-p"]:
        return Decision(False, "Blocked: allowed shape is 'mkdir -p <dir>'.")
    ok, msg, p = _validate_path_arg(argv[2])
    if not ok:
        return Decision(False, msg)
    return Decision(True, "Allowed: mkdir -p <dir>", ["mkdir", "-p", str(p)])

def v_cp(argv: List[str]) -> Decision:
    if len(argv) != 3 or argv[0] != "cp":
        return Decision(False, "Blocked: allowed shape is 'cp <src> <dst>' (no flags).")
    ok1, msg1, src = _validate_path_arg(argv[1])
    if not ok1:
        return Decision(False, msg1)
    ok2, msg2, dst = _validate_path_arg(argv[2])
    if not ok2:
        return Decision(False, msg2)
    return Decision(True, "Allowed: cp <src> <dst>", ["cp", str(src), str(dst)])

def v_mv(argv: List[str]) -> Decision:
    if len(argv) != 3 or argv[0] != "mv":
        return Decision(False, "Blocked: allowed shape is 'mv <src> <dst>' (no flags).")
    ok1, msg1, src = _validate_path_arg(argv[1])
    if not ok1:
        return Decision(False, msg1)
    ok2, msg2, dst = _validate_path_arg(argv[2])
    if not ok2:
        return Decision(False, msg2)
    return Decision(True, "Allowed: mv <src> <dst>", ["mv", str(src), str(dst)])

def v_rm(argv: List[str]) -> Decision:
    # rm file  (no flags)
    if len(argv) != 2 or argv[0] != "rm":
        return Decision(False, "Blocked: allowed shape is 'rm <file>' (no flags).")
    ok, msg, p = _validate_path_arg(argv[1])
    if not ok:
        return Decision(False, msg)
    if p.is_dir():
        return Decision(False, "Blocked: rm is file-only (directories not allowed).")
    return Decision(True, "Allowed: rm <file>", ["rm", str(p)])

def v_chmod(argv: List[str]) -> Decision:
    # chmod u+rw file OR chmod u-rw file
    if len(argv) != 3 or argv[0] != "chmod":
        return Decision(False, "Blocked: allowed shape is 'chmod u±rw <file>'.")
    if argv[1] not in {"u+rw", "u-rw"}:
        return Decision(False, "Blocked: chmod mode must be exactly u+rw or u-rw.")
    ok, msg, p = _validate_path_arg(argv[2])
    if not ok:
        return Decision(False, msg)
    if p.is_dir():
        return Decision(False, "Blocked: chmod is file-only here.")
    return Decision(True, "Allowed: chmod u±rw <file>", ["chmod", argv[1], str(p)])

ALLOWLIST = {
    "python": v_python,
    "pwd": v_pwd,
    "ls": v_ls,
    "cat": v_cat,
    "head": v_head,
    "tail": v_tail,
    "wc": v_wc,
    "stat": v_stat,
    "grep": v_grep,
    "find": v_find,
    "mkdir": v_mkdir,
    "cp": v_cp,
    "mv": v_mv,
    "rm": v_rm,
    "chmod": v_chmod,
}

# ---------------------------
# PUBLIC API
# ---------------------------

def gate(cmdline: str) -> Decision:
    """Return ALLOW/BLOCK + reason for ONE command line."""
    try:
        argv = shlex.split(cmdline, posix=True)
    except ValueError as e:
        return Decision(False, f"BLOCK: parse error: {e}")

    if not argv:
        return Decision(False, "BLOCK: empty command.")

    if _has_deny_tokens(argv):
        return Decision(False, "BLOCK: contains denied operator token (; | && > >>).")

    validator = ALLOWLIST.get(argv[0])
    if not validator:
        return Decision(False, f"BLOCK: '{argv[0]}' not in allowlist (DEFAULT DENY).")

    d = validator(argv)
    # normalize reason prefix
    if d.allowed and not d.reason.startswith("ALLOW"):
        return Decision(True, "ALLOW: " + d.reason.replace("Allowed:", "").strip(), d.normalized_argv)
    if not d.allowed and not d.reason.startswith("BLOCK"):
        return Decision(False, "BLOCK: " + d.reason.replace("Blocked:", "").strip(), None)
    return d

# ---------------------------
# CLI
# ---------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Guardrails Gate: accept or block one command.")
    parser.add_argument("command", help="Command line in quotes, e.g., \"ls -la\"")
    parser.add_argument("--exec", action="store_true", help="Actually execute if allowed (shell=False).")
    parser.add_argument("--timeout", type=int, default=30, help="Execution timeout seconds (only with --exec).")
    args = parser.parse_args()

    decision = gate(args.command)
    print(decision.reason)

    if args.exec:
        if not decision.allowed or not decision.normalized_argv:
            raise SystemExit(126)
        proc = subprocess.run(
            decision.normalized_argv,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=args.timeout,
            shell=False,
        )
        print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=os.sys.stderr)
        raise SystemExit(proc.returncode)

if __name__ == "__main__":
    main()
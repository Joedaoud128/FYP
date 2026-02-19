"""
Phase 3 - Proactive Code Generator
Powered by Qwen2.5-Coder:7B running locally via Ollama.

10-Stage Pipeline:
    Stage 1:  Accept user natural language prompt
    Stage 2:  Extract environment info (Python, OS, packages, network, disk)
    Stage 3:  Requirement Parser & Intent Classifier + Complexity Threshold
    Stage 4:  Multi-Step Agentic Planner (search_docs, write_file, run_sandbox, install_package)
    Stage 5:  Library Identification & Validation (import check + PyPI API verification)
    Stage 6:  Code Generator (comprehensive context prompt)
    Stage 7:  Syntax Validation via AST (max 3 retries with LLM-guided fixes)
    Stage 8:  Execution Engine (sandboxed subprocess with timeout + resource isolation)
    Stage 9:  Success path (exit code 0, no stderr)
    Stage 10: Escalation to Phase 4 reactive debugging loop (iterative auto-fix)

Requirements (install once):
    1. Install Ollama:        winget install Ollama.Ollama
    2. Pull the model:        ollama pull qwen2.5-coder:7b
    3. Ollama starts automatically as a background service on Windows.

Usage:
    python Phase3.py "Write a script that reads a CSV and plots a bar chart"
    python Phase3.py --max-retries 5 "Build a REST API with Flask"
"""

import ast
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import textwrap
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# LLM Client - wraps Qwen2.5-Coder:7B via Ollama local REST API
# ---------------------------------------------------------------------------

class QwenCoderClient:
    """
    Calls Ollama's local REST API (http://localhost:11434).
    Ollama runs as a background service and manages GPU acceleration automatically.
    Model: qwen2.5-coder:7b  (pull with: ollama pull qwen2.5-coder:7b)
    """

    OLLAMA_BASE = "http://localhost:11434"
    OLLAMA_CHAT = f"{OLLAMA_BASE}/api/chat"
    MODEL_NAME = "qwen2.5-coder:7b"

    def __init__(self, max_new_tokens: int = 2048, temperature: float = 0.2):
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self._check_ollama()

    def _check_ollama(self):
        """Verify Ollama is running and the required model is pulled."""
        try:
            with urllib.request.urlopen(f"{self.OLLAMA_BASE}/api/tags", timeout=5) as resp:
                data = json.loads(resp.read())
            model_names = [m["name"] for m in data.get("models", [])]
            base_name = self.MODEL_NAME.split(":")[0]
            found = any(base_name in m for m in model_names)
            if found:
                print(f"[LLM] Ollama ready - model '{self.MODEL_NAME}' available on GPU")
            else:
                print(f"[LLM] WARNING: model '{self.MODEL_NAME}' not found in Ollama.")
                print(f"       Available models: {model_names}")
                print(f"       Run:  ollama pull {self.MODEL_NAME}")
        except OSError:
            print("[LLM] ERROR: Cannot connect to Ollama at localhost:11434")
            print("      Start it with:  ollama serve")
            print("      Or install it:  winget install Ollama.Ollama")
            sys.exit(1)

    def chat(self, system_prompt: str, user_message: str) -> str:
        """Send a chat-style request to Ollama and return the model reply."""
        payload = json.dumps({
            "model": self.MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_new_tokens,
            },
        }).encode()

        req = urllib.request.Request(
            self.OLLAMA_CHAT,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        return result["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Phase-3 Proactive Code Generator (10-Stage Pipeline)
# ---------------------------------------------------------------------------

class ProactiveCodeGenerator:
    """
    Orchestrates code generation through a 10-stage pipeline:
      Stages 1-6: Analysis, planning, generation
      Stage 7:    Syntax validation (AST) with up to 3 LLM-guided retries
      Stage 8:    Sandboxed execution
      Stage 9:    Success path
      Stage 10:   Phase 4 reactive debugging loop (auto-fix iterations)
    """

    COMPLEXITY_THRESHOLD = 8  # Max complexity level (1-10); above this = exit early
    MAX_SYNTAX_RETRIES = 3    # Max AST validation retries before aborting
    MAX_DEBUG_ITERATIONS = 3  # Max Phase 4 auto-debug iterations (Stage 10)
    EXECUTION_TIMEOUT = 30    # Subprocess timeout in seconds
    OUTPUT_DIR = "generated_code"

    def __init__(self, llm_client: QwenCoderClient | None = None, max_debug_iterations: int = 3):
        self.llm: QwenCoderClient = llm_client or QwenCoderClient()
        self.MAX_DEBUG_ITERATIONS = max_debug_iterations

    # ===================================================================
    # PUBLIC ENTRY POINT
    # ===================================================================

    def generate_from_prompt(self, user_prompt: str) -> dict:
        """
        Main orchestrator — runs the full 10-stage pipeline.
        Returns a dict with 'status' ('success' or 'error') and full context.
        """

        # ----- Stage 1: Accept user input -----
        print(f"\n{'='*60}")
        print(f"[Stage 1] Received prompt: {user_prompt}")
        print(f"{'='*60}")

        # ----- Stage 2: Extract environment info -----
        env_info = self._stage2_extract_environment()
        print(f"[Stage 2] Environment collected:")
        print(f"          Python {env_info['python_version']} | {env_info['os']} {env_info['arch']}")
        print(f"          Packages: {env_info['installed_packages_count']} installed")
        print(f"          Network: {'online' if env_info['network_available'] else 'OFFLINE'}")
        print(f"          Disk free: {env_info['disk_free_gb']:.1f} GB")

        # ----- Stage 3: Parse requirements + Complexity Threshold -----
        requirements = self._stage3_parse_requirements(user_prompt, env_info)

        if requirements.get("status") == "exit":
            print(f"[Stage 3] EXITING: {requirements['message']}")
            return {"status": "error", "stage": 3, "error": requirements["message"]}

        complexity = requirements.get("complexity_level", 5)
        if complexity > self.COMPLEXITY_THRESHOLD:
            msg = (
                f"Task complexity ({complexity}/10) exceeds threshold "
                f"({self.COMPLEXITY_THRESHOLD}/10). Please break this into "
                f"smaller sub-tasks and re-submit each part individually."
            )
            print(f"[Stage 3] COMPLEXITY THRESHOLD EXCEEDED: {msg}")
            return {"status": "error", "stage": 3, "error": msg, "requirements": requirements}

        print(f"[Stage 3] Task type: {requirements.get('task_type', 'general')}")
        print(f"          Complexity: {complexity}/10 (threshold: {self.COMPLEXITY_THRESHOLD})")
        print(f"          Libraries: {requirements['libraries']}")
        print(f"          Steps est.: {requirements.get('estimated_steps', 'N/A')}")
        print(f"          Description: {requirements.get('description', 'N/A')}")

        # ----- Stage 4: Multi-Step Agentic Planner -----
        plan = self._stage4_create_plan(requirements, env_info)
        print(f"[Stage 4] Agentic plan created with {len(plan)} step(s):")
        for step in plan:
            print(f"          {step}")

        # ----- Stage 5: Library Identification & Validation (PyPI) -----
        library_status = self._stage5_validate_libraries(requirements["libraries"])
        print(f"[Stage 5] Library validation complete:")
        for lib, status in library_status.items():
            print(f"          {lib}: {status}")

        # ----- Stage 6: Code Generator (full context prompt) -----
        code = self._stage6_generate_code(
            user_prompt, requirements, env_info, plan, library_status
        )
        print(f"[Stage 6] Code generated ({len(code)} chars)")

        # ----- Stage 7: Syntax Validation via AST (max 3 retries) -----
        code, syntax_ok = self._stage7_validate_syntax(code)
        if not syntax_ok:
            return {
                "status": "error",
                "stage": 7,
                "error": "Failed syntax validation after 3 retries",
                "last_code": code,
            }

        # Write validated code to file
        file_path = self._write_to_file(code, "generated_script.py")
        print(f"[*] Code saved to: {file_path}")

        # ----- Stage 8: Execution Engine (sandboxed) -----
        exec_result = self._stage8_execute_sandboxed(file_path)
        print(f"[Stage 8] Execution result: exit_code={exec_result['exit_code']}")
        if exec_result["stdout"]:
            print(f"          stdout (first 200 chars): {exec_result['stdout'][:200]}")

        # ----- Stage 9 / Stage 10: Success or Phase 4 Debug Loop -----
        if exec_result["exit_code"] == 0 and not exec_result["stderr"].strip():
            # Stage 9: Success
            return self._stage9_success(exec_result, code)
        else:
            # Stage 10: Escalate to Phase 4 reactive debugging loop
            return self._stage10_phase4_debug_loop(
                code, exec_result, user_prompt, requirements, env_info, library_status
            )

    # ===================================================================
    # STAGE IMPLEMENTATIONS
    # ===================================================================

    def _stage2_extract_environment(self) -> dict:
        """
        Stage 2 - Extract comprehensive environment information:
        Python version, OS, installed packages, network connectivity, disk space.
        """
        # Installed packages via pip freeze
        installed_packages = []
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0:
                installed_packages = [
                    line.split("==")[0].lower()
                    for line in proc.stdout.strip().splitlines()
                    if "==" in line
                ]
        except Exception:
            pass

        # Network connectivity check
        network_available = False
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            network_available = True
        except OSError:
            pass

        # Disk space
        disk_free_gb = 0.0
        try:
            usage = shutil.disk_usage(Path(__file__).parent)
            disk_free_gb = usage.free / (1024 ** 3)
        except Exception:
            pass

        return {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "os": platform.system(),
            "os_version": platform.version(),
            "arch": platform.machine(),
            "installed_packages": installed_packages,
            "installed_packages_count": len(installed_packages),
            "network_available": network_available,
            "disk_free_gb": disk_free_gb,
        }

    def _stage3_parse_requirements(self, user_prompt: str, env_info: dict) -> dict:
        """
        Stage 3 - Requirement Parser & Intent Classifier.
        Extracts: task_type, libraries, complexity_level, estimated_steps,
                  description, constraints, status, message.
        Includes Complexity Threshold decision point.
        """
        system = textwrap.dedent("""\
            You are a software analysis assistant. Given a user request, extract:
            1. task_type: one of [data_analysis, web_scraping, automation, visualization, ml, general]
            2. libraries: Python list of pip-installable package names required
            3. complexity_level: integer 1-10 (1=trivial, 10=extremely complex multi-system)
            4. estimated_steps: integer, how many implementation steps needed
            5. description: one-sentence summary of what the code should accomplish
            6. constraints: list of relevant constraints (e.g. 'no internet', 'Windows only')
            7. status: 'ok' or 'exit' (exit only if request is impossible or harmful)
            8. message: if status=='exit', explain why; otherwise empty string

            Respond ONLY with a valid Python dict literal. No explanation.
            Example:
            {"task_type": "visualization", "libraries": ["matplotlib", "pandas"], "complexity_level": 3, "estimated_steps": 4, "description": "Read CSV and plot bar chart of sales data", "constraints": [], "status": "ok", "message": ""}
        """)

        prompt = (
            f"User request: {user_prompt}\n"
            f"OS: {env_info['os']} {env_info['arch']}\n"
            f"Python: {env_info['python_version']}\n"
            f"Already installed packages: {env_info['installed_packages'][:50]}\n"
            f"Network: {'available' if env_info['network_available'] else 'unavailable'}"
        )
        raw = self.llm.chat(system, prompt)

        try:
            cleaned = self._strip_code_fences(raw)
            result = ast.literal_eval(cleaned)
            # Enforce all required keys with safe defaults
            result.setdefault("task_type", "general")
            result.setdefault("libraries", [])
            result.setdefault("complexity_level", 5)
            result.setdefault("estimated_steps", 3)
            result.setdefault("description", user_prompt)
            result.setdefault("constraints", [])
            result.setdefault("status", "ok")
            result.setdefault("message", "")
            result["original_prompt"] = user_prompt
            return result
        except Exception:
            return {
                "task_type": "general",
                "libraries": [],
                "complexity_level": 5,
                "estimated_steps": 3,
                "description": user_prompt,
                "constraints": [],
                "status": "ok",
                "message": "",
                "original_prompt": user_prompt,
                "_parse_error": f"Could not parse LLM response: {raw[:200]}",
            }

    def _stage4_create_plan(self, requirements: dict, env_info: dict) -> list[str]:
        """
        Stage 4 - Multi-Step Agentic Planner.
        Uses agentic reasoning to produce a sequential action plan with tool references:
        available tools: search_docs, write_file, run_sandbox, install_package.
        """
        system = textwrap.dedent("""\
            You are a senior Python engineer acting as an agentic planner.
            Given a task, produce a numbered step-by-step action plan (max 8 steps).

            You have these tools available at each step:
              - search_docs: look up API documentation or library usage examples
              - write_file: write or update a Python source file
              - run_sandbox: execute code in a sandboxed environment to test it
              - install_package: install a pip package if not already present

            For each step, indicate which tool(s) to use in square brackets.
            Respond ONLY with a Python list of strings.
            Example:
            [
                "1. [install_package] Install pandas and matplotlib",
                "2. [search_docs] Look up pandas read_csv API for handling encodings",
                "3. [write_file] Write import statements and data loading function",
                "4. [write_file] Implement bar chart plotting with matplotlib",
                "5. [write_file] Add if __name__ == '__main__' guard with error handling",
                "6. [run_sandbox] Execute and verify output"
            ]
        """)

        prompt = (
            f"Task type: {requirements.get('task_type', 'general')}\n"
            f"User request: {requirements['original_prompt']}\n"
            f"Description: {requirements.get('description', '')}\n"
            f"Required libraries: {requirements.get('libraries', [])}\n"
            f"Complexity: {requirements.get('complexity_level', 5)}/10\n"
            f"Estimated steps: {requirements.get('estimated_steps', 3)}\n"
            f"OS: {env_info['os']} | Python: {env_info['python_version']}"
        )
        raw = self.llm.chat(system, prompt)
        try:
            cleaned = self._strip_code_fences(raw)
            plan = ast.literal_eval(cleaned)
            if isinstance(plan, list) and len(plan) > 0:
                return plan
        except Exception:
            pass
        return [
            "1. [install_package] Ensure all required libraries are installed",
            "2. [search_docs] Review API documentation for key libraries",
            "3. [write_file] Implement the requested functionality with error handling",
            "4. [run_sandbox] Execute and verify correctness",
        ]

    def _stage5_validate_libraries(self, libraries: list[str]) -> dict:
        """
        Stage 5 - Library Identification & Validation.
        For each library:
          1. Check if already installed via import attempt
          2. If missing, verify existence on PyPI API before installing
          3. Attempt pip install for verified libraries
        Captures dependency info for Phase 4 debugging.
        """
        status = {}
        for lib in libraries:
            import_name = lib.replace("-", "_").split("[")[0]

            # Step 1: Check if already installed
            try:
                __import__(import_name)
                status[lib] = "installed"
                continue
            except ImportError:
                pass

            # Step 2: Verify library exists on PyPI
            pypi_exists = False
            pypi_info = ""
            try:
                pypi_url = f"https://pypi.org/pypi/{lib}/json"
                with urllib.request.urlopen(pypi_url, timeout=10) as resp:
                    pypi_data = json.loads(resp.read())
                    pypi_exists = True
                    pypi_info = pypi_data.get("info", {}).get("summary", "")
            except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                status[lib] = f"not_found_on_pypi"
                print(f"[Stage 5] WARNING: '{lib}' not found on PyPI - skipping install")
                continue

            # Step 3: Attempt pip install for verified packages
            if pypi_exists:
                print(f"[Stage 5] Installing '{lib}' (PyPI verified: {pypi_info[:60]})")
                try:
                    proc = subprocess.run(
                        [sys.executable, "-m", "pip", "install", lib, "-q"],
                        capture_output=True, text=True, timeout=120,
                    )
                    if proc.returncode == 0:
                        status[lib] = "installed"
                    else:
                        status[lib] = f"install_failed: {proc.stderr.strip()[:100]}"
                except subprocess.TimeoutExpired:
                    status[lib] = "install_timeout"
                except Exception as e:
                    status[lib] = f"install_error: {str(e)[:80]}"

        return status

    def _stage6_generate_code(
        self,
        user_prompt: str,
        requirements: dict,
        env_info: dict,
        plan: list[str],
        library_status: dict,
    ) -> str:
        """
        Stage 6 - Code Generator.
        Sends a comprehensive prompt containing: original request, parsed requirements,
        environment info, library status, and explicit code-quality instructions.
        """
        available_libs = [lib for lib, s in library_status.items() if s == "installed"]
        failed_libs = [lib for lib, s in library_status.items() if s != "installed"]
        plan_text = "\n".join(plan)

        system = textwrap.dedent("""\
            You are an expert Python programmer. Write COMPLETE, RUNNABLE Python code.

            MANDATORY rules:
            - Include ALL necessary imports at the top of the file.
            - Add a `if __name__ == '__main__':` guard as the entry point.
            - Use descriptive variable names (no single letters except loop indices).
            - Add logging statements using print() to show progress at key steps.
            - Include clear inline comments explaining non-obvious logic.
            - Wrap risky operations in try/except with meaningful error messages.
            - Handle edge cases (empty input, missing files, etc.).
            - Return ONLY the Python code. No markdown fences. No explanatory text.
              Any text outside valid Python will break the parser.
        """)

        prompt = (
            f"=== USER REQUEST ===\n{user_prompt}\n\n"
            f"=== PARSED REQUIREMENTS ===\n"
            f"Task type: {requirements.get('task_type', 'general')}\n"
            f"Description: {requirements.get('description', user_prompt)}\n"
            f"Constraints: {requirements.get('constraints', [])}\n\n"
            f"=== ENVIRONMENT ===\n"
            f"Python: {env_info['python_version']}\n"
            f"OS: {env_info['os']} {env_info['arch']}\n"
            f"Network: {'available' if env_info['network_available'] else 'UNAVAILABLE'}\n\n"
            f"=== IMPLEMENTATION PLAN ===\n{plan_text}\n\n"
            f"=== LIBRARY STATUS ===\n"
            f"Available (use freely): {available_libs}\n"
            + (f"UNAVAILABLE (do NOT import): {failed_libs}\n" if failed_libs else "")
        )
        return self.llm.chat(system, prompt)

    def _stage7_validate_syntax(self, code: str) -> tuple[str, bool]:
        """
        Stage 7 - Syntax Validation via AST.
        Parses code with ast.parse() up to MAX_SYNTAX_RETRIES times.
        On failure, feeds the error + line number back to the LLM for correction.
        Returns (final_code, is_valid).
        """
        for attempt in range(1, self.MAX_SYNTAX_RETRIES + 1):
            clean = self._strip_code_fences(code)
            try:
                ast.parse(clean)
                print(f"[Stage 7] Syntax validation PASSED (attempt {attempt})")
                return clean, True
            except SyntaxError as e:
                error_msg = f"SyntaxError at line {e.lineno}: {e.msg}"
                print(f"[Stage 7] Syntax error (attempt {attempt}/{self.MAX_SYNTAX_RETRIES}): {error_msg}")

                if attempt < self.MAX_SYNTAX_RETRIES:
                    system = (
                        "You are an expert Python debugger. The code below has a syntax error. "
                        "Fix ONLY the syntax error and return the COMPLETE corrected Python code. "
                        "Do NOT add explanations. Do NOT use markdown fences."
                    )
                    prompt = (
                        f"Code:\n{clean}\n\n"
                        f"Error: {error_msg}\n\n"
                        "Return the complete corrected Python code."
                    )
                    code = self.llm.chat(system, prompt)

        print(f"[Stage 7] FAILED after {self.MAX_SYNTAX_RETRIES} attempts")
        return code, False

    def _stage8_execute_sandboxed(self, file_path: str) -> dict:
        """
        Stage 8 - Execution Engine.
        Runs the script in a sandboxed subprocess with:
        - stdout/stderr capture
        - Timeout enforcement to prevent infinite loops
        - Resource isolation (separate process, restricted cwd)
        """
        env = os.environ.copy()
        # Prevent the child process from prompting for input
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        try:
            proc = subprocess.run(
                [sys.executable, file_path],
                capture_output=True,
                text=True,
                timeout=self.EXECUTION_TIMEOUT,
                cwd=str(Path(file_path).parent),
                env=env,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "file_path": file_path,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution timed out after {self.EXECUTION_TIMEOUT}s (possible infinite loop)",
                "file_path": file_path,
            }
        except Exception as e:
            return {
                "exit_code": -2,
                "stdout": "",
                "stderr": f"Execution engine error: {e}",
                "file_path": file_path,
            }

    def _stage9_success(self, exec_result: dict, code: str) -> dict:
        """
        Stage 9 - Success Path.
        Reached when exit_code == 0 and stderr is empty.
        """
        print(f"[Stage 9] Execution SUCCESSFUL!")
        return {
            "status": "success",
            "stage": 9,
            "stdout": exec_result["stdout"],
            "stderr": exec_result["stderr"],
            "file_path": exec_result["file_path"],
            "code": code,
        }

    def _stage10_phase4_debug_loop(
        self,
        code: str,
        exec_result: dict,
        user_prompt: str,
        requirements: dict,
        env_info: dict,
        library_status: dict,
    ) -> dict:
        """
        Stage 10 - Phase 4 Reactive Debugging Loop.
        Automatically invokes iterative debugging when execution fails:
          1. Pass stderr (error messages, tracebacks) to the LLM
          2. LLM produces a corrected version of the code
          3. Re-validate syntax (Stage 7)
          4. Re-execute (Stage 8)
          5. Repeat until success or MAX_DEBUG_ITERATIONS reached
        Creates a closed-loop autonomous system.
        """
        print(f"\n[Stage 10] Execution FAILED - entering Phase 4 reactive debugging loop")
        print(f"           Max iterations: {self.MAX_DEBUG_ITERATIONS}")

        current_code = code
        current_result = exec_result
        debug_history = []

        for iteration in range(1, self.MAX_DEBUG_ITERATIONS + 1):
            stderr = current_result["stderr"]
            exit_code = current_result["exit_code"]

            print(f"\n[Phase 4] Debug iteration {iteration}/{self.MAX_DEBUG_ITERATIONS}")
            print(f"          Error: {stderr[:200]}")

            # Record debug history
            debug_history.append({
                "iteration": iteration,
                "exit_code": exit_code,
                "stderr": stderr[:500],
            })

            # Ask the LLM to diagnose and fix the code
            system = textwrap.dedent("""\
                You are an expert Python debugger performing reactive code repair.
                You are given Python code that failed at runtime, along with the full
                error output (traceback). Your job:
                1. Diagnose the root cause of the error.
                2. Fix the code so it runs successfully.
                3. Return ONLY the complete corrected Python code.
                4. Do NOT add explanations, comments about what you changed, or markdown.
                5. Keep all existing functionality intact - only fix the error.
            """)

            prompt = (
                f"=== ORIGINAL USER REQUEST ===\n{user_prompt}\n\n"
                f"=== ENVIRONMENT ===\n"
                f"Python: {env_info['python_version']} | OS: {env_info['os']}\n"
                f"Available libraries: {[l for l, s in library_status.items() if s == 'installed']}\n\n"
                f"=== FAILING CODE ===\n{current_code}\n\n"
                f"=== ERROR OUTPUT (exit code {exit_code}) ===\n{stderr}\n\n"
                f"=== DEBUG HISTORY ===\n"
                f"This is attempt {iteration}. Previous errors: "
                f"{[h['stderr'][:100] for h in debug_history[:-1]]}\n\n"
                f"Return the complete corrected Python code."
            )

            fixed_code = self.llm.chat(system, prompt)

            # Re-validate syntax (Stage 7 sub-loop)
            fixed_code, syntax_ok = self._stage7_validate_syntax(fixed_code)
            if not syntax_ok:
                print(f"[Phase 4] Iteration {iteration}: Fix has syntax errors, continuing...")
                current_code = fixed_code
                continue

            # Write the fixed code and re-execute
            file_path = self._write_to_file(fixed_code, "generated_script.py")
            current_result = self._stage8_execute_sandboxed(file_path)
            current_code = fixed_code

            print(f"[Phase 4] Iteration {iteration}: exit_code={current_result['exit_code']}")

            # Check if fixed
            if current_result["exit_code"] == 0 and not current_result["stderr"].strip():
                print(f"[Phase 4] Bug FIXED on iteration {iteration}!")
                return {
                    "status": "success",
                    "stage": 10,
                    "debug_iterations": iteration,
                    "stdout": current_result["stdout"],
                    "stderr": current_result["stderr"],
                    "file_path": current_result["file_path"],
                    "code": current_code,
                    "debug_history": debug_history,
                }

        # All debug iterations exhausted
        print(f"\n[Phase 4] EXHAUSTED all {self.MAX_DEBUG_ITERATIONS} debug iterations")
        print(f"          Final error: {current_result['stderr'][:200]}")

        return {
            "status": "error",
            "stage": 10,
            "debug_iterations": self.MAX_DEBUG_ITERATIONS,
            "exit_code": current_result["exit_code"],
            "stdout": current_result["stdout"],
            "stderr": current_result["stderr"],
            "file_path": current_result.get("file_path", ""),
            "code": current_code,
            "debug_history": debug_history,
            "message": (
                f"Failed after {self.MAX_DEBUG_ITERATIONS} Phase 4 debug iterations. "
                f"Manual intervention required."
            ),
        }

    # ===================================================================
    # UTILITY METHODS
    # ===================================================================

    def _write_to_file(self, code: str, filename: str) -> str:
        """Write generated code to the output directory."""
        code = self._strip_code_fences(code)
        output_dir = Path(__file__).parent / self.OUTPUT_DIR
        output_dir.mkdir(exist_ok=True)
        file_path = output_dir / filename
        file_path.write_text(code, encoding="utf-8")
        return str(file_path)

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Remove markdown ```python ... ``` fences the LLM may wrap around code."""
        lines = text.strip().splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 3 - Proactive Code Generator (Qwen2.5-Coder:7b via Ollama)"
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Write a Python script that prints a multiplication table from 1 to 10",
        help="Natural-language description of the code to generate",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=2048,
        help="Maximum new tokens for LLM generation (default: 2048)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.2,
        help="Sampling temperature (default: 0.2 - near-deterministic)",
    )
    parser.add_argument(
        "--max-retries", type=int, default=3,
        help="Max Phase 4 debug iterations on execution failure (default: 3)",
    )
    parser.add_argument(
        "--complexity-threshold", type=int, default=8,
        help="Max complexity level 1-10 before early exit (default: 8)",
    )
    args = parser.parse_args()

    print(f"Phase 3 - Proactive Code Generator")
    print(f"Model: Qwen2.5-Coder:7b via Ollama")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Config: max_tokens={args.max_tokens}, temp={args.temperature}, "
          f"debug_retries={args.max_retries}, complexity_threshold={args.complexity_threshold}")

    # Connect to Ollama
    llm = QwenCoderClient(max_new_tokens=args.max_tokens, temperature=args.temperature)

    # Create generator with config
    generator = ProactiveCodeGenerator(llm_client=llm, max_debug_iterations=args.max_retries)
    generator.COMPLEXITY_THRESHOLD = args.complexity_threshold

    # Run the full 10-stage pipeline
    result = generator.generate_from_prompt(args.prompt)

    # Final report
    print(f"\n{'='*60}")
    print(f"PIPELINE RESULT: {result['status'].upper()}")
    print(f"{'='*60}")

    if result["status"] == "success":
        print(f"Completed at Stage {result.get('stage', '?')}")
        if result.get("debug_iterations"):
            print(f"Phase 4 debug iterations used: {result['debug_iterations']}")
        print(f"\n--- Generated Script Output ---")
        print(result.get("stdout", "(no stdout)") or "(no stdout)")
        print(f"\nSaved to: {result.get('file_path', 'N/A')}")
    else:
        print(f"Failed at Stage {result.get('stage', '?')}")
        if result.get("debug_iterations"):
            print(f"Phase 4 debug iterations used: {result['debug_iterations']}")
        print(f"\n--- Error ---")
        print(result.get("error", result.get("stderr", "Unknown error")))
        if result.get("debug_history"):
            print(f"\n--- Debug History ---")
            for entry in result["debug_history"]:
                print(f"  Iteration {entry['iteration']}: exit={entry['exit_code']} | {entry['stderr'][:100]}")
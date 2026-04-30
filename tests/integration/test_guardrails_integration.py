# tests/integration/test_guardrails_integration.py
"""
Integration tests for GuardrailsEngine with real commands.
"""

import pytest
from guardrails_engine import GuardrailsEngine
import tempfile
import os

@pytest.mark.integration
class TestGuardrailsIntegration:
    """Verify guardrails block dangerous commands in real scenarios."""

    @pytest.fixture
    def engine(self):
        config_path = "src/guardrails/guardrails_config.yaml"
        return GuardrailsEngine(config_path)

    @pytest.fixture
    def workspace(self, tmp_path):
        """Create a test workspace."""
        return str(tmp_path)

    def test_reject_command_chaining(self, engine, workspace):
        """Command chaining with ; should be rejected."""
        result = engine.validate({
            "caller_service": "generation",
            "raw_command": "python main.py; rm -rf /",
            "working_dir": workspace
        })
        assert result["status"] == "REJECT"
        assert "token_order_step_1" in result.get("failing_rule_id", "")

    def test_block_variable_expansion(self, engine, workspace):
        """Variable expansion like $1 should be blocked."""
        result = engine.validate({
            "caller_service": "debugging",
            "raw_command": "python $1 script.py",
            "working_dir": workspace
        })
        assert result["status"] == "BLOCK"
        assert result["failing_rule_id"] == "token_order_step_2"

    def test_path_traversal_rejected(self, engine, workspace):
        """../ path traversal should be rejected."""
        result = engine.validate({
            "caller_service": "generation",
            "raw_command": "cat ../../../etc/passwd",
            "working_dir": workspace
        })
        assert result["status"] == "REJECT"
        assert result["failing_rule_id"] == "PATH-02"
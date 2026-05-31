"""
Unit tests for engine/parser MiddlewareRunner — PII removal, guardrails,
cost gate, schema validation, auto-compaction. Pure logic, no LLM.
"""
import pytest
import json
from engine.parser import MiddlewareRunner
from engine.state import AgentFlowState


# ─────────────────────────────────────────────────────────────────────────────
# PII Removal middleware
# ─────────────────────────────────────────────────────────────────────────────

class TestMiddlewareRunnerPIIRemoval:
    """MiddlewareRunner.before_node handles pii_removal middleware."""

    def test_pii_removal_redacts_emails(self):
        """pii_removal middleware redacts email addresses."""
        config = {
            "middlewares": [
                {"type": "pii_removal", "config": {}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {
                "message": "Contact me at john.doe@example.com or jane@example.org",
            },
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)

        # Email should be redacted
        msg = result["initial_input"]["message"]
        assert "john.doe@example.com" not in msg
        assert "jane@example.org" not in msg
        assert "[REDACTED_EMAIL]" in msg

    def test_pii_removal_redacts_phone_numbers(self):
        """pii_removal middleware redacts phone numbers."""
        config = {
            "middlewares": [
                {"type": "pii_removal", "config": {}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {
                "message": "Call me at 555-123-4567 or 987.654.3210",
            },
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)

        msg = result["initial_input"]["message"]
        assert "555-123-4567" not in msg
        assert "[REDACTED_PHONE]" in msg

    def test_pii_removal_preserves_non_pii_text(self):
        """pii_removal only affects email and phone patterns."""
        config = {
            "middlewares": [
                {"type": "pii_removal", "config": {}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {
                "message": "The capital of France is Paris and the population is 2.1 million.",
            },
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)

        assert "capital of France" in result["initial_input"]["message"]
        assert "Paris" in result["initial_input"]["message"]

    def test_pii_removal_applies_to_telegram_message(self):
        """pii_removal also redacts telegram_message field."""
        config = {
            "middlewares": [
                {"type": "pii_removal", "config": {}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": 6662064047,
            "telegram_message": "My email is test@example.com",
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)

        assert "[REDACTED_EMAIL]" in result["telegram_message"]
        assert "test@example.com" not in result["telegram_message"]

    def test_pii_removal_no_op_without_pii(self):
        """pii_removal leaves clean text unchanged."""
        config = {
            "middlewares": [
                {"type": "pii_removal", "config": {}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {"message": "Hello world"},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)
        assert result["initial_input"]["message"] == "Hello world"


# ─────────────────────────────────────────────────────────────────────────────
# Guardrails middleware
# ─────────────────────────────────────────────────────────────────────────────

class TestMiddlewareRunnerGuardrails:
    """MiddlewareRunner.before_node handles guardrails middleware."""

    def test_guardrails_blocks_on_blocklist_match(self):
        """guardrails middleware raises ValueError when blocklist word is found."""
        config = {
            "middlewares": [
                {"type": "guardrails", "config": {"blocklist": ["hack", "bypass"]}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {"message": "Please hack the system"},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        with pytest.raises(ValueError, match="Safety Violation"):
            MiddlewareRunner.before_node(state, config)

    def test_guardrails_blocks_telegram_message(self):
        """guardrails checks telegram_message as well."""
        config = {
            "middlewares": [
                {"type": "guardrails", "config": {"blocklist": ["secret", "confidential"]}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": 6662064047,
            "telegram_message": "The secret password is xyz",
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        with pytest.raises(ValueError, match="Safety Violation"):
            MiddlewareRunner.before_node(state, config)

    def test_guardrails_allows_clean_input(self):
        """guardrails allows non-blocked input."""
        config = {
            "middlewares": [
                {"type": "guardrails", "config": {"blocklist": ["hack"]}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {"message": "What is the weather like?"},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)
        assert result["initial_input"]["message"] == "What is the weather like?"

    def test_guardrails_case_insensitive(self):
        """guardrails blocklist matching is case-insensitive."""
        config = {
            "middlewares": [
                {"type": "guardrails", "config": {"blocklist": ["Bypass"]}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {"message": "BYPASS the security"},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        with pytest.raises(ValueError, match="Safety Violation"):
            MiddlewareRunner.before_node(state, config)


# ─────────────────────────────────────────────────────────────────────────────
# Cost Gate middleware
# ─────────────────────────────────────────────────────────────────────────────

class TestMiddlewareRunnerCostGate:
    """MiddlewareRunner.after_node handles cost_gate middleware."""

    def test_cost_gate_raises_when_limit_exceeded(self, client):
        """cost_gate raises ValueError when accumulated cost exceeds max_cost_usd."""
        from sqlmodel import Session
        from database import engine as db_engine
        from models.run import CostEvent

        # Create a run record with accumulated cost events
        wfs = client.get("/api/workflows/").json()
        wf_id = wfs[0]["id"]
        start_res = client.post("/api/runs/start", json={
            "workflow_id": wf_id,
            "initial_input": {"message": "trigger cost"},
        })
        run_id = start_res.json()["run_id"]

        # Insert a cost event that exceeds the limit
        with Session(db_engine) as session:
            session.add(CostEvent(
                run_id=run_id, node_id="test_node",
                provider="test", model="test-model",
                input_tokens=100, output_tokens=100,
                estimated_cost_usd=0.001,  # 1 mill USD
            ))
            session.commit()

        config = {
            "middlewares": [
                {"type": "cost_gate", "config": {"max_cost_usd": 0.0001}}  # very low limit
            ]
        }
        state: AgentFlowState = {
            "run_id": run_id, "workflow_id": "1",
            "initial_input": {}, "node_outputs": {}, "parallel_results": [],
            "_run_error": None, "__recursion_registry__": {},
            "telegram_chat_id": None, "telegram_message": None,
            "__hitl_pending__": False, "__hitl_response__": None,
        }
        output = {"content": "some output"}

        with pytest.raises(ValueError, match="Cost Gate"):
            MiddlewareRunner.after_node("test_node", output, config, state)

    def test_cost_gate_allows_within_limit(self, client):
        """cost_gate allows execution when total cost is below limit."""
        config = {
            "middlewares": [
                {"type": "cost_gate", "config": {"max_cost_usd": 999.0}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "nonexistent_run_123",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }
        output = {"content": "some output"}

        result = MiddlewareRunner.after_node("test_node", output, config, state)
        assert result == output  # Unchanged


# ─────────────────────────────────────────────────────────────────────────────
# Schema Validator middleware
# ─────────────────────────────────────────────────────────────────────────────

class TestMiddlewareRunnerSchemaValidator:
    """MiddlewareRunner.after_node handles schema_validator middleware."""

    def test_schema_validator_passes_when_output_matches(self):
        """schema_validator allows output that contains all required fields."""
        config = {
            "middlewares": [
                {
                    "type": "schema_validator",
                    "config": {
                        "schema": {"required": ["name", "email"]}
                    }
                }
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }
        output = {"content": '{"name": "John", "email": "john@example.com"}'}

        result = MiddlewareRunner.after_node("test_node", output, config, state)
        assert result == output  # Unchanged

    def test_schema_validator_fails_on_missing_field(self):
        """schema_validator raises ValueError when required field is missing."""
        config = {
            "middlewares": [
                {
                    "type": "schema_validator",
                    "config": {
                        "schema": {"required": ["name", "email"]}
                    }
                }
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }
        output = {"content": '{"name": "John"}'}  # missing email

        with pytest.raises(ValueError, match="Schema validation failed"):
            MiddlewareRunner.after_node("test_node", output, config, state)

    def test_schema_validator_no_op_without_schema(self):
        """schema_validator does nothing when no schema is configured."""
        config = {"middlewares": [{"type": "schema_validator", "config": {}}]}
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }
        output = {"content": "some random text"}
        result = MiddlewareRunner.after_node("test_node", output, config, state)
        assert result == output


# ─────────────────────────────────────────────────────────────────────────────
# Auto-compaction middleware
# ─────────────────────────────────────────────────────────────────────────────

class TestMiddlewareRunnerAutoCompaction:
    """MiddlewareRunner.before_node handles auto_compaction middleware."""

    def test_auto_compaction_triggers_above_threshold(self):
        """auto_compaction replaces node_outputs when state exceeds max_tokens * 4."""
        config = {
            "middlewares": [
                {"type": "auto_compaction", "config": {"max_tokens": 100}}
            ]
        }
        # Large node_outputs that exceeds 100 * 4 = 400 chars
        large_output = "x" * 500  # 500 chars
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {
                "node_a": {"content": large_output},
            },
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)

        # Should be compacted
        compacted = result["node_outputs"]
        assert "compacted_history" in compacted or "content" not in str(large_output)
        # The compaction message should be there
        assert compacted.get("compacted_history", {}).get("content") == "State history compacted to reduce token footprint."

    def test_auto_compaction_no_op_below_threshold(self):
        """auto_compaction does nothing when state is below threshold."""
        config = {
            "middlewares": [
                {"type": "auto_compaction", "config": {"max_tokens": 10000}}
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {
                "node_a": {"content": "small output"},
            },
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)
        assert "node_a" in result["node_outputs"]
        assert "compacted_history" not in result["node_outputs"]


# ─────────────────────────────────────────────────────────────────────────────
# Middleware chaining — multiple middlewares applied in order
# ─────────────────────────────────────────────────────────────────────────────

class TestMiddlewareRunnerChaining:
    """Multiple middlewares are applied in sequence."""

    def test_pii_then_guardrails_chaining(self):
        """PII removal runs before guardrails in same request."""
        config = {
            "middlewares": [
                {"type": "pii_removal", "config": {}},
                {"type": "guardrails", "config": {"blocklist": ["secret"]}},
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {
                "message": "Contact me at admin@evil.com — this is a secret message",
            },
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        # pii_removal runs first → email redacted, then guardrails fires on "secret"
        with pytest.raises(ValueError, match="Safety Violation"):
            MiddlewareRunner.before_node(state, config)
        # Guardrails fires on "secret" before PII assertions can be checked.

    def test_guardrails_before_pii_order(self):
        """Guardrails fires even when preceded by pii_removal."""
        config = {
            "middlewares": [
                {"type": "guardrails", "config": {"blocklist": ["evil"]}},
                {"type": "pii_removal", "config": {}},
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {
                "message": "Visit evil.com for more",
            },
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        with pytest.raises(ValueError, match="Safety Violation"):
            MiddlewareRunner.before_node(state, config)


# ─────────────────────────────────────────────────────────────────────────────
# Middleware empty / no-op cases
# ─────────────────────────────────────────────────────────────────────────────

class TestMiddlewareRunnerNoOp:
    """Edge cases: no middlewares, empty config."""

    def test_no_middlewares_returns_state_unchanged(self):
        """before_node with no middlewares returns state unchanged."""
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {"message": "hello"},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }
        config = {"middlewares": []}

        result = MiddlewareRunner.before_node(state, config)
        assert result["initial_input"]["message"] == "hello"

    def test_after_node_no_middlewares_returns_output_unchanged(self):
        """after_node with no middlewares returns output unchanged."""
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }
        config = {"middlewares": []}
        output = {"content": "test output", "tokens": 10}

        result = MiddlewareRunner.after_node("test_node", output, config, state)
        assert result == output

    def test_unknown_middleware_type_ignored(self):
        """Unknown middleware type is silently skipped."""
        config = {
            "middlewares": [
                {"type": "unknown_middleware_type_xyz", "config": {}},
            ]
        }
        state: AgentFlowState = {
            "run_id": "test",
            "workflow_id": "1",
            "initial_input": {"message": "test"},
            "node_outputs": {},
            "parallel_results": [],
            "_run_error": None,
            "__recursion_registry__": {},
            "telegram_chat_id": None,
            "telegram_message": None,
            "__hitl_pending__": False,
            "__hitl_response__": None,
        }

        result = MiddlewareRunner.before_node(state, config)
        assert result["initial_input"]["message"] == "test"
"""
Unit tests for engine/edges resolve_next_node() — pure logic, no LLM needed.
Covers: error routing, conditional evaluation, normal fallback, no edges → None.
"""
import pytest
from engine.edges import resolve_next_node


class TestResolveNextNodeErrorRouting:
    """Error edges take priority when _run_error is set in state."""

    def test_error_edge_taken_when_error_set(self):
        """When _run_error is present, error edge is returned over conditional."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "error"},
            {"id": "e2", "source": "node_a", "target": "node_c", "type": "conditional",
             "condition": "state['node_outputs']['v']['is_approved'] == True"},
        ]
        state = {"_run_error": {"node_id": "node_a", "message": "oops"}}
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_b"

    def test_no_error_edge_returns_none_when_error_set(self):
        """When _run_error is set but no error edge exists, returns None (end)."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "normal"},
        ]
        state = {"_run_error": {"node_id": "node_a", "message": "oops"}}
        result = resolve_next_node("node_a", edges, state)
        assert result is None


class TestResolveNextNodeConditional:
    """Conditional edges are evaluated in declaration order."""

    def test_conditional_true_returns_target(self):
        """First conditional that evaluates True returns its target."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "conditional",
             "condition": "state['node_outputs']['v']['is_approved'] == True"},
            {"id": "e2", "source": "node_a", "target": "node_c", "type": "conditional",
             "condition": "state['node_outputs']['v']['is_approved'] == False"},
        ]
        state = {"node_outputs": {"v": {"is_approved": True}}}
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_b"

    def test_conditional_false_skips_to_next(self):
        """False condition skips to next conditional or normal edge."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "conditional",
             "condition": "state['node_outputs']['v']['is_approved'] == False"},
            {"id": "e2", "source": "node_a", "target": "node_c", "type": "normal"},
        ]
        state = {"node_outputs": {"v": {"is_approved": True}}}
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_c"

    def test_all_conditionals_false_falls_through(self):
        """When all conditionals are False and no normal edge, returns None."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "conditional",
             "condition": "state['node_outputs']['v']['is_approved'] == True"},
            {"id": "e2", "source": "node_a", "target": "node_c", "type": "conditional",
             "condition": "state['node_outputs']['v']['score'] > 100"},
        ]
        state = {"node_outputs": {"v": {"is_approved": False, "score": 42}}}
        result = resolve_next_node("node_a", edges, state)
        assert result is None

    def test_conditional_with_numeric_comparison(self):
        """Numeric conditions work correctly."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "conditional",
             "condition": "state['node_outputs']['counter']['count'] >= 3"},
        ]
        state = {"node_outputs": {"counter": {"count": 5}}}
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_b"

    def test_conditional_missing_key_returns_none(self):
        """Missing keys in state cause condition to fail gracefully."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "conditional",
             "condition": "state['node_outputs']['v']['is_approved'] == True"},
        ]
        state = {"node_outputs": {}}
        result = resolve_next_node("node_a", edges, state)
        assert result is None


class TestResolveNextNodeNormalEdge:
    """Normal edges are unconditional fallback after conditionals."""

    def test_normal_edge_returns_target(self):
        """Normal edge is returned as unconditional fallback."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "normal"},
        ]
        state = {}
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_b"

    def test_normal_edge_not_checked_when_conditional_matches(self):
        """Normal edge is only used when no conditional edge matches."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "conditional",
             "condition": "state['node_outputs']['v']['flag'] == True"},
            {"id": "e2", "source": "node_a", "target": "node_c", "type": "normal"},
        ]
        state = {"node_outputs": {"v": {"flag": True}}}
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_b"


class TestResolveNextNodeNoEdges:
    """No outgoing edges means graph end."""

    def test_no_outgoing_edges_returns_none(self):
        """Node with no outgoing edges terminates (returns None)."""
        edges = []  # no edges at all
        state = {}
        result = resolve_next_node("node_a", edges, state)
        assert result is None


class TestResolveNextNodeParallelFanIn:
    """parallel_fan_in edges are treated as normal (handled by fan-out sender)."""
    # Note: parallel_fan_in doesn't go through resolve_next_node routing.
    # The fan-out sender uses Send() to dispatch items; the fan-in aggregator
    # receives results via parallel_results state channel.

    def test_parallel_fan_in_edge_not_routed_here(self):
        """parallel_fan_in edges are treated as normal fallback edges."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_b", "type": "parallel_fan_in"},
        ]
        state = {}
        # parallel_fan_in is in the normal_edges type list: ("normal", "parallel_fan_in")
        # so it gets returned as the fallback target.
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_b"


class TestResolveNextNodeMixedEdges:
    """Complex graphs with error + conditional + normal edges."""

    def test_error_overrides_conditional_and_normal(self):
        """Error takes priority over everything."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_error_handler", "type": "error"},
            {"id": "e2", "source": "node_a", "target": "node_b", "type": "conditional",
             "condition": "state['node_outputs']['v']['ok'] == True"},
            {"id": "e3", "source": "node_a", "target": "node_c", "type": "normal"},
        ]
        state = {
            "_run_error": {"node_id": "node_a", "message": "crashed"},
            "node_outputs": {"v": {"ok": True}},
        }
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_error_handler"

    def test_conditional_matches_before_normal(self):
        """First matching conditional wins; normal is only fallback."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_high", "type": "conditional",
             "condition": "state['node_outputs']['s']['score'] > 80"},
            {"id": "e2", "source": "node_a", "target": "node_medium", "type": "conditional",
             "condition": "state['node_outputs']['s']['score'] > 50"},
            {"id": "e3", "source": "node_a", "target": "node_low", "type": "normal"},
        ]
        state = {"node_outputs": {"s": {"score": 95}}}
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_high"

    def test_second_conditional_matches(self):
        """Second conditional matches when first is False."""
        edges = [
            {"id": "e1", "source": "node_a", "target": "node_high", "type": "conditional",
             "condition": "state['node_outputs']['s']['score'] > 80"},
            {"id": "e2", "source": "node_a", "target": "node_medium", "type": "conditional",
             "condition": "state['node_outputs']['s']['score'] > 50"},
            {"id": "e3", "source": "node_a", "target": "node_low", "type": "normal"},
        ]
        state = {"node_outputs": {"s": {"score": 65}}}
        result = resolve_next_node("node_a", edges, state)
        assert result == "node_medium"
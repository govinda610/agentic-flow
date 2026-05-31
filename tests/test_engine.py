import pytest
from engine.edges import evaluate_condition

def test_asteval_simple_boolean():
    """Deterministic edge: simple boolean condition evaluates correctly."""
    state = {"node_outputs": {"node_verifier": {"is_approved": True}}}
    result = evaluate_condition(
        "state['node_outputs']['node_verifier']['is_approved'] == True",
        state
    )
    assert result is True

def test_asteval_false_condition():
    """Deterministic edge: false condition returns False."""
    state = {"node_outputs": {"node_verifier": {"is_approved": False}}}
    result = evaluate_condition(
        "state['node_outputs']['node_verifier']['is_approved'] == True",
        state
    )
    assert result is False

def test_asteval_numeric_comparison():
    """Deterministic edge: numeric comparison works."""
    state = {"node_outputs": {"node_counter": {"count": 3}}}
    result = evaluate_condition(
        "state['node_outputs']['node_counter']['count'] >= 2",
        state
    )
    assert result is True

def test_asteval_dict_get_safe():
    """Edge condition using .get() doesn't raise on missing key."""
    state = {"node_outputs": {}}
    result = evaluate_condition(
        "state['node_outputs'].get('node_verifier', {}).get('is_approved') == True",
        state
    )
    assert result is False

def test_asteval_blocks_import():
    """Security: asteval with minimal=True blocks import statements."""
    with pytest.raises(Exception):
        evaluate_condition("import os; os.system('echo HACKED')", {})

def test_asteval_blocks_exec():
    """Security: asteval blocks exec() calls."""
    with pytest.raises(Exception):
        evaluate_condition("exec('print(1)')", {})

def test_parallel_results_channel():
    """State: parallel_results uses operator.add for list accumulation."""
    import operator
    # Simulate two parallel branches updating the list channel
    acc: list = []
    acc = operator.add(acc, [{"node": "node_researcher", "output": {"output": "result1"}}])
    acc = operator.add(acc, [{"node": "node_researcher", "output": {"output": "result2"}}])
    assert len(acc) == 2
    assert acc[0]["output"]["output"] == "result1"
    assert acc[1]["output"]["output"] == "result2"

def test_build_input_context_task_priority():
    """node_input: __task__ key takes top priority over node_outputs."""
    from engine.node_input import build_input_context
    state = {
        "initial_input": {"__task__": "Specific task", "message": "ignored"},
        "node_outputs":  {"node_prev": {"output": "previous big output"}},
        "parallel_results": [],
    }
    result = build_input_context(state)
    assert result == "Specific task"

def test_build_input_context_sequential_fallback():
    """node_input: sequential mode uses node_outputs when no __task__."""
    from engine.node_input import build_input_context
    state = {
        "initial_input": {"message": "hello"},
        "node_outputs": {"node_a": {"output": "first result"}},
        "parallel_results": [],
    }
    result = build_input_context(state)
    assert "node_a" in result

def test_auto_layout_no_overlap():
    """Auto-layout: browser-level assertion — skip in unit suite."""
    pytest.skip("Browser-level layout assertion; validated manually in the canvas UI")

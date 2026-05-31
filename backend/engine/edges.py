from asteval import Interpreter
import logging

logger = logging.getLogger(__name__)


def evaluate_condition(condition_str: str, state: dict) -> bool:
    """
    Safely evaluate a boolean edge condition string against the current run state.

    Uses asteval with minimal=True to disable import, exec, eval, and all
    dangerous builtins. Only arithmetic, boolean logic, comparisons,
    dict/list access, and string operations are permitted.

    Args:
        condition_str: e.g. "state['node_outputs']['node_verifier']['is_approved'] == True"
        state: The current AgentFlowState dict

    Returns:
        bool: True if the condition is met, False otherwise

    Raises:
        ValueError: If the condition string contains syntax errors or security violations

    Note: asteval==0.9.32 uses `usersyms=` kwarg. If bumping to asteval>=1.0,
          rename to `user_symbols=`.
    """
    aeval = Interpreter(
        usersyms={"state": state},
        minimal=True,           # Strips: import, exec, eval, open, subprocess, etc.
        no_print=True,
        max_statement_length=500,
    )

    result = aeval(condition_str)

    if aeval.error:
        error_msg = "; ".join(str(e) for e in aeval.error)
        logger.error(f"Edge condition evaluation error: {error_msg}")
        raise ValueError(f"Invalid edge condition '{condition_str}': {error_msg}")

    return bool(result)


def resolve_next_node(
    node_id: str,
    edges: list[dict],
    state: dict
) -> str | None:
    """
    Given the current node and all edges, determine which node to execute next.
    Handles: normal edges, conditional edges, error edges.

    Error edges take priority when state['_run_error'] is set.
    Conditional edges are evaluated in declaration order.
    Normal edges act as the unconditional fallback.

    Returns:
        str: Next node ID
        None: End of graph
    """
    outgoing = [e for e in edges if e["source"] == node_id]

    if not outgoing:
        return None

    # Error routing: check for an error edge first when a node has failed
    if state.get("_run_error"):
        error_edges = [e for e in outgoing if e.get("type") == "error"]
        if error_edges:
            return error_edges[0]["target"]
        # No error edge defined → propagate error to graph end
        return None

    # Conditional edges take precedence when present
    conditional_edges = [e for e in outgoing if e.get("type") == "conditional"]
    for edge in conditional_edges:
        condition = edge.get("condition")
        if condition is None:
            logger.warning(f"Edge {edge['id']} has no condition — skipping")
            continue
        try:
            if evaluate_condition(condition, state):
                return edge["target"]
        except ValueError as exc:
            logger.warning(f"Condition eval failed for edge {edge['id']}: {exc}")
            continue

    # Normal (unconditional) edge acts as the default fallback.
    # Falling through to normal edges if all conditional edges fail is intentional behavior.
    normal_edges = [e for e in outgoing if e.get("type") in ("normal", "parallel_fan_in")]
    if normal_edges:
        return normal_edges[0]["target"]

    # If no conditional edge matches and there is no normal edge, terminate execution gracefully.
    return None

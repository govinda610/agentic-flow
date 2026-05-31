from typing import TypedDict, Annotated, Any
import operator


def _first_error(existing: dict | None, new: dict | None) -> dict | None:
    """Reducer for _run_error so concurrent parallel branches can converge.

    Parallel fan-out branches each write _run_error in the same superstep; a
    plain channel rejects multiple values per step. Keep the first error seen
    (a run routes to its end once _run_error is set, so it is never cleared).
    """
    return existing if existing is not None else new


class AgentFlowState(TypedDict):
    """The shared state object passed between all nodes in a LangGraph workflow."""

    # Core run metadata
    run_id: str
    workflow_id: str

    # Input from the trigger (Start node, Webhook, or Telegram)
    initial_input: dict[str, Any]

    # Per-node output: keyed by node_id, value is node's output dict.
    # operator.or_ merges dicts — valid for sequential nodes where each
    # node has a unique key. For parallel fan-out nodes, use parallel_results.
    node_outputs: Annotated[dict[str, Any], operator.or_]

    # Parallel fan-out accumulator: each parallel branch appends one item.
    # operator.add concatenates lists from concurrent branches correctly.
    # FIX: added to prevent parallel branches from overwriting each other in node_outputs.
    parallel_results: Annotated[list, operator.add]

    # Error handling: set when any node raises an unhandled exception
    _run_error: Annotated[dict[str, Any] | None, _first_error]

    # Recursion tracking for clone_agent_tool
    __recursion_registry__: dict[str, Any]

    # Telegram context (if triggered via Telegram)
    telegram_chat_id: int | None
    telegram_message: str | None

    # Human-in-the-loop: managed via LangGraph's dynamic interrupt() mechanism.
    # __hitl_pending__ tracks UI display state; __hitl_response__ is reserved
    # but not used by the engine (interrupt() returns the value directly).
    __hitl_pending__: bool
    __hitl_response__: Any

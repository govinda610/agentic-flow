"""
Single source of truth for how a node determines what text to use as its LLM input.

Rules (in priority order):
1. If initial_input contains '__task__' — this is a delegated/cloned/fan-out invocation.
   Use the task string directly. This prevents parent node_outputs from bleeding in.
2. Otherwise, if node_outputs is non-empty, use the full accumulated outputs as context
   (standard sequential chaining behaviour).
3. If parallel_results are present, merge them into the context so fan-in aggregators
   can see all parallel branch outputs.
4. Fall back to initial_input message/full dict if nothing else is available.
"""
from typing import Any


def build_input_context(state: dict[str, Any]) -> str:
    """
    Compute the LLM input string for a node from the current workflow state.

    This function is used by ALL node runners (simple_llm, agent, deep_agent,
    supervisor) to ensure consistent, correct input selection.
    """
    ii = state.get("initial_input") or {}

    # Priority 1: explicit task delegation (fan-out item, clone task, supervisor child task)
    if "__task__" in ii:
        return str(ii["__task__"])

    # Priority 2: accumulated sequential outputs + any parallel results
    prior = dict(state.get("node_outputs") or {})
    parallel = state.get("parallel_results")
    if parallel:
        # Inject parallel branch results so the fan-in aggregator sees them all
        prior["parallel_results"] = parallel

    if prior:
        return str(prior)

    # Priority 3: fallback to initial input
    return str(ii.get("message") or ii)


def text_of(msg: Any) -> str:
    """
    Extract a plain text string from a LangChain AIMessage or any content value.

    In LangChain 1.x with standardised content blocks, .content can be a list
    of typed blocks rather than a plain string. This helper handles both.
    """
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)

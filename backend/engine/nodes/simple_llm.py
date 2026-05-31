from langchain_core.messages import HumanMessage, SystemMessage
from providers.registry import get_llm
from engine.state import AgentFlowState
from engine.node_input import build_input_context, text_of


async def run_simple_llm_node(state: AgentFlowState, node_config: dict) -> dict:
    """Tier 1: Direct llm.ainvoke() with system prompt + input context."""
    llm = get_llm(
        model=node_config.get("model"),
        temperature=node_config.get("temperature", 0.0),
        max_tokens=node_config.get("max_tokens", 4096),
    )
    system_prompt = node_config.get("system_prompt", "You are a helpful assistant.")
    input_str = build_input_context(state)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=input_str),
    ]

    response = await llm.ainvoke(messages)
    return {"content": text_of(response)}

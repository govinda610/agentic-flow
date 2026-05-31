from langchain.tools import tool
from providers.registry import get_llm
from engine.state import AgentFlowState
from engine.nodes.create_agent import run_agent_node
from engine.node_input import build_input_context, text_of
from langchain.agents import create_agent
import json

def make_delegate_tool(child_configs: list[dict], run_id: str, state: dict):
    """Create a delegate_to_child tool for a supervisor node."""
    child_map = {c["name"]: c for c in child_configs}
    available = ", ".join(child_map.keys())

    @tool(description=(
        "Delegate a specific task to a child specialist agent. "
        "child_name is the agent to delegate to; task is the specific question "
        f"or instruction for it. Available children: {available}."
    ))
    async def delegate_to_child(child_name: str, task: str) -> str:
        if child_name not in child_map:
            return f"Error: Child '{child_name}' not found. Available: {list(child_map.keys())}"

        child_config = child_map[child_name]
        # FIX: use __task__ key so build_input_context() in run_agent_node
        # uses the delegated task directly instead of parent node_outputs context.
        child_state = {
            **state,
            "initial_input": {"__task__": task, "message": task},
        }

        # FIX: resolve the child's string tool names into real tool objects via the
        # shared resolver — create_agent needs BaseTool instances, not name strings.
        from engine.parser import resolve_tools
        child_tools = await resolve_tools(run_id, child_name, child_config, child_state)
        result = await run_agent_node(child_state, child_name, child_config, child_tools)
        return json.dumps(result)

    return delegate_to_child


async def run_supervisor_node(
    state: AgentFlowState,
    node_id: str,
    node_config: dict,
    run_id: str,
) -> dict:
    """Tier 4: Supervisor that routes tasks to named child specialist agents."""
    children     = node_config.get("children", [])
    delegate_tool = make_delegate_tool(children, run_id, state)

    llm = get_llm(
        model=node_config.get("model"),
        temperature=node_config.get("temperature", 0.0),
        max_tokens=node_config.get("max_tokens", 4096),
    )

    # FIX: use build_input_context() for consistent input resolution
    input_str = build_input_context(state)

    agent = create_agent(
        model=llm,
        tools=[delegate_tool],
        system_prompt=node_config.get(
            "system_prompt",
            "You are a supervisor. Decompose the task and delegate each part to the appropriate specialist.",
        ),
    )
    result = await agent.ainvoke({"messages": [{"role": "user", "content": input_str}]})
    return {"output": text_of(result["messages"][-1])}

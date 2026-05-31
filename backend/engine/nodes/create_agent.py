from typing import Optional
from providers.registry import get_llm
from engine.state import AgentFlowState
from engine.node_input import build_input_context, text_of
from pydantic import create_model
from langchain.agents import create_agent

TYPE_MAP = {
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": float,
    "array": list,
}


import re
import keyword

def validate_field_name(name: str) -> str:
    """Sanitize field name to be a valid Python identifier and not a keyword."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
    if not sanitized or sanitized[0].isdigit() or keyword.iskeyword(sanitized):
        return f"field_{sanitized}"
    return sanitized


def build_output_model(fields: list[dict]):
    """Dynamically construct a Pydantic model from UI field definitions."""
    field_defs = {}
    for f in fields:
        name = validate_field_name(f["name"])
        py_type = TYPE_MAP.get(f["type"], str)
        # Fields are optional by default so the model never fails to parse when
        # the agent legitimately has nothing to report for a field. Set
        # "required": true on a field to force the agent to populate it.
        if f.get("required"):
            field_defs[name] = (py_type, ...)
        else:
            field_defs[name] = (Optional[py_type], None)
    return create_model("DynamicOutput", **field_defs)


async def run_agent_node(
    state: AgentFlowState,
    node_id: str,
    node_config: dict,
    tools: list,
) -> dict:
    """
    Tier 2: Standard React Agent with tools and optional structured output.

    Uses create_agent from langchain 1.x:
      - model: BaseChatModel instance
      - tools: list of LangChain tools
      - system_prompt: str (supported in langchain >= 1.0)
      - response_format: Pydantic model class for structured output
                         (langchain wraps it with the appropriate strategy)

    Result shape:
      - With structured_output: result["structured_response"] is a pydantic instance
      - Without: result["messages"][-1] is the final AIMessage
    """
    llm = get_llm(
        model=node_config.get("model"),
        temperature=node_config.get("temperature", 0.0),
        max_tokens=node_config.get("max_tokens", 4096),
    )
    structured_output_config = node_config.get("structured_output")
    input_str = build_input_context(state)

    agent_kwargs = {
        "model": llm,
        "tools": tools,
        "system_prompt": node_config.get("system_prompt", "You are a helpful assistant."),
    }

    # Tier 2 has no native skills=, so attach skill capabilities as middleware
    # (FilesystemMiddleware + SkillsMiddleware) over a workspace-backed filesystem.
    skill_names = node_config.get("skills", [])
    if skill_names:
        from engine.nodes.create_deep_agent import ensure_workspace
        from engine.user_tools import build_skill_middleware
        agent_id = node_config.get("agent_id", node_id)
        workspace = ensure_workspace(agent_id, node_config.get("system_prompt", ""))
        skill_mw = build_skill_middleware(workspace, skill_names)
        if skill_mw:
            agent_kwargs["middleware"] = skill_mw

    if structured_output_config and structured_output_config.get("fields"):
        OutputModel = build_output_model(structured_output_config["fields"])
        agent_kwargs["response_format"] = OutputModel

    agent = create_agent(**agent_kwargs)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": input_str}]})

    if "structured_response" in result and result["structured_response"] is not None:
        structured = result["structured_response"]
        return structured.model_dump() if hasattr(structured, "model_dump") else dict(structured)

    return {"output": text_of(result["messages"][-1])}

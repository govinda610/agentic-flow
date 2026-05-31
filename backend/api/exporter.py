from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from models.workflow import Workflow
from sqlmodel import Session
from database import engine as db_engine
import json

router = APIRouter()

EXPORT_TEMPLATE = '''#!/usr/bin/env python3
"""
Agentic Flow — Exported Workflow Script
Workflow: ###WORKFLOW_NAME###
Generated: ###GENERATED_AT###

This is a standalone, self-contained LangGraph script exported from Agentic Flow.
Run with: python exported_workflow.py

Prerequisites:
    pip install langgraph "langchain>=1.0" langchain-anthropic python-dotenv asteval==0.9.32 aiosqlite
"""

import asyncio
import os
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Any
import operator
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from asteval import Interpreter

load_dotenv()

# ── LLM Setup ────────────────────────────────────────────────────────────────
llm = ChatAnthropic(
    model=os.getenv("GLM_MODEL", "glm-5-turbo"),
    api_key=os.getenv("GLM_API_KEY"),
    base_url=os.getenv("GLM_BASE_URL", "https://api.z.ai/api/anthropic"),
    max_tokens=4096,
)

# ── State ─────────────────────────────────────────────────────────────────────
def _first_error(existing: dict | None, new: dict | None) -> dict | None:
    # Concurrent parallel branches each write _run_error in one superstep; keep the first.
    return existing if existing is not None else new

class WorkflowState(TypedDict):
    initial_input: dict
    node_outputs: Annotated[dict[str, Any], operator.or_]
    parallel_results: Annotated[list, operator.add]
    _run_error: Annotated[dict | None, _first_error]

# ── Edge Condition Evaluator ──────────────────────────────────────────────────
def evaluate_condition(condition: str, state: dict) -> bool:
    aeval = Interpreter(usersyms={"state": state}, minimal=True, no_print=True)
    result = aeval(condition)
    if aeval.error:
        error_msg = "; ".join(str(err) for err in aeval.error)
        raise ValueError(f"Condition error: {error_msg}")
    return bool(result)

# ── Node Functions ────────────────────────────────────────────────────────────
###NODE_FUNCTIONS###

# ── Router Functions ──────────────────────────────────────────────────────────
###ROUTER_FUNCTIONS###

# ── Graph Definition ──────────────────────────────────────────────────────────
def build_graph():
    graph = StateGraph(WorkflowState)
###GRAPH_NODES###
###GRAPH_EDGES###
    return graph.compile()

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    initial_input = {"message": input("Enter your input: ")}
    graph = build_graph()
    state = WorkflowState(
        initial_input=initial_input,
        node_outputs={},
        parallel_results=[],
        _run_error=None,
    )
    result = await graph.ainvoke(state)
    print("\\n=== Final Output ===")
    for node_id, output in result.get("node_outputs", {}).items():
        print(f"\\n[{node_id}]")
        print(output)

if __name__ == "__main__":
    asyncio.run(main())
'''


def _text_of(content) -> str:
    """Extract plain text from a LangChain 1.x content value (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def _generate_node_function(node: dict) -> str:
    node_id     = node["id"]
    node_type   = node.get("type", "agent")
    config      = node.get("config", {})
    system_prompt = config.get("system_prompt", "You are a helpful assistant.")
    name          = config.get("name", node_id)

    if node_type in ("start", "end", "webhook_trigger"):
        return f'''
async def {node_id}(state: WorkflowState) -> dict:
    """{'Start node.' if node_type == 'start' else 'End node.'}"""
    return {{}}
'''

    if node_type == "simple_llm":
        return f'''
async def {node_id}(state: WorkflowState) -> dict:
    """Simple LLM Node: {name}"""
    ii = state.get("initial_input") or {{}}
    if "__task__" in ii:
        context = str(ii["__task__"])
    elif state.get("node_outputs"):
        context = str(state["node_outputs"])
    else:
        context = str(ii.get("message") or ii)
    messages = [
        SystemMessage(content={repr(system_prompt)}),
        HumanMessage(content=context),
    ]
    response = await llm.ainvoke(messages)
    content = _text_of(response.content)
    return {{"node_outputs": {{"{node_id}": {{"content": content}}}}, "_run_error": None}}
'''

    # Default: agent node (React agent without tools for the standalone export)
    # WARNING: deep_agent / supervisor / human_chat features are not fully supported in standalone export.
    return f'''
async def {node_id}(state: WorkflowState) -> dict:
    """Agent Node: {name}
    
    WARNING: deep_agent / supervisor / human_chat features are not fully supported in standalone export.
    This runs as a simplified agent node without tools/delegation/HITL.
    """
    from langchain.agents import create_agent
    ii = state.get("initial_input") or {{}}
    if "__task__" in ii:
        context = str(ii["__task__"])
    elif state.get("node_outputs"):
        context = str(state["node_outputs"])
    else:
        context = str(ii.get("message") or ii)
    agent = create_agent(model=llm, tools=[], system_prompt={repr(system_prompt)})
    result = await agent.ainvoke({{"messages": [{{"role": "user", "content": context}}]}})
    output = _text_of(result["messages"][-1].content)
    return {{"node_outputs": {{"{node_id}": {{"output": output}}}}, "_run_error": None}}
'''


def _generate_graph_nodes(nodes: list[dict]) -> str:
    lines = []
    for node in nodes:
        node_id = node["id"]
        if node["type"] not in ("start", "end"):
            lines.append(f'    graph.add_node("{node_id}", {node_id})')
    return "\n".join(lines)


def _generate_graph_edges(nodes: list[dict], edges: list[dict]) -> str:
    node_map = {n["id"]: n for n in nodes}
    lines = []

    # FIX: 'error' added to special_sources so error-source nodes are routed through
    # the conditional router (which calls resolve_next_node → checks _run_error state)
    # rather than being treated as simple unconditional edges.
    special_sources = {
        e["source"]
        for e in edges
        if e.get("type") in ("conditional", "parallel_fan_out", "error")
    }

    for edge in edges:
        src      = edge["source"]
        tgt      = edge["target"]
        src_type = node_map.get(src, {}).get("type")
        tgt_type = node_map.get(tgt, {}).get("type")

        src_mapped = "START" if src_type == "start" else f'"{src}"'
        tgt_mapped = "END"   if tgt_type == "end"   else f'"{tgt}"'

        if (
            src not in special_sources
            and edge.get("type") in ("normal", "parallel_fan_in")
            and edge.get("condition") is None
        ):
            lines.append(f'    graph.add_edge({src_mapped}, {tgt_mapped})')

    conditional_sources = {e["source"] for e in edges if e.get("type") == "conditional"}
    for src in conditional_sources:
        lines.append(f'    graph.add_conditional_edges("{src}", _router_{src})')

    return "\n".join(lines)


def _generate_router_functions(edges: list[dict]) -> str:
    lines = []
    conditional_sources = {e["source"] for e in edges if e.get("type") == "conditional"}

    for src in conditional_sources:
        src_edges = [e for e in edges if e["source"] == src and e.get("type") == "conditional"]
        conditions = "\n".join([
            f'    if evaluate_condition({repr(e["condition"])}, state): return "{e["target"]}"'
            for e in src_edges
        ])
        router_fn = f'''
def _router_{src}(state: WorkflowState) -> str:
{conditions}
    return END
'''
        lines.append(router_fn)

    return "\n".join(lines)


@router.get("/{workflow_id}/export", response_class=PlainTextResponse)
def export_workflow_code(workflow_id: int):
    """Export a workflow JSON schema as a standalone, executable Python script."""
    with Session(db_engine) as session:
        workflow = session.get(Workflow, workflow_id)
        if not workflow:
            return PlainTextResponse("Workflow not found", status_code=404)

    schema = workflow.workflow_schema
    nodes  = schema.get("nodes", [])
    edges  = schema.get("edges", [])

    from datetime import datetime, timezone

    node_functions   = "\n".join(_generate_node_function(n) for n in nodes)
    router_functions = _generate_router_functions(edges)
    graph_nodes      = _generate_graph_nodes(nodes)
    graph_edges      = _generate_graph_edges(nodes, edges)

    script = (
        EXPORT_TEMPLATE
        .replace("###WORKFLOW_NAME###", workflow.name)
        .replace("###GENERATED_AT###", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        .replace("###NODE_FUNCTIONS###", node_functions)
        .replace("###ROUTER_FUNCTIONS###", router_functions)
        .replace("###GRAPH_NODES###", graph_nodes)
        .replace("###GRAPH_EDGES###", graph_edges)
    )

    return PlainTextResponse(
        script,
        headers={"Content-Disposition": f'attachment; filename="{workflow.name.replace(" ", "_").lower()}.py"'}
    )

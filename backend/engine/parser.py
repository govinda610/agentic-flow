from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from engine.state import AgentFlowState
from engine.edges import resolve_next_node
from engine.nodes.simple_llm import run_simple_llm_node
from engine.nodes.create_agent import run_agent_node
from engine.nodes.create_deep_agent import (
    run_deep_agent_node,
    ensure_workspace,
    make_file_reader_tool,
    make_file_writer_tool,
    make_write_todos_tool,
    make_write_memory_tool,
)
from models.workflow import Workflow
from engine.interpreter import StatefulInterpreter
from engine.tools.web_search import web_search
from database import engine as db_engine
from sqlmodel import Session, select
from datetime import datetime, timezone
from models.inbox import AgentInbox
from langchain.tools import tool
from dataclasses import dataclass
import logging
import json

logger = logging.getLogger(__name__)


def make_send_telegram_message_tool(telegram_chat_id: int | None):
    @tool
    async def send_telegram_message(message: str) -> str:
        """Send a message to the user via Telegram. Non-blocking notification."""
        if not telegram_chat_id:
            return "Error: Telegram is not connected for this run."
        import gateway.state as gateway_state
        if not gateway_state.telegram_gateway:
            return "Error: Telegram bot is not active."
        success = await gateway_state.telegram_gateway.send_message(telegram_chat_id, message)
        return "Message sent successfully." if success else "Failed to send message."
    return send_telegram_message


def make_send_inbox_message_tool(run_id: str, from_node_id: str):
    @tool
    def send_inbox_message(to_node_id: str, content: str) -> str:
        """
        Send a message asynchronously to another agent's inbox in this workflow run.
        The recipient will check their inbox at their next execution cycle.
        """
        with Session(db_engine) as session:
            inbox = AgentInbox(
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                workflow_run_id=run_id,
                message_content=content,
                is_read=False,
            )
            session.add(inbox)
            session.commit()
        return f"Message sent to agent '{to_node_id}' inbox."
    return send_inbox_message


def make_read_inbox_messages_tool(run_id: str, node_id: str):
    @tool
    def read_inbox_messages() -> str:
        """Read all unread messages in your inbox and mark them as read."""
        with Session(db_engine) as session:
            messages = session.exec(
                select(AgentInbox)
                .where(AgentInbox.workflow_run_id == run_id)
                .where(AgentInbox.to_node_id == node_id)
                .where(AgentInbox.is_read == False)  # noqa: E712
            ).all()

            if not messages:
                return "No new messages."

            result = []
            for msg in messages:
                msg.is_read = True
                msg.read_at = datetime.now(timezone.utc)
                session.add(msg)
                result.append(f"From {msg.from_node_id}: {msg.message_content}")
            session.commit()
            return "\n".join(result)
    return read_inbox_messages


class MiddlewareRunner:
    """Executes pre- and post-node middlewares."""

    @staticmethod
    def before_node(state: AgentFlowState, node_config: dict) -> AgentFlowState:
        middlewares = node_config.get("middlewares", [])
        if not middlewares:
            return state

        # Create a copy of the state structure to avoid in-place mutation
        state_copy = {**state}
        for mw in middlewares:
            mw_type = mw.get("type")
            mw_config = mw.get("config", {})

            if mw_type == "pii_removal":
                import re
                email_re = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
                phone_re = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")

                def redact(s: str) -> str:
                    return phone_re.sub("[REDACTED_PHONE]", email_re.sub("[REDACTED_EMAIL]", s))

                if "initial_input" in state_copy and isinstance(state_copy["initial_input"], dict):
                    state_copy["initial_input"] = {
                        k: redact(v) if isinstance(v, str) else v
                        for k, v in state_copy["initial_input"].items()
                    }
                if "telegram_message" in state_copy and isinstance(state_copy["telegram_message"], str):
                    state_copy["telegram_message"] = redact(state_copy["telegram_message"])

            elif mw_type == "guardrails":
                blocklist = mw_config.get("blocklist", ["hack", "bypass instructions"])
                query = str(state_copy.get("initial_input", {})) + " " + str(state_copy.get("telegram_message", ""))
                for word in blocklist:
                    if word.lower() in query.lower():
                        raise ValueError(f"Safety Violation: Input contains blocked phrase '{word}'.")

            elif mw_type == "auto_compaction":
                max_tokens = mw_config.get("max_tokens", 4000)
                outputs = state.get("node_outputs", {})
                if len(str(outputs)) > max_tokens * 4:
                    state_copy["node_outputs"] = {
                        "compacted_history": {"content": "State history compacted to reduce token footprint."}
                    }

        return state_copy

    @staticmethod
    def after_node(node_id: str, output: dict, node_config: dict, state: AgentFlowState) -> dict:
        middlewares = node_config.get("middlewares", [])
        for mw in middlewares:
            mw_type = mw.get("type")
            mw_config = mw.get("config", {})

            if mw_type == "cost_gate":
                max_cost = mw_config.get("max_cost_usd", 0.50)
                with Session(db_engine) as session:
                    from models.run import CostEvent
                    from sqlmodel import func
                    total_cost = session.exec(
                        select(func.sum(CostEvent.estimated_cost_usd))
                        .where(CostEvent.run_id == state["run_id"])
                    ).one() or 0.0
                if total_cost > max_cost:
                    raise ValueError(
                        f"Cost Gate: Cost limit of ${max_cost:.2f} exceeded (spent ${total_cost:.4f})."
                    )

            elif mw_type == "schema_validator":
                schema = mw_config.get("schema")
                if schema and "content" in output:
                    try:
                        parsed = json.loads(output["content"])
                        for field in schema.get("required", []):
                            if field not in parsed:
                                raise ValueError(f"Field '{field}' missing from schema response.")
                    except Exception as exc:
                        raise ValueError(f"Schema validation failed: {exc}")

        return output


def make_sub_workflow_tool(workflow_slug: str):
    """Create a tool that runs a sub-workflow and waits for its completion."""
    import asyncio

    # FIX: @tool name must be passed as first positional argument, not a keyword.
    @tool(f"run_{workflow_slug}", description=f"Delegate a task to the sub-workflow '{workflow_slug}' and return its final output.")
    async def run_sub_workflow(query: str) -> str:
        """Run a named sub-workflow synchronously and return its result."""
        from engine.runner import start_run
        from models.run import WorkflowRun, RunStep

        with Session(db_engine) as session:
            workflow = session.exec(
                select(Workflow).where(
                    (Workflow.template_slug == workflow_slug) |
                    (Workflow.name == workflow_slug)
                )
            ).first()
            if not workflow:
                return f"Error: Sub-workflow '{workflow_slug}' not found."
            workflow_id = workflow.id

        sub_run_id = await start_run(
            workflow_id=workflow_id,
            initial_input={"__task__": query, "message": query},
            telegram_chat_id=None,
        )

        # Poll until completion (max ~60 seconds)
        for _ in range(60):
            await asyncio.sleep(1)
            with Session(db_engine) as session:
                sub_run = session.get(WorkflowRun, sub_run_id)
                if not sub_run:
                    return "Error: Sub-workflow execution lost."
                if sub_run.status == "completed":
                    steps = session.exec(
                        select(RunStep)
                        .where(RunStep.run_id == sub_run_id, RunStep.status == "completed")
                        .order_by(RunStep.id.desc())
                    ).all()
                    for step in steps:
                        out_data = json.loads(step.output_state_json) if step.output_state_json else {}
                        if "output" in out_data:
                            return out_data["output"]
                        if "content" in out_data:
                            return out_data["content"]
                    return "Sub-workflow completed with no text output."
                elif sub_run.status == "failed":
                    return f"Error: Sub-workflow failed: {sub_run.error_message}"
                elif sub_run.status == "cancelled":
                    return "Error: Sub-workflow was cancelled."

        return "Error: Sub-workflow timed out after 60 seconds."

    return run_sub_workflow


@dataclass
class ResolveContext:
    """Everything a tool factory needs to bind itself to the current run/node."""
    run_id: str
    node_id: str
    node_config: dict
    state: AgentFlowState

    @property
    def tool_names(self) -> list:
        return self.node_config.get("tools", [])

    @property
    def telegram_chat_id(self):
        return self.state.get("telegram_chat_id")

    @property
    def mcp_servers(self) -> dict:
        """Per-node MCP server connection map, e.g. {"math": {"command": ..., "transport": "stdio"}}."""
        return self.node_config.get("mcp_servers", {})

    @property
    def workspace(self):
        agent_id = self.node_config.get("agent_id", self.node_id)
        return ensure_workspace(agent_id, self.node_config.get("system_prompt", ""))


def _make_clone_agent_tool(ctx: "ResolveContext"):
    from engine.nodes.clone_agent import make_clone_agent_tool
    return make_clone_agent_tool(ctx.node_id, ctx.node_config, ctx.run_id, ctx.state)


# Registry of built-in tools: name -> factory(ResolveContext) -> BaseTool. Each factory
# binds the tool to the live run/node context. Adding a built-in is one dict entry — no
# new branch in resolve_tools — which is what lets web_search, MCP, etc. plug in cleanly.
BUILTIN_TOOL_FACTORIES = {
    "code_interpreter":      lambda ctx: StatefulInterpreter.make_tool(f"{ctx.run_id}:{ctx.node_id}:main"),
    "send_telegram_message": lambda ctx: make_send_telegram_message_tool(ctx.telegram_chat_id),
    "send_inbox_message":    lambda ctx: make_send_inbox_message_tool(ctx.run_id, ctx.node_id),
    "read_inbox_messages":   lambda ctx: make_read_inbox_messages_tool(ctx.run_id, ctx.node_id),
    "file_reader":           lambda ctx: make_file_reader_tool(ctx.workspace),
    "file_writer":           lambda ctx: make_file_writer_tool(ctx.workspace),
    "write_todos":           lambda ctx: make_write_todos_tool(ctx.workspace),
    "write_memory":          lambda ctx: make_write_memory_tool(ctx.workspace),
    "clone_agent":           _make_clone_agent_tool,
    "web_search":            lambda ctx: web_search,
}


def register_tool(name: str, factory):
    """Register a built-in tool factory: name -> (ResolveContext) -> BaseTool.

    Extension seam so new tools (e.g. web_search) register themselves at import time
    instead of editing resolve_tools.
    """
    BUILTIN_TOOL_FACTORIES[name] = factory


# Set by N3 (DB-backed user Python tools) to a callable(name, ctx) -> BaseTool | None.
# Kept as one hook so bring-your-own tools resolve through the same path as built-ins.
USER_TOOL_LOADER = None

# Set at startup to a callable(names: list) -> server map, so a node can reference stored
# MCP server capabilities by name instead of inlining the connection config.
MCP_SERVER_RESOLVER = None


async def load_mcp_tools(mcp_servers: dict) -> list:
    """Dynamically discover tools from configured MCP servers at runtime.

    `mcp_servers` maps server name -> connection config for langchain-mcp-adapters'
    MultiServerMCPClient. Returns [] when none are configured. The server decides which
    tools exist, so these can't be enumerated ahead of time — they're loaded on demand.
    """
    if not mcp_servers:
        return []
    from langchain_mcp_adapters.client import MultiServerMCPClient
    client = MultiServerMCPClient(mcp_servers)
    return await client.get_tools()


async def resolve_tools(run_id: str, node_id: str, node_config: dict, state: AgentFlowState) -> list:
    """
    Single capability-resolution point: map a node's `tools` name list into resolved
    LangChain tool objects. Used by both the parser (top-level nodes) and the supervisor
    (delegated children), so every tier resolves capabilities identically.

    Resolution sources, in order:
      1. Built-in registry (BUILTIN_TOOL_FACTORIES)
      2. `run_<slug>` sub-workflow delegation
      3. User-defined Python tools (USER_TOOL_LOADER, populated by N3)
      4. MCP servers declared on the node (bulk-loaded dynamically)
    """
    ctx = ResolveContext(run_id, node_id, node_config, state)
    tools = []

    for name in ctx.tool_names:
        factory = BUILTIN_TOOL_FACTORIES.get(name)
        if factory is not None:
            tools.append(factory(ctx))
        elif name.startswith("run_"):
            tools.append(make_sub_workflow_tool(name[4:]))
        elif USER_TOOL_LOADER is not None and (t := USER_TOOL_LOADER(name, ctx)) is not None:
            tools.append(t)
        else:
            logger.warning(f"Unknown tool '{name}' on node '{node_id}' — skipped.")

    # MCP servers may be an inline {name: connection} dict, or a list of stored MCP
    # capability names resolved via MCP_SERVER_RESOLVER.
    servers = ctx.mcp_servers
    if not isinstance(servers, dict):
        servers = MCP_SERVER_RESOLVER(servers) if MCP_SERVER_RESOLVER is not None else {}
    tools.extend(await load_mcp_tools(servers))
    return tools


class WorkflowParser:
    """
    Reads a workflow JSON schema and compiles it into a LangGraph StateGraph.
    The schema IS the program — no code generation, no string eval of node logic.
    """

    def __init__(self, schema: dict, run_id: str):
        self.schema = schema
        self.run_id = run_id
        self.nodes = {n["id"]: n for n in schema["nodes"]}
        self.edges = schema["edges"]

    async def _get_tools_for_node(self, node_id: str, node_config: dict, state: AgentFlowState) -> list:
        """Build the tool list for a node, delegating to the shared resolver."""
        return await resolve_tools(self.run_id, node_id, node_config, state)

    def _make_node_fn(self, node_id: str):
        """Create an async node function for use in LangGraph."""
        node = self.nodes[node_id]
        node_type = node["type"]
        node_config = node.get("config", {})

        async def node_fn(state: AgentFlowState) -> dict:
            try:
                state = MiddlewareRunner.before_node(state, node_config)
                tools = await self._get_tools_for_node(node_id, node_config, state)

                if node_type == "simple_llm":
                    output = await run_simple_llm_node(state, node_config)

                elif node_type == "agent":
                    output = await run_agent_node(state, node_id, node_config, tools)

                elif node_type == "deep_agent":
                    output = await run_deep_agent_node(state, node_id, node_config, tools, self.run_id)

                elif node_type == "supervisor":
                    from engine.nodes.supervisor import run_supervisor_node
                    output = await run_supervisor_node(state, node_id, node_config, self.run_id)

                elif node_type == "telegram_output":
                    import json
                    node_outputs = state.get("node_outputs", {})
                    message_template = node_config.get("message_template")
                    if message_template:
                        resolved_msg = message_template
                        for nid, nout in node_outputs.items():
                            if isinstance(nout, dict):
                                val = nout.get("output") or nout.get("content")
                                val = str(val) if val is not None else json.dumps(nout)
                                resolved_msg = resolved_msg.replace(f"{{{nid}_output}}", val)
                    else:
                        # No template configured: use the most recent node output.
                        last = list(node_outputs.values())[-1] if node_outputs else {}
                        if isinstance(last, dict):
                            resolved_msg = str(last.get("output") or last.get("content") or json.dumps(last))
                        else:
                            resolved_msg = str(last)

                    # Always carry the resolved report as `content` so web runs surface
                    # it as the final output. Telegram delivery is a side effect whose
                    # status is reported separately and must not clobber the content.
                    chat_id = state.get("telegram_chat_id")
                    telegram_sent = False
                    telegram_error = None
                    if chat_id:
                        import gateway.state as gateway_state
                        if gateway_state.telegram_gateway:
                            await gateway_state.telegram_gateway.send_message(chat_id, resolved_msg)
                            telegram_sent = True
                        else:
                            telegram_error = "Telegram gateway not active"
                    else:
                        telegram_error = "No telegram_chat_id in state (web run)"
                    output = {"content": resolved_msg, "telegram_sent": telegram_sent}
                    if telegram_error:
                        output["telegram_error"] = telegram_error

                elif node_type == "human_chat":
                    # FIX: Use dynamic interrupt() instead of static interrupt_before.
                    # interrupt() suspends execution and returns the resume value directly —
                    # no need to manually thread __hitl_response__ through state.
                    from langgraph.types import interrupt
                    response = interrupt({"prompt": node_config.get("prompt", "Waiting for your input...")})
                    output = {"content": response}

                elif node_type in ("start", "end", "webhook_trigger"):
                    output = {}

                else:
                    raise ValueError(f"Unknown node type: {node_type}")

                output = MiddlewareRunner.after_node(node_id, output, node_config, state)

                # FIX: parallel clone targets accumulate into parallel_results (list + operator.add)
                # instead of node_outputs (dict + operator.or_) to prevent branch overwrites.
                if node_config.get("is_parallel_clone_target"):
                    return {
                        "parallel_results": [{"node": node_id, "output": output}],
                        "_run_error": None,
                    }

                return {"node_outputs": {node_id: output}, "_run_error": None}

            except Exception as exc:
                # FIX: GraphInterrupt MUST be re-raised — it is LangGraph's mechanism
                # for pausing execution at an interrupt() call. Swallowing it would
                # convert a HITL pause into an error.
                from langgraph.errors import GraphInterrupt
                import asyncio
                if isinstance(exc, (GraphInterrupt, asyncio.CancelledError)):
                    raise

                import traceback
                logger.error(f"Node {node_id} failed: {exc}")
                return {
                    "node_outputs": {node_id: {}},
                    "_run_error": {
                        "node_id": node_id,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                }

        node_fn.__name__ = f"node_{node_id}"
        return node_fn

    def _make_router_fn(self, node_id: str):
        """Create the routing function after a node, using asteval for conditionals."""
        edges = self.edges
        fan_out_edges = [
            e for e in edges
            if e["source"] == node_id and e.get("type") == "parallel_fan_out"
        ]

        def read_state_path(state: AgentFlowState, path: str):
            """Traverse a dot-separated path in the state dict."""
            value = state
            for part in path.split("."):
                value = value.get(part, {}) if isinstance(value, dict) else {}
            return value

        def router(state: AgentFlowState):
            # FIX: parallel fan-out sends per-item task via __task__ key in initial_input,
            # so the node runner uses the item directly rather than full node_outputs context.
            if fan_out_edges:
                edge = fan_out_edges[0]
                items = read_state_path(state, edge.get("fan_out_from", ""))
                if not isinstance(items, list) or not items:
                    logger.warning(
                        f"Fan-out from '{edge.get('fan_out_from')}' on node '{node_id}' "
                        f"returned empty or non-list. Ending branch."
                    )
                    return END
                return [
                    Send(edge["target"], {
                        **state,
                        "initial_input": {"__task__": item, "item": item},
                    })
                    for item in items
                ]

            next_node = resolve_next_node(node_id, edges, state)
            if next_node is None:
                return END
            return next_node

        router.__name__ = f"router_{node_id}"
        return router

    def compile(self, checkpointer=None) -> tuple:
        """
        Build and compile the LangGraph StateGraph from the JSON schema.

        Args:
            checkpointer: An AsyncSqliteSaver instance (from engine.checkpointer).
                          Callers (runner.py) create/obtain this via get_checkpointer().
                          Subgraphs should pass checkpointer=None.

        Returns:
            (compiled_graph, checkpointer) — checkpointer is the same object passed in.
        """
        graph = StateGraph(AgentFlowState)

        # Nodes that need conditional routing (have conditional, fan_out, OR error edges)
        special_sources = {
            e["source"]
            for e in self.edges
            if e.get("type") in ("conditional", "parallel_fan_out", "error")
        }

        for node in self.schema["nodes"]:
            node_id = node["id"]
            node_type = node["type"]

            if node_type == "subgraph":
                child_wf_id = node["config"]["workflow_id"]
                with Session(db_engine) as session:
                    child_wf = session.get(Workflow, child_wf_id)
                if not child_wf:
                    raise ValueError(f"Nested subgraph workflow ID {child_wf_id} not found.")
                # Subgraph compiled WITHOUT its own checkpointer — parent graph manages state
                child_parser = WorkflowParser(child_wf.workflow_schema, self.run_id)
                child_compiled, _ = child_parser.compile(checkpointer=None)
                graph.add_node(node_id, child_compiled)

            elif node_type not in ("start", "end"):
                graph.add_node(node_id, self._make_node_fn(node_id))

        # Direct (unconditional) edges for nodes that have no special routing
        for edge in self.edges:
            src = edge["source"]
            tgt = edge["target"]
            edge_type = edge.get("type", "normal")

            src_mapped = START if self.nodes.get(src, {}).get("type") == "start" else src
            tgt_mapped = END if self.nodes.get(tgt, {}).get("type") == "end" else tgt

            if (
                src not in special_sources
                and edge_type in ("normal", "parallel_fan_in")
                and edge.get("condition") is None
            ):
                graph.add_edge(src_mapped, tgt_mapped)

        # Conditional routing for nodes with special edges
        routing_sources = {
            e["source"]
            for e in self.edges
            if e.get("type") in ("conditional", "parallel_fan_out", "error")
        }
        for node_id in routing_sources:
            if self.nodes.get(node_id, {}).get("type") not in ("start", "end"):
                graph.add_conditional_edges(node_id, self._make_router_fn(node_id))

        compiled = graph.compile(checkpointer=checkpointer)
        return compiled, checkpointer

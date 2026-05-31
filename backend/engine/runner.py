import asyncio
import uuid
import json
import traceback
from collections import deque
from datetime import datetime, timezone
from sqlmodel import Session, select
from database import engine as db_engine
from models.run import WorkflowRun, RunStep, CostEvent
from models.workflow import Workflow
from engine.parser import WorkflowParser
from engine.state import AgentFlowState

# Cost estimate — adjust to actual GLM pricing
_COST_PER_1K_TOKENS = 0.0006

# Per-run event buffers for SSE reconnect replay
_event_buffers: dict[str, deque] = {}
_event_queues: dict[str, asyncio.Queue] = {}
_event_id_counters: dict[str, int] = {}
_run_tasks: dict[str, asyncio.Task] = {}
_cleanup_tasks: set[asyncio.Task] = set()


def _schedule_run_cleanup(run_id: str):
    """Schedule delayed cleanup of event streams to allow late reconnects."""
    async def delayed_cleanup(rid: str):
        await asyncio.sleep(60)
        _event_queues.pop(rid, None)
        _event_buffers.pop(rid, None)
        _event_id_counters.pop(rid, None)
    task = asyncio.create_task(delayed_cleanup(run_id))
    _cleanup_tasks.add(task)
    task.add_done_callback(_cleanup_tasks.discard)


def _get_queue(run_id: str) -> asyncio.Queue:
    if run_id not in _event_queues:
        _event_queues[run_id] = asyncio.Queue()
        _event_buffers[run_id] = deque(maxlen=200)
        _event_id_counters[run_id] = 0
    return _event_queues[run_id]


DEFAULT_RECURSION_LIMIT = 50


def _resolve_recursion_limit(schema: dict) -> int:
    """Read the workflow's recursion_limit, falling back to a sane default.

    Clamped to [1, 500] so a bad value can't hang or instantly abort a run.
    """
    raw = (schema or {}).get("recursion_limit")
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RECURSION_LIMIT
    return max(1, min(limit, 500))


def _resolve_final_output(values: dict) -> tuple[dict | None, str | None]:
    """Pick the last node's output from final state as the run's result.

    Returns (output_dict, display_text). For dict outputs, prefers the
    'output'/'content' field for the human-readable text.
    """
    outputs = values.get("node_outputs") or {}
    if not outputs:
        return None, None
    last_key = list(outputs.keys())[-1]
    last = outputs[last_key]
    if isinstance(last, dict):
        text = last.get("output") or last.get("content")
        text = str(text) if text is not None else json.dumps(last, default=str)
    else:
        text = str(last)
    return {last_key: last}, text


def _tool_preview(value, limit: int = 200) -> str:
    """Short, JSON-safe preview of a tool's input/output for the live log feed."""
    if isinstance(value, str):
        s = value
    elif isinstance(value, (dict, list)):
        s = json.dumps(value, default=str)
    else:
        s = str(value)
    return s if len(s) <= limit else s[:limit] + "…"


async def _send_final_to_telegram(telegram_chat_id, workflow_name: str, text: str):
    """Deliver the run's final output back to the Telegram chat that started it."""
    import gateway.state as gateway_state
    if not gateway_state.telegram_gateway:
        return
    body = text if len(text) <= 3500 else text[:3500] + "\n…(truncated)"
    await gateway_state.telegram_gateway.send_message(
        telegram_chat_id,
        f"✅ *{workflow_name}* finished:\n\n{body}",
        is_markdown=True,
    )


def sweep_orphaned_runs() -> int:
    """Fail any run left mid-execution by a previous process (call once on startup).

    'running'/'pending' runs had their driver task killed when the server stopped
    and cannot be resumed, so they are marked failed. 'paused' runs are left intact —
    they hold a LangGraph checkpoint and can still be resumed via /resume.
    """
    with Session(db_engine) as session:
        orphans = session.exec(
            select(WorkflowRun).where(WorkflowRun.status.in_(("running", "pending")))
        ).all()
        for run in orphans:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_message = "Interrupted by server restart"
        if orphans:
            session.commit()
    return len(orphans)


async def _emit(run_id: str, event_type: str, data: dict):
    """Push an SSE event to the run's queue and replay buffer."""
    queue = _get_queue(run_id)
    _event_id_counters[run_id] += 1
    event = {
        "id": _event_id_counters[run_id],
        "event": event_type,
        "data": data,
    }
    _event_buffers[run_id].append(event)
    await queue.put(event)


async def stream_events(run_id: str, last_event_id: int = 0):
    """
    AsyncGenerator for SSE: replays buffered events since last_event_id,
    then yields new events as they arrive. Sends heartbeats every 30s.
    """
    if run_id in _event_buffers:
        for event in _event_buffers[run_id]:
            if event["id"] > last_event_id:
                yield event

    queue = _get_queue(run_id)
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=30)
            yield event
            if event.get("event") in ("run_complete", "run_failed", "run_cancelled"):
                break
        except asyncio.TimeoutError:
            yield {"event": "heartbeat", "data": {"run_id": run_id}}


async def start_run(
    workflow_id: int,
    initial_input: dict,
    telegram_chat_id: int | None = None,
) -> str:
    """
    Initialize a workflow run: create DB record, parse schema, execute graph.
    Returns the run_id immediately; execution continues in background.
    """
    run_id = str(uuid.uuid4())

    with Session(db_engine) as session:
        workflow = session.get(Workflow, workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        workflow_schema = workflow.workflow_schema

        run = WorkflowRun(
            id=run_id,
            workflow_id=workflow_id,
            status="pending",
            initial_input_json=json.dumps(initial_input),
            telegram_chat_id=telegram_chat_id,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.commit()

    _run_tasks[run_id] = asyncio.create_task(
        _execute_run(run_id, workflow_schema, initial_input, telegram_chat_id)
    )
    return run_id


async def _execute_run(
    run_id: str,
    schema: dict,
    initial_input: dict,
    telegram_chat_id: int | None,
):
    """Background task: runs the compiled LangGraph graph and emits SSE events."""
    await _emit(run_id, "run_started", {"run_id": run_id, "status": "running"})

    # Note: Using a synchronous Session inside an async context blocks the event loop,
    # which is acceptable for sqlite in this application's scope.
    with Session(db_engine) as session:
        run = session.get(WorkflowRun, run_id)
        run.status = "running"
        session.commit()

    try:
        from engine.checkpointer import get_checkpointer
        checkpointer = await get_checkpointer()

        parser = WorkflowParser(schema, run_id)
        compiled_graph, _ = parser.compile(checkpointer=checkpointer)

        initial_state = AgentFlowState(
            run_id=run_id,
            workflow_id=str(schema.get("workflow_id", "")),
            initial_input=initial_input,
            node_outputs={},
            parallel_results=[],
            _run_error=None,
            __recursion_registry__={},
            telegram_chat_id=telegram_chat_id,
            telegram_message=initial_input.get("message"),
            __hitl_pending__=False,
            __hitl_response__=None,
        )

        # recursion_limit caps how many node steps a run may take before LangGraph
        # aborts (default 50; the workflow schema may override it).
        recursion_limit = _resolve_recursion_limit(schema)
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": recursion_limit}

        # Per-node usage accumulator, populated from on_chat_model_end events
        node_usage: dict[str, dict] = {}

        # TODO(tech-debt): Migrate from v2 to v3 event protocol when LangGraph removes v2.
        # v3 uses a different event schema: method/params/namespace instead of event/name/metadata.
        # See VERIFICATION_ISSUES.md H2 for the full migration analysis.
        async for event in compiled_graph.astream_events(initial_state, config=config):
            event_name = event.get("event", "")
            meta = event.get("metadata", {})

            # FIX: Capture real token usage from LLM events, attributed by langgraph_node
            if event_name == "on_chat_model_end":
                msg = event.get("data", {}).get("output")
                um = getattr(msg, "usage_metadata", None)
                if um:
                    nid = meta.get("langgraph_node", "")
                    acc = node_usage.setdefault(nid, {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    })
                    acc["prompt_tokens"] += um.get("input_tokens", 0)
                    acc["completion_tokens"] += um.get("output_tokens", 0)
                    acc["total_tokens"] += um.get("total_tokens", 0)

            elif event_name == "on_chain_start":
                # FIX: check membership in parser.nodes (robust) not startswith("node_") (fragile)
                nid = event.get("name", "")
                if nid in parser.nodes:
                    node_input = event.get("data", {}).get("input", {})
                    await _emit(run_id, "node_state", {
                        "node_id": nid,
                        "status": "running",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    _persist_step_start(
                        run_id, nid, node_input, parser.nodes.get(nid, {}).get("type", "unknown")
                    )

            elif event_name == "on_chain_end":
                nid = event.get("name", "")
                if nid in parser.nodes:
                    # Extract the clean node output (not the full state-update dict)
                    raw = event.get("data", {}).get("output")
                    node_out = raw.get("node_outputs", {}).get(nid, raw) if isinstance(raw, dict) else raw

                    usage = node_usage.get(nid, {})
                    est_cost = usage.get("total_tokens", 0) / 1000 * _COST_PER_1K_TOKENS
                    await _emit(run_id, "node_state", {
                        "node_id": nid,
                        "status": "completed",
                        "output": node_out,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    if usage:
                        await _emit(run_id, "cost_update", {"node_id": nid, **usage, "estimated_cost_usd": est_cost})
                    _persist_step_complete(run_id, nid, node_out, usage, est_cost)
                    # Reset usage so a node that runs again (retry loop / fan-in revisit)
                    # is costed per-execution, not cumulatively.
                    node_usage.pop(nid, None)

            elif event_name == "on_chain_error":
                nid = event.get("name", "")
                if nid in parser.nodes:
                    err = event.get("data", {}).get("error")
                    err_msg = str(err) if err else "Unknown error"
                    if isinstance(err, BaseException):
                        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
                    else:
                        tb = err_msg
                    _persist_step_failed(run_id, nid, tb)
                    await _emit(run_id, "node_state", {
                        "node_id": nid,
                        "status": "failed",
                        "error": err_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            elif event_name == "on_tool_start":
                await _emit(run_id, "tool_call", {
                    "node_id": meta.get("langgraph_node", ""),
                    "tool": event.get("name", ""),
                    "phase": "start",
                    "input": _tool_preview(event.get("data", {}).get("input", {})),
                })

            elif event_name == "on_tool_end":
                await _emit(run_id, "tool_call", {
                    "node_id": meta.get("langgraph_node", ""),
                    "tool": event.get("name", ""),
                    "phase": "end",
                    "output": _tool_preview(event.get("data", {}).get("output", "")),
                })

        # Check if pause is requested by a node
        state_info = await compiled_graph.aget_state(config)
        if state_info.next:
            next_node = state_info.next[0]
            with Session(db_engine) as session:
                run = session.get(WorkflowRun, run_id)
                run.status = "paused"
                session.commit()

            await _emit(run_id, "run_paused", {"run_id": run_id, "next_node": next_node})

            if telegram_chat_id:
                node_config = parser.nodes.get(next_node, {}).get("config", {})
                prompt_text = node_config.get("prompt", "Waiting for your input...")
                import gateway.state as gateway_state
                if gateway_state.telegram_gateway:
                    await gateway_state.telegram_gateway.send_message(
                        telegram_chat_id,
                        f"❓ *Input required for node '{next_node}'*:\n\n{prompt_text}",
                        is_markdown=True,
                    )
            return

        run_error = state_info.values.get("_run_error")
        err_text = run_error.get("message") if isinstance(run_error, dict) else (str(run_error) if run_error else None)
        final_output, final_text = _resolve_final_output(state_info.values)
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
            run.status = "failed" if run_error else "completed"
            run.completed_at = datetime.now(timezone.utc)
            if err_text:
                run.error_message = err_text
            if final_output is not None:
                run.final_output_json = json.dumps(final_output, default=str)
            session.commit()
            chat_id = run.telegram_chat_id
            workflow = session.get(Workflow, run.workflow_id)
            workflow_name = workflow.name if workflow else "Workflow"

        if run_error:
            await _emit(run_id, "run_failed", {"run_id": run_id, "status": "failed", "error": err_text})
        else:
            await _emit(run_id, "run_complete", {"run_id": run_id, "status": "completed", "final_text": final_text})
            if chat_id and final_text:
                await _send_final_to_telegram(chat_id, workflow_name, final_text)

    except asyncio.CancelledError:
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
            if run:
                run.status = "cancelled"
                run.completed_at = datetime.now(timezone.utc)
                session.commit()
        await _emit(run_id, "run_cancelled", {"run_id": run_id, "status": "cancelled"})
        raise

    except Exception as exc:
        import traceback
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
            if run:
                run.status = "failed"
                run.error_message = str(exc)
                run.completed_at = datetime.now(timezone.utc)
                session.commit()

        await _emit(run_id, "run_failed", {
            "run_id": run_id,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })

    finally:
        _run_tasks.pop(run_id, None)
        _schedule_run_cleanup(run_id)


async def resume_run(run_id: str, user_input: str):
    """Resume a paused workflow run by supplying the human response."""
    with Session(db_engine) as session:
        run = session.get(WorkflowRun, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        if run.status != "paused":
            raise ValueError(f"Run {run_id} is not paused (status: {run.status})")
        run.status = "running"
        session.commit()
        workflow = session.get(Workflow, run.workflow_id)
        schema = workflow.workflow_schema

    from engine.checkpointer import get_checkpointer
    checkpointer = await get_checkpointer()
    parser = WorkflowParser(schema, run_id)
    compiled_graph, _ = parser.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": _resolve_recursion_limit(schema)}

    await _emit(run_id, "run_resumed", {"run_id": run_id, "status": "running"})
    _run_tasks[run_id] = asyncio.create_task(
        _resume_execute_run(run_id, compiled_graph, config, parser, run.telegram_chat_id, user_input)
    )


async def _resume_execute_run(
    run_id: str,
    compiled_graph,
    config: dict,
    parser: WorkflowParser,
    telegram_chat_id: int | None,
    resume_value: str,
):
    """Continue execution after a HITL interrupt with the user's response value."""
    try:
        from langgraph.types import Command

        node_usage: dict[str, dict] = {}

        # FIX: Command(resume=value) delivers the resume value to interrupt(),
        # which then returns it as the result of the interrupt() call in human_chat node_fn.
        async for event in compiled_graph.astream_events(
            Command(resume=resume_value), config=config,
            # TODO(tech-debt): Same v2→v3 migration note as _execute_run above.
        ):
            event_name = event.get("event", "")
            meta = event.get("metadata", {})

            if event_name == "on_chat_model_end":
                msg = event.get("data", {}).get("output")
                um = getattr(msg, "usage_metadata", None)
                if um:
                    nid = meta.get("langgraph_node", "")
                    acc = node_usage.setdefault(nid, {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    })
                    acc["prompt_tokens"] += um.get("input_tokens", 0)
                    acc["completion_tokens"] += um.get("output_tokens", 0)
                    acc["total_tokens"] += um.get("total_tokens", 0)

            elif event_name == "on_chain_start":
                nid = event.get("name", "")
                if nid in parser.nodes:
                    node_input = event.get("data", {}).get("input", {})
                    await _emit(run_id, "node_state", {
                        "node_id": nid,
                        "status": "running",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    _persist_step_start(
                        run_id, nid, node_input, parser.nodes.get(nid, {}).get("type", "unknown")
                    )

            elif event_name == "on_chain_end":
                nid = event.get("name", "")
                if nid in parser.nodes:
                    raw = event.get("data", {}).get("output") or {}
                    node_out = raw.get("node_outputs", {}).get(nid, raw) if isinstance(raw, dict) else raw
                    usage = node_usage.get(nid, {})
                    est_cost = usage.get("total_tokens", 0) / 1000 * _COST_PER_1K_TOKENS
                    await _emit(run_id, "node_state", {
                        "node_id": nid,
                        "status": "completed",
                        "output": node_out,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    if usage:
                        await _emit(run_id, "cost_update", {"node_id": nid, **usage, "estimated_cost_usd": est_cost})
                    _persist_step_complete(run_id, nid, node_out, usage, est_cost)

            elif event_name == "on_tool_start":
                await _emit(run_id, "tool_call", {
                    "node_id": meta.get("langgraph_node", ""),
                    "tool": event.get("name", ""),
                    "phase": "start",
                    "input": _tool_preview(event.get("data", {}).get("input", {})),
                })

            elif event_name == "on_tool_end":
                await _emit(run_id, "tool_call", {
                    "node_id": meta.get("langgraph_node", ""),
                    "tool": event.get("name", ""),
                    "phase": "end",
                    "output": _tool_preview(event.get("data", {}).get("output", "")),
                })

        # Check if still paused (multiple HITL nodes in sequence)
        state_info = await compiled_graph.aget_state(config)
        if state_info.next:
            next_node = state_info.next[0]
            with Session(db_engine) as session:
                run = session.get(WorkflowRun, run_id)
                run.status = "paused"
                session.commit()
            await _emit(run_id, "run_paused", {"run_id": run_id, "next_node": next_node})
            if telegram_chat_id:
                node_config = parser.nodes.get(next_node, {}).get("config", {})
                prompt_text = node_config.get("prompt", "Waiting for your input...")
                import gateway.state as gateway_state
                if gateway_state.telegram_gateway:
                    await gateway_state.telegram_gateway.send_message(
                        telegram_chat_id,
                        f"❓ *Input required for '{next_node}'*:\n\n{prompt_text}",
                        is_markdown=True,
                    )
            return

        run_error = state_info.values.get("_run_error")
        err_text = run_error.get("message") if isinstance(run_error, dict) else (str(run_error) if run_error else None)
        final_output, final_text = _resolve_final_output(state_info.values)
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
            run.status = "failed" if run_error else "completed"
            run.completed_at = datetime.now(timezone.utc)
            if err_text:
                run.error_message = err_text
            if final_output is not None:
                run.final_output_json = json.dumps(final_output, default=str)
            session.commit()
            chat_id = run.telegram_chat_id
            workflow = session.get(Workflow, run.workflow_id)
            workflow_name = workflow.name if workflow else "Workflow"

        if run_error:
            await _emit(run_id, "run_failed", {"run_id": run_id, "status": "failed", "error": err_text})
        else:
            await _emit(run_id, "run_complete", {"run_id": run_id, "status": "completed", "final_text": final_text})
            if chat_id and final_text:
                await _send_final_to_telegram(chat_id, workflow_name, final_text)

    except asyncio.CancelledError:
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
            if run:
                run.status = "cancelled"
                run.completed_at = datetime.now(timezone.utc)
                session.commit()
        await _emit(run_id, "run_cancelled", {"run_id": run_id, "status": "cancelled"})
        raise

    except Exception as exc:
        import traceback
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
            if run:
                run.status = "failed"
                run.error_message = str(exc)
                run.completed_at = datetime.now(timezone.utc)
                session.commit()
        await _emit(run_id, "run_failed", {
            "run_id": run_id,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })

    finally:
        _run_tasks.pop(run_id, None)
        _schedule_run_cleanup(run_id)


def _persist_step_start(run_id: str, node_id: str, state: dict, node_type: str = "unknown"):
    with Session(db_engine) as session:
        step = RunStep(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            status="running",
            input_state_json=json.dumps(state, default=str),
            started_at=datetime.now(timezone.utc),
        )
        session.add(step)
        session.commit()


def _persist_step_complete(
    run_id: str,
    node_id: str,
    output: dict,
    usage: dict | None = None,
    estimated_cost: float = 0.0,
):
    with Session(db_engine) as session:
        step = session.exec(
            select(RunStep)
            .where(
                RunStep.run_id == run_id,
                RunStep.node_id == node_id,
                RunStep.status == "running",
            )
            .order_by(RunStep.id.desc())
        ).first()
        if step:
            step.status = "completed"
            step.output_state_json = json.dumps(output, default=str)
            step.tokens_used = (usage or {}).get("total_tokens", 0)
            step.estimated_cost_usd = estimated_cost
            step.completed_at = datetime.now(timezone.utc)
            if usage and usage.get("total_tokens", 0) > 0:
                session.add(CostEvent(
                    run_id=run_id,
                    node_id=node_id,
                    provider="z.ai",
                    model="glm-5-turbo",
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    estimated_cost_usd=estimated_cost,
                ))
            session.commit()


def _persist_step_failed(run_id: str, node_id: str, error_traceback: str):
    """Mark the most-recent running step for a node as failed and store its traceback."""
    with Session(db_engine) as session:
        step = session.exec(
            select(RunStep)
            .where(
                RunStep.run_id == run_id,
                RunStep.node_id == node_id,
                RunStep.status == "running",
            )
            .order_by(RunStep.id.desc())
        ).first()
        if step:
            step.status = "failed"
            step.error_traceback = error_traceback
            step.completed_at = datetime.now(timezone.utc)
            session.commit()

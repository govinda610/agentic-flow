from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from engine.runner import start_run, stream_events
from models.run import WorkflowRun, RunStep
from sqlmodel import Session, select
from database import engine as db_engine
from pydantic import BaseModel
import json

router = APIRouter()


class StartRunRequest(BaseModel):
    workflow_id: int
    initial_input: dict = {}
    telegram_chat_id: int | None = None


@router.post("/start")
async def api_start_run(body: StartRunRequest):
    run_id = await start_run(body.workflow_id, body.initial_input, body.telegram_chat_id)
    return {"run_id": run_id, "status": "started"}


@router.get("/{run_id}/stream")
async def api_stream_run(run_id: str, request: Request, last_event_id: int = 0):
    # Parse last_event_id from header fallback if query parameter is empty/zero
    header_val = request.headers.get("Last-Event-ID")
    if header_val:
        try:
            last_event_id = int(header_val)
        except ValueError:
            pass

    async def event_generator():
        async for event in stream_events(run_id, last_event_id):
            sse: dict = {
                "event": event.get("event"),
                "data": json.dumps(event.get("data", {})),
            }
            # sse_starlette requires the SSE id to be a string; our buffer uses int ids.
            # Heartbeats have no id and must be left out.
            if event.get("id") is not None:
                sse["id"] = str(event["id"])
            yield sse
    return EventSourceResponse(event_generator())


@router.get("/{run_id}/steps")
def api_get_steps(run_id: str):
    with Session(db_engine) as session:
        steps = session.exec(select(RunStep).where(RunStep.run_id == run_id)).all()
    return steps


@router.get("/{run_id}/steps/{node_id}")
def api_get_step(run_id: str, node_id: str):
    with Session(db_engine) as session:
        step = session.exec(
            select(RunStep)
            .where(RunStep.run_id == run_id, RunStep.node_id == node_id)
            .order_by(RunStep.id.desc())
        ).first()
    if not step:
        return JSONResponse(status_code=404, content={"detail": "Step not found"})
    return step


@router.get("/{run_id}/inbox/{node_id}")
def api_get_inbox_messages(run_id: str, node_id: str):
    from models.inbox import AgentInbox
    with Session(db_engine) as session:
        messages = session.exec(
            select(AgentInbox)
            .where(AgentInbox.workflow_run_id == run_id)
            .where(AgentInbox.to_node_id == node_id)
        ).all()
    return messages


@router.post("/{run_id}/pause")
async def api_pause_run(run_id: str):
    """Confirm the UI is aware of a HITL pause. The pause itself is triggered by interrupt()."""
    with Session(db_engine) as session:
        run = session.get(WorkflowRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.status != "paused":
            raise HTTPException(status_code=409, detail="Run is not currently paused.")
    return {"run_id": run_id, "status": "paused"}


@router.post("/{run_id}/resume")
async def api_resume_run(run_id: str, body: dict):
    from engine.runner import resume_run
    await resume_run(run_id, body.get("value", "approved"))
    return {"run_id": run_id, "status": "resumed"}


@router.post("/{run_id}/cancel")
async def api_cancel_run(run_id: str):
    from engine.runner import _run_tasks
    task = _run_tasks.get(run_id)
    if task and not task.done():
        # A live task owns its own status transition via its CancelledError
        # handler; just request cancellation so the two don't race the DB row.
        task.cancel()
    else:
        # No live task (e.g. a paused or already-orphaned run): nobody else will
        # write the terminal status, so do it here without clobbering a finished run.
        from datetime import datetime, timezone
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
            if run and run.status not in ("completed", "failed", "cancelled"):
                run.status = "cancelled"
                run.completed_at = datetime.now(timezone.utc)
                session.commit()
    return {"run_id": run_id, "status": "cancelled"}

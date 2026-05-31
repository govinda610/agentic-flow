from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session
from models.workflow import Workflow, WebhookToken
from models.run import WorkflowRun, RunStep
from models.inbox import AgentInbox
from pydantic import BaseModel
from datetime import datetime, timezone
import json

router = APIRouter()

class WorkflowSave(BaseModel):
    name: str
    description: str | None = None
    workflow_schema: dict
    cron_schedule: str | None = None

class WorkflowRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    workflow_schema: dict
    cron_schedule: str | None = None
    is_template: bool
    template_slug: str | None = None

@router.get("/")
def list_workflows(session: Session = Depends(get_session)):
    workflows = session.exec(select(Workflow)).all()
    return [
        WorkflowRead(
            id=w.id, name=w.name, description=w.description,
            workflow_schema=w.workflow_schema, cron_schedule=w.cron_schedule,
            is_template=w.is_template, template_slug=w.template_slug
        ) for w in workflows
    ]

@router.get("/{workflow_id}")
def get_workflow(workflow_id: int, session: Session = Depends(get_session)):
    workflow = session.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowRead(
        id=workflow.id, name=workflow.name, description=workflow.description,
        workflow_schema=workflow.workflow_schema, cron_schedule=workflow.cron_schedule,
        is_template=workflow.is_template, template_slug=workflow.template_slug
    )

@router.post("/")
def save_workflow(data: WorkflowSave, session: Session = Depends(get_session)):
    raw_id = data.workflow_schema.get("workflow_id")
    if raw_id is not None and not isinstance(raw_id, int):
        raise HTTPException(status_code=422, detail="workflow_schema.workflow_id must be an integer")

    workflow = None
    if raw_id:
        workflow = session.get(Workflow, raw_id)

    if not workflow:
        workflow = Workflow(
            name=data.name,
            description=data.description,
            schema_blob=json.dumps(data.workflow_schema),
            cron_schedule=data.cron_schedule,
            is_template=False
        )
        session.add(workflow)
    else:
        workflow.name = data.name
        workflow.description = data.description
        workflow.schema_blob = json.dumps(data.workflow_schema)
        workflow.cron_schedule = data.cron_schedule
        workflow.updated_at = datetime.now(timezone.utc)  # explicitly update timestamp
        session.add(workflow)

    session.commit()
    session.refresh(workflow)

    # Write the assigned DB id back into the schema blob under the same key the
    # lookup above reads, so a later save updates this row instead of duplicating it.
    schema = json.loads(workflow.schema_blob)
    schema["workflow_id"] = workflow.id
    workflow.schema_blob = json.dumps(schema)
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    # Sync schedule with APScheduler
    from engine.scheduler import update_workflow_job
    update_workflow_job(workflow.id, workflow.cron_schedule)

    return WorkflowRead(
        id=workflow.id, name=workflow.name, description=workflow.description,
        workflow_schema=workflow.workflow_schema, cron_schedule=workflow.cron_schedule,
        is_template=workflow.is_template, template_slug=workflow.template_slug
    )

@router.delete("/{workflow_id}")
def delete_workflow(workflow_id: int, session: Session = Depends(get_session)):
    workflow = session.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Cascade-delete dependents in child-before-parent order (foreign_keys=ON enforces this).
    runs = session.exec(select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)).all()
    for run in runs:
        # Delete RunStep and AgentInbox rows that FK to this run
        for step in session.exec(select(RunStep).where(RunStep.run_id == run.id)).all():
            session.delete(step)
        for msg in session.exec(select(AgentInbox).where(AgentInbox.workflow_run_id == run.id)).all():
            session.delete(msg)
        session.delete(run)

    for token in session.exec(select(WebhookToken).where(WebhookToken.workflow_id == workflow_id)).all():
        session.delete(token)

    session.delete(workflow)
    session.commit()

    # Remove schedule from APScheduler
    from engine.scheduler import remove_workflow_job
    remove_workflow_job(workflow_id)

    return {"ok": True}

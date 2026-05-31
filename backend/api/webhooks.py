from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session
from models.workflow import Workflow, WebhookToken
from engine.runner import start_run
from pydantic import BaseModel
import secrets
import json

router = APIRouter()


class WebhookRegisterRequest(BaseModel):
    workflow_id: int


class WebhookTriggerPayload(BaseModel):
    message: str = ""
    data: dict = {}


@router.post("/register")
def register_webhook(body: WebhookRegisterRequest, session: Session = Depends(get_session)):
    """
    Register a new webhook URL for a workflow.
    Returns a unique token that can be embedded in an external webhook URL:
        POST /api/webhooks/{token}
    """
    workflow = session.get(Workflow, body.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Revoke old token for this workflow if one exists
    existing = session.exec(
        select(WebhookToken).where(WebhookToken.workflow_id == body.workflow_id)
    ).first()
    if existing:
        session.delete(existing)

    token = secrets.token_urlsafe(32)
    wh = WebhookToken(token=token, workflow_id=body.workflow_id)
    session.add(wh)
    session.commit()

    return {
        "token": token,
        "webhook_url": f"/api/webhooks/{token}",
        "workflow_id": body.workflow_id,
    }


@router.post("/{token}")
async def trigger_webhook(token: str, payload: WebhookTriggerPayload):
    """
    Trigger a workflow run via its registered webhook token.
    Used by external services (GitHub, Zapier, n8n, etc.) to kick off workflows.
    """
    from database import engine as db_engine
    with Session(db_engine) as session:
        wh = session.exec(
            select(WebhookToken).where(WebhookToken.token == token)
        ).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Invalid or revoked webhook token")
        workflow_id = wh.workflow_id

    run_id = await start_run(
        workflow_id=workflow_id,
        initial_input={
            "message": payload.message,
            "source": "webhook",
            "webhook_data": payload.data,
        },
        telegram_chat_id=None,
    )
    return {"run_id": run_id, "status": "started", "source": "webhook"}


@router.get("/list/{workflow_id}")
def list_webhook_tokens(workflow_id: int, session: Session = Depends(get_session)):
    """List all active webhook tokens for a workflow."""
    tokens = session.exec(
        select(WebhookToken).where(WebhookToken.workflow_id == workflow_id)
    ).all()
    return [{"token": t.token[:8] + "...", "created_at": t.created_at} for t in tokens]


@router.delete("/{token}")
def revoke_webhook(token: str, session: Session = Depends(get_session)):
    """Revoke a webhook token."""
    wh = session.exec(select(WebhookToken).where(WebhookToken.token == token)).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Token not found")
    session.delete(wh)
    session.commit()
    return {"ok": True, "revoked": token[:8] + "..."}

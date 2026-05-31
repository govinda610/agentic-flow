from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session
from models.capability import Capability
from pydantic import BaseModel
from datetime import datetime, timezone
import json

router = APIRouter()

VALID_KINDS = {"tool", "skill", "mcp"}


class CapabilitySave(BaseModel):
    name: str
    kind: str            # "tool" | "skill" | "mcp"
    description: str | None = None
    config: dict = {}


class CapabilityRead(BaseModel):
    id: int
    name: str
    kind: str
    description: str | None
    config: dict


def _read(c: Capability) -> CapabilityRead:
    return CapabilityRead(
        id=c.id, name=c.name, kind=c.kind,
        description=c.description, config=json.loads(c.config_json),
    )


@router.get("/", response_model=list[CapabilityRead])
def list_capabilities(kind: str | None = None, session: Session = Depends(get_session)):
    stmt = select(Capability)
    if kind:
        stmt = stmt.where(Capability.kind == kind)
    return [_read(c) for c in session.exec(stmt).all()]


# Human-readable descriptions for the built-in tools registered in the engine.
BUILTIN_TOOL_DESCRIPTIONS = {
    "code_interpreter":      "Run Python in a stateful sandbox REPL.",
    "web_search":            "Search the web (DuckDuckGo) and return results.",
    "send_telegram_message": "Send a message to the run's Telegram chat.",
    "send_inbox_message":    "Send a message to another agent's inbox.",
    "read_inbox_messages":   "Read messages from this agent's inbox.",
    "file_reader":           "Read a file from the agent workspace.",
    "file_writer":           "Write a file to the agent workspace.",
    "write_todos":           "Maintain a todo list in the workspace.",
    "write_memory":          "Persist notes to the agent's memory.",
    "clone_agent":           "Spawn parallel clones of this agent for sub-tasks.",
}


@router.get("/builtins")
def list_builtin_tools():
    """Read-only list of built-in tools the engine provides (not stored in the DB)."""
    from engine.parser import BUILTIN_TOOL_FACTORIES
    return [
        {"name": name, "description": BUILTIN_TOOL_DESCRIPTIONS.get(name, "")}
        for name in BUILTIN_TOOL_FACTORIES
    ]


@router.get("/{capability_id}", response_model=CapabilityRead)
def get_capability(capability_id: int, session: Session = Depends(get_session)):
    cap = session.get(Capability, capability_id)
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")
    return _read(cap)


@router.post("/", response_model=CapabilityRead)
def create_capability(data: CapabilitySave, session: Session = Depends(get_session)):
    if data.kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {sorted(VALID_KINDS)}")
    existing = session.exec(
        select(Capability).where(Capability.name == data.name, Capability.kind == data.kind)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A {data.kind} named '{data.name}' already exists")
    cap = Capability(
        name=data.name, kind=data.kind, description=data.description,
        config_json=json.dumps(data.config),
    )
    session.add(cap)
    session.commit()
    session.refresh(cap)
    return _read(cap)


@router.put("/{capability_id}", response_model=CapabilityRead)
def update_capability(capability_id: int, data: CapabilitySave, session: Session = Depends(get_session)):
    if data.kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {sorted(VALID_KINDS)}")
    cap = session.get(Capability, capability_id)
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")
    cap.name = data.name
    cap.kind = data.kind
    cap.description = data.description
    cap.config_json = json.dumps(data.config)
    cap.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(cap)
    return _read(cap)


@router.delete("/{capability_id}")
def delete_capability(capability_id: int, session: Session = Depends(get_session)):
    cap = session.get(Capability, capability_id)
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")
    session.delete(cap)
    session.commit()
    return {"ok": True}

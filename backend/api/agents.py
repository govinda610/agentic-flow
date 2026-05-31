from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session
from models.agent import Agent
from pydantic import BaseModel
import json

router = APIRouter()

class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str
    model: str = "glm-5-turbo"
    node_type: str = "agent"
    tools: list[str] = []
    config: dict = {}

class AgentRead(BaseModel):
    id: int
    name: str
    description: str | None
    system_prompt: str
    model: str
    node_type: str
    tools: list[str]
    config: dict

@router.get("/", response_model=list[AgentRead])
def list_agents(session: Session = Depends(get_session)):
    agents = session.exec(select(Agent)).all()
    return [AgentRead(
        id=a.id, name=a.name, description=a.description,
        system_prompt=a.system_prompt, model=a.model, node_type=a.node_type,
        tools=json.loads(a.tools_json), config=json.loads(a.config_json)
    ) for a in agents]

@router.post("/", response_model=AgentRead)
def create_agent_endpoint(data: AgentCreate, session: Session = Depends(get_session)):
    agent = Agent(
        name=data.name,
        description=data.description,
        system_prompt=data.system_prompt,
        model=data.model,
        node_type=data.node_type,
        tools_json=json.dumps(data.tools),
        config_json=json.dumps(data.config),
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return AgentRead(
        id=agent.id, name=agent.name, description=agent.description,
        system_prompt=agent.system_prompt, model=agent.model, node_type=agent.node_type,
        tools=data.tools, config=data.config
    )

@router.put("/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: int, data: AgentCreate, session: Session = Depends(get_session)):
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    from datetime import datetime, timezone
    agent.name = data.name
    agent.description = data.description
    agent.system_prompt = data.system_prompt
    agent.model = data.model
    agent.node_type = data.node_type
    agent.tools_json = json.dumps(data.tools)
    agent.config_json = json.dumps(data.config)
    agent.updated_at = datetime.now(timezone.utc)  # explicitly update timestamp
    session.commit()
    session.refresh(agent)
    return AgentRead(
        id=agent.id, name=agent.name, description=agent.description,
        system_prompt=agent.system_prompt, model=agent.model, node_type=agent.node_type,
        tools=data.tools, config=data.config
    )

@router.delete("/{agent_id}")
def delete_agent(agent_id: int, session: Session = Depends(get_session)):
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    session.delete(agent)
    session.commit()
    return {"ok": True}

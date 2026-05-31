from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone

class AgentInbox(SQLModel, table=True):
    __tablename__ = "agent_inboxes"

    id: Optional[int] = Field(default=None, primary_key=True)
    from_node_id: str = Field(index=True)
    to_node_id: str = Field(index=True)
    workflow_run_id: str = Field(foreign_key="workflow_runs.id")
    message_content: str
    is_read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    read_at: Optional[datetime] = None

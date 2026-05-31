from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone
import json

class Agent(SQLModel, table=True):
    __tablename__ = "agents"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    system_prompt: str
    model: str = Field(default="glm-5-turbo")
    node_type: str = Field(default="agent")  # simple_llm | agent | deep_agent | supervisor
    tools_json: str = Field(default="[]")    # JSON array of tool names
    config_json: str = Field(default="{}")   # JSON: max_depth, max_breadth, etc.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def tools(self) -> list[str]:
        return json.loads(self.tools_json)

    @property
    def config(self) -> dict:
        return json.loads(self.config_json)

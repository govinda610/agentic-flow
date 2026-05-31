from sqlmodel import SQLModel, Field, UniqueConstraint
from typing import Optional
from datetime import datetime, timezone


class Capability(SQLModel, table=True):
    """A reusable capability referenced by name across workflows.

    One table serves all three kinds; the kind-specific payload lives in config_json:
      - kind="tool":  {"code": "<python defining an @tool>"}
      - kind="skill": {"content": "<skill markdown>"}
      - kind="mcp":   {"servers": {<MultiServerMCPClient connection map>}}
    """
    __tablename__ = "capabilities"
    __table_args__ = (UniqueConstraint("name", "kind", name="uq_capability_name_kind"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    kind: str = Field(index=True)  # "tool" | "skill" | "mcp"
    description: Optional[str] = None
    config_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone
import json

class Workflow(SQLModel, table=True):
    __tablename__ = "workflows"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    schema_blob: str = Field(default="{}")          # Full JSON schema blob
    cron_schedule: Optional[str] = Field(default=None)  # Cron expression for schedules
    is_template: bool = Field(default=False)
    template_slug: Optional[str] = Field(default=None, index=True)  # e.g. "data_science_loop"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def workflow_schema(self) -> dict:
        """Returns the parsed JSON schema. Named workflow_schema to avoid conflict with Pydantic's .schema()."""
        return json.loads(self.schema_blob)

class WebhookToken(SQLModel, table=True):
    __tablename__ = "webhook_tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(unique=True, index=True)
    workflow_id: int = Field(foreign_key="workflows.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

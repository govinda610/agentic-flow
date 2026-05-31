from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone

class WorkflowRun(SQLModel, table=True):
    __tablename__ = "workflow_runs"

    id: str = Field(primary_key=True)              # UUID string
    workflow_id: int = Field(foreign_key="workflows.id")
    status: str = Field(default="pending")          # pending|running|paused|completed|failed|cancelled
    initial_input_json: str = Field(default="{}")
    final_output_json: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    telegram_chat_id: Optional[int] = None          # Set if triggered via Telegram

class RunStep(SQLModel, table=True):
    __tablename__ = "run_steps"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="workflow_runs.id", index=True)
    node_id: str = Field(index=True)
    node_type: str
    status: str                                     # pending|running|completed|failed|skipped
    input_state_json: Optional[str] = None
    output_state_json: Optional[str] = None
    error_traceback: Optional[str] = None
    tokens_used: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class CostEvent(SQLModel, table=True):
    __tablename__ = "cost_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    node_id: str
    provider: str
    model: str
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ConsoleLog(SQLModel, table=True):
    __tablename__ = "console_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    node_id: Optional[str] = None
    level: str = Field(default="info")              # info|warning|error|debug
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

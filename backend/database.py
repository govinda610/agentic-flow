from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy import event
from config import settings
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

# Synchronous engine for SQLModel — the LangGraph checkpointer uses its own
# separate aiosqlite connection to a different DB file (see engine/checkpointer.py).
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False}
)

@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Keep local SQLite reliable under concurrent SSE, checkpoint, and run writes."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

def get_session():
    with Session(engine) as session:
        yield session

def init_db():
    """Create all tables if they don't exist. Called synchronously at startup."""
    # Import all models to register them with SQLModel metadata
    from models.agent import Agent
    from models.workflow import Workflow, WebhookToken
    from models.run import WorkflowRun, RunStep, CostEvent, ConsoleLog
    from models.inbox import AgentInbox
    from models.capability import Capability

    SQLModel.metadata.create_all(engine)

def seed_templates():
    """Seed pre-built templates on first startup (idempotent). Called synchronously at startup."""
    from models.workflow import Workflow

    templates_dir = Path(__file__).parent / "templates"
    if not templates_dir.exists():
        return

    with Session(engine) as session:
        for template_file in sorted(templates_dir.glob("*.json")):
            slug = template_file.stem
            existing = session.exec(
                select(Workflow).where(Workflow.template_slug == slug)
            ).first()
            if existing:
                continue

            try:
                schema = json.loads(template_file.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Skipping template {slug}: {exc}")
                continue

            workflow = Workflow(
                name=schema.get("name", slug),
                description=schema.get("description", ""),
                schema_blob=json.dumps(schema),
                is_template=True,
                template_slug=slug,
            )
            session.add(workflow)
        session.commit()

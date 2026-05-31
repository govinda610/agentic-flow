from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, seed_templates
from config import settings
from gateway.telegram import TelegramGateway
import gateway.state as gateway_state
from api import agents, workflows, runs, copilot, gateway as gateway_router, webhooks, exporter, capabilities
from engine.scheduler import start_scheduler, scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    # 1. Initialize DB schema (sync — blocks briefly at startup, intentional)
    init_db()
    # 2. Seed templates if DB is empty
    seed_templates()
    # 2b. Wire DB-backed capabilities into the resolver (user Python tools + MCP servers)
    from engine import parser
    from engine.user_tools import load_user_tool, load_mcp_server_map
    parser.USER_TOOL_LOADER = load_user_tool
    parser.MCP_SERVER_RESOLVER = load_mcp_server_map
    # 3. Fail runs orphaned by a previous process (resumable paused runs are kept)
    from engine.runner import sweep_orphaned_runs
    swept = sweep_orphaned_runs()
    if swept:
        import logging
        logging.getLogger(__name__).info(f"Marked {swept} orphaned run(s) as failed on startup")
    # 4. Start APScheduler and register crons
    start_scheduler()
    # 4. Start Telegram bot (if token configured)
    if settings.telegram_bot_token:
        try:
            tg = TelegramGateway(settings.telegram_bot_token)
            await tg.start()
            gateway_state.telegram_gateway = tg
            # Register existing workflows
            from sqlmodel import Session, select
            from database import engine as db_engine
            from models.workflow import Workflow
            with Session(db_engine) as session:
                wfs = session.exec(select(Workflow)).all()
                for wf in wfs:
                    keyword = wf.template_slug or wf.name.lower().replace(" ", "_")
                    await tg.register_workflow(wf.id, keyword)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Failed to start Telegram gateway: {exc}")

    yield  # FastAPI serves requests here

    # ── Shutdown ─────────────────────────────────────────────
    if gateway_state.telegram_gateway:
        try:
            await gateway_state.telegram_gateway.stop()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Failed to stop Telegram gateway: {exc}")
    try:
        scheduler.shutdown()
    except Exception:
        pass
    # Close the shared LangGraph checkpointer connection
    try:
        from engine.checkpointer import _checkpointer
        if _checkpointer is not None:
            await _checkpointer.conn.close()
    except Exception:
        pass

app = FastAPI(
    title="Agentic Flow API",
    version="1.0.0",
    lifespan=lifespan,
)

# Optional API key security middleware (enabled via .env)
from middleware.auth import api_key_middleware
app.middleware("http")(api_key_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Register routers
app.include_router(agents.router,           prefix="/api/agents",    tags=["Agents"])
app.include_router(workflows.router,        prefix="/api/workflows", tags=["Workflows"])
app.include_router(runs.router,             prefix="/api/runs",      tags=["Runs"])
app.include_router(copilot.router,          prefix="/api",           tags=["Copilot"])
app.include_router(gateway_router.router,   prefix="/api/gateway",   tags=["Gateway"])
app.include_router(webhooks.router,         prefix="/api/webhooks",  tags=["Webhooks"])
app.include_router(exporter.router,         prefix="/api/workflows", tags=["Exporter"])
app.include_router(capabilities.router,     prefix="/api/capabilities", tags=["Capabilities"])

@app.get("/api/health")
async def health():
    return {"status": "ok", "telegram_active": gateway_state.telegram_gateway is not None}

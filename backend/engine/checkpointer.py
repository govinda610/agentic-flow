"""
App-lifetime AsyncSqliteSaver singleton.

Why this exists:
- SqliteSaver.from_conn_string() is a *synchronous context manager* — passing it
  directly to graph.compile() gives compile a CM object, not a saver, which fails.
- AsyncSqliteSaver is required because the engine uses astream_events (async).
- Opening a new connection on every compile() call (start/resume/sub-workflow)
  is wasteful and can conflict. A single shared connection is correct.

Usage:
    from engine.checkpointer import get_checkpointer
    checkpointer = await get_checkpointer()
    compiled, _ = parser.compile(checkpointer=checkpointer)

Shutdown:
    In main.py lifespan shutdown, call:
        from engine.checkpointer import _checkpointer
        if _checkpointer: await _checkpointer.conn.close()
"""
import aiosqlite
from pathlib import Path
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

_checkpointer: AsyncSqliteSaver | None = None


async def get_checkpointer() -> AsyncSqliteSaver:
    """Return (or lazily create) the shared AsyncSqliteSaver instance."""
    global _checkpointer
    if _checkpointer is None:
        from config import settings
        url = settings.database_url
        if not url.startswith("sqlite"):
            raise RuntimeError(f"Checkpointer requires a sqlite database_url, got: {url}")
        db_path = Path(url.replace("sqlite:///", ""))
        checkpoint_path = str(db_path.with_name(db_path.stem + "_checkpoints.db"))
        conn = await aiosqlite.connect(checkpoint_path, check_same_thread=False)
        _checkpointer = AsyncSqliteSaver(conn)
    return _checkpointer

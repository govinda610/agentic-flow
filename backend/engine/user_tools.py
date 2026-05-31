"""Loaders that turn stored Capability rows into live agent capabilities.

Three kinds, each materialized on demand from the capabilities table:
  - tool  -> load_user_tool():     exec stored Python into a live @tool
  - mcp   -> load_mcp_server_map(): resolve names into a MultiServerMCPClient server map
  - skill -> materialize_skills():  write stored SKILL.md files into an agent workspace

SECURITY: load_user_tool executes user-supplied Python on the host. That is arbitrary
code execution — acceptable for this local, single-user app (same posture as the
existing custom-skills loader in create_deep_agent.py). Do not expose this to untrusted
users without a sandbox.

The tool and mcp loaders are wired into the resolver at startup (see main.py) via
parser.USER_TOOL_LOADER and parser.MCP_SERVER_RESOLVER.
"""
import json
import logging
from pathlib import Path

from sqlmodel import Session, select
from langchain.tools import tool  # noqa: F401 — provided into the exec namespace
from langchain_core.tools import BaseTool

from database import engine as db_engine
from models.capability import Capability

logger = logging.getLogger(__name__)


def load_user_tool(name: str, ctx=None):
    """Look up a stored tool capability by name, exec its code, and return the tool.

    The stored code is expected to define an `@tool`-decorated function (the `tool`
    decorator is injected into the namespace). Returns the resulting BaseTool, or None
    if no such capability exists or the code defines no tool.
    """
    with Session(db_engine) as session:
        cap = session.exec(
            select(Capability).where(Capability.kind == "tool", Capability.name == name)
        ).first()
    if not cap:
        return None

    code = json.loads(cap.config_json).get("code", "")
    if not code.strip():
        return None

    namespace = {"tool": tool}
    try:
        exec(code, namespace)
    except Exception as exc:
        logger.error(f"User tool '{name}' failed to load: {exc}")
        return None

    found = [v for v in namespace.values() if isinstance(v, BaseTool)]
    if not found:
        logger.warning(f"User tool '{name}' defined no @tool object.")
        return None

    # Prefer a tool whose own name matches the capability name; else take the first.
    for t in found:
        if t.name == name:
            return t
    return found[0]


def load_mcp_server_map(names) -> dict:
    """Resolve a list of stored MCP capability names into a MultiServerMCPClient map.

    Each mcp capability stores {"servers": {<name>: <connection config>}}; this merges
    the referenced ones into a single dict for load_mcp_tools(). Returns {} for none.
    """
    if not names:
        return {}
    combined = {}
    with Session(db_engine) as session:
        for name in names:
            cap = session.exec(
                select(Capability).where(Capability.kind == "mcp", Capability.name == name)
            ).first()
            if not cap:
                logger.warning(f"MCP capability '{name}' not found — skipped.")
                continue
            combined.update(json.loads(cap.config_json).get("servers", {}))
    return combined


def materialize_skills(skill_names, workspace: Path) -> list:
    """Write referenced skill capabilities into <workspace>/skills/<name>/SKILL.md.

    Returns the backend source paths to pass to create_deep_agent(skills=...). The
    workspace is mounted at /workspace/ inside the agent, so sources are returned in
    that namespace. Each skill stores {"content": "<SKILL.md>"}; if the content has no
    YAML frontmatter we synthesise a minimal one from the capability name/description.
    """
    if not skill_names:
        return []
    skills_root = workspace / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    with Session(db_engine) as session:
        for name in skill_names:
            cap = session.exec(
                select(Capability).where(Capability.kind == "skill", Capability.name == name)
            ).first()
            if not cap:
                logger.warning(f"Skill capability '{name}' not found — skipped.")
                continue
            content = json.loads(cap.config_json).get("content", "")
            if not content.lstrip().startswith("---"):
                content = f"---\nname: {name}\ndescription: {cap.description or name}\n---\n\n{content}"
            skill_dir = skills_root / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content)
    return ["/workspace/skills/"]


def build_skill_middleware(workspace: Path, skill_names) -> list:
    """Middleware that gives a plain ReAct (create_agent) agent library-skill support.

    create_deep_agent has native skills=; create_agent does not, so for Tier 2 we attach
    deepagents' FilesystemMiddleware (provides read_file for progressive disclosure) and
    SkillsMiddleware over a workspace-backed filesystem. Returns [] when no skills.
    """
    sources = materialize_skills(skill_names, workspace)
    if not sources:
        return []
    from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend
    from deepagents.middleware import FilesystemMiddleware, SkillsMiddleware
    backend = CompositeBackend(
        default=StateBackend(),
        routes={"/workspace/": FilesystemBackend(root_dir=str(workspace.resolve()), virtual_mode=True)},
    )
    return [
        FilesystemMiddleware(backend=backend),
        SkillsMiddleware(backend=backend, sources=sources),
    ]

from pathlib import Path
from langchain.tools import tool
from providers.registry import get_llm
from engine.state import AgentFlowState
from engine.node_input import build_input_context, text_of
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend
import json
import re
import importlib.util
import sys
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

WORKSPACES_DIR = Path(__file__).parent.parent.parent / "workspaces"


def ensure_workspace(agent_id: str, system_prompt: str) -> Path:
    """Create workspace directory and write SOUL.md, MEMORY.md, AGENTS.md, skills/ dir."""
    workspace = WORKSPACES_DIR / str(agent_id)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "skills").mkdir(exist_ok=True)

    soul_path = workspace / "SOUL.md"
    if not soul_path.exists():
        soul_path.write_text(f"# SOUL\n\n{system_prompt}\n")

    memory_path = workspace / "MEMORY.md"
    if not memory_path.exists():
        memory_path.write_text("# MEMORY\n\n_No memories yet._\n")

    agents_path = workspace / "AGENTS.md"
    if not agents_path.exists():
        agents_path.write_text(
            f"# WORKSPACE RULES\n\n"
            f"- You have read/write access to: {workspace}\n"
            f"- Do not access files outside this directory.\n"
        )

    return workspace


def make_file_reader_tool(workspace: Path):
    @tool
    def file_reader(filename: str) -> str:
        """Read a file from the agent workspace. Use relative paths only."""
        safe_path = (workspace / filename).resolve()
        if not str(safe_path).startswith(str(workspace.resolve())):
            return "Error: Path traversal not allowed."
        try:
            return safe_path.read_text()
        except FileNotFoundError:
            return f"Error: File '{filename}' not found."
    return file_reader


def make_file_writer_tool(workspace: Path):
    @tool
    def file_writer(filename: str, content: str) -> str:
        """Write content to a file in the agent workspace. Use relative paths only."""
        safe_path = (workspace / filename).resolve()
        if not str(safe_path).startswith(str(workspace.resolve())):
            return "Error: Path traversal not allowed."
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content)
        return f"Successfully wrote {len(content)} characters to {filename}."
    return file_writer


def make_write_todos_tool(workspace: Path):
    @tool
    def write_todos(todos: str) -> str:
        """Write your current task plan to TODO.md before starting work."""
        (workspace / "TODO.md").write_text(f"# TODOS\n\n{todos}")
        return "TODO list saved."
    return write_todos


def make_write_memory_tool(workspace: Path):
    @tool
    def write_memory(key: str, fact: str) -> str:
        """Store a key fact or user preference in your MEMORY.md file for future reference."""
        memory_file = workspace / "MEMORY.md"
        current_mem = memory_file.read_text() if memory_file.exists() else "# MEMORY\n\n"
        new_mem = current_mem + f"\n- {key}: {fact} (Logged on {datetime.now(timezone.utc).isoformat()})"
        memory_file.write_text(new_mem)
        return f"Fact saved: '{key}: {fact}'"
    return write_memory


def load_custom_skills(agent_id: str) -> list:
    """Dynamically load custom Python skills from the agent's skills directory."""
    skills = []
    skills_dir = WORKSPACES_DIR / str(agent_id) / "skills"
    if not skills_dir.exists():
        return skills

    for file_path in skills_dir.glob("*.py"):
        try:
            module_name = f"custom_skill_{agent_id}_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if hasattr(attr, "args_schema") and hasattr(attr, "name"):
                    skills.append(attr)
        except Exception as exc:
            logger.error(f"Failed to load custom skill from {file_path.name}: {exc}")
    return skills


def _coerce_structured_output(text: str, structured_output_config: dict | None) -> dict:
    """
    Post-process deep_agent text output into structured fields when requested.

    deepagents.create_deep_agent does not accept response_format, so structured
    output is obtained by parsing the JSON object the system prompt instructed
    the model to produce.

    Returns a dict with the structured fields merged alongside the raw output.
    """
    if not structured_output_config or not structured_output_config.get("fields"):
        return {"output": text}

    result = {"output": text}
    # Try to extract a JSON object from the response text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            result.update(parsed)
        except json.JSONDecodeError:
            pass
    return result


async def run_deep_agent_node(
    state: AgentFlowState,
    node_id: str,
    node_config: dict,
    extra_tools: list,
    run_id: str,
) -> dict:
    """Tier 3: Deep Agent with native filesystem access, memory files, and custom skills."""
    agent_id = node_config.get("agent_id", node_id)
    workspace = ensure_workspace(agent_id, node_config.get("system_prompt", ""))

    # Instruct the agent on its virtual filesystem mounting location
    enhanced_system_prompt = (
        f"Use your built-in planning and filesystem capabilities for multi-step work.\n"
        f"Your workspace is mounted at `/workspace/`. Always read, write, and edit files "
        f"within `/workspace/` (e.g. `/workspace/TODO.md` or `/workspace/MEMORY.md`).\n"
        f"Record durable facts and intermediate findings in your memory files so you can refer back to them later while working on this task."
    )

    custom_skills = load_custom_skills(agent_id)

    # Materialize any referenced skill-library capabilities into the workspace so the
    # native SkillsMiddleware (via create_deep_agent(skills=...)) can load them.
    from engine.user_tools import materialize_skills
    skill_sources = materialize_skills(node_config.get("skills", []), workspace)

    # Filter out redundant filesystem/planning tools from extra_tools list
    filtered_extra_tools = [
        t for t in extra_tools
        if t.name not in ("file_reader", "file_writer", "write_todos", "write_memory")
    ]
    tools = [*custom_skills, *filtered_extra_tools]

    llm = get_llm(
        model=node_config.get("model"),
        temperature=node_config.get("temperature", 0.0),
        max_tokens=node_config.get("max_tokens", 4096),
    )
    input_str = build_input_context(state)

    # Route /workspace/ to physical workspace directory on disk, keep internal files in state
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/workspace/": FilesystemBackend(root_dir=str(workspace.resolve()), virtual_mode=True),
        },
    )

    # Instantiate deep agent with native memory loading and custom backend
    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=enhanced_system_prompt,
        memory=["/workspace/SOUL.md", "/workspace/AGENTS.md", "/workspace/MEMORY.md"],
        backend=backend,
        skills=skill_sources or None,
    )
    result = await agent.ainvoke({"messages": [{"role": "user", "content": input_str}]})
    output_text = text_of(result["messages"][-1])

    # Attempt structured output coercion if configured
    return _coerce_structured_output(output_text, node_config.get("structured_output"))

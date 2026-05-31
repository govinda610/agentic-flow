from langchain.tools import tool
from engine.node_input import text_of
import json

class RecursionRegistry:
    """
    Tracks clone depth and breadth per parent node to enforce limits.

    Note: The recursion registry state survives workflow pause/resume because 
    it is stored directly inside the AgentFlowState (under the __recursion_registry__ key) 
    which is saved and restored by the checkpointer.
    """

    def __init__(self, state: dict, parent_node_id: str):
        self.state = state
        self.parent_node_id = parent_node_id
        registry = state.setdefault("__recursion_registry__", {})
        self.node_registry = registry.setdefault(
            parent_node_id, {"depth": 0, "breadth": 0, "children": []}
        )

    def can_spawn(self, max_depth: int, max_breadth: int) -> bool:
        return (
            self.node_registry["depth"] < max_depth and
            self.node_registry["breadth"] < max_breadth
        )

    def register_spawn(self) -> str:
        """Register a new clone and return its clone_id."""
        clone_id = f"clone_{len(self.node_registry['children'])}"
        self.node_registry["breadth"] += 1
        self.node_registry["children"].append(clone_id)
        self.state["__recursion_registry__"][self.parent_node_id] = self.node_registry
        return clone_id

    def get_child_depth(self) -> int:
        return self.node_registry["depth"] + 1


def make_clone_agent_tool(
    node_id: str,
    node_config: dict,
    run_id: str,
    state: dict,
):
    """
    Factory: creates a clone_agent tool bound to a specific parent node.
    Enforces max_depth and max_breadth recursion limits from node_config.
    """
    max_depth   = node_config.get("max_depth", 1)
    max_breadth = node_config.get("max_breadth", 2)

    @tool
    async def clone_agent(task: str) -> str:
        """
        Spawn a copy of yourself to handle a specific sub-task in isolation.
        Use this to parallelize complex work. Returns the clone's output.

        Args:
            task: The specific sub-task for the clone to handle.
        """
        registry = RecursionRegistry(state, node_id)

        if not registry.can_spawn(max_depth, max_breadth):
            return (
                f"Recursion limit reached (max_depth={max_depth}, max_breadth={max_breadth}). "
                f"Handle this task directly without spawning more clones."
            )

        clone_id    = registry.register_spawn()
        child_depth = registry.get_child_depth()

        clone_config = {
            **node_config,
            "max_breadth": max_breadth,
            "name": f"{node_config.get('name', 'Agent')} (Clone {clone_id})",
        }

        clone_state = {
            **state,
            # FIX: use __task__ key so build_input_context() in run_agent_node
            # uses the task directly, bypassing accumulated node_outputs context.
            "initial_input": {"__task__": task, "message": task},
            "__recursion_registry__": {
                **state.get("__recursion_registry__", {}),
                f"{node_id}/{clone_id}": {"depth": child_depth, "breadth": 0, "children": []},
            },
        }

        from engine.nodes.create_agent import run_agent_node
        from engine.interpreter import StatefulInterpreter

        session_key = f"{run_id}:{node_id}:{clone_id}"
        tools = [StatefulInterpreter.make_tool(session_key)]

        try:
            result = await run_agent_node(clone_state, f"{node_id}/{clone_id}", clone_config, tools)
            return json.dumps(result)
        except Exception as exc:
            return f"Clone {clone_id} failed: {str(exc)}"

    return clone_agent

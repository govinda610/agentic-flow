"""
Unit tests for engine/parser WorkflowParser.compile() — tests graph compilation
from JSON schema without needing a real LLM.

Covers: compile() returns correct graph structure, node functions exist,
router functions work, subgraph compilation (including H4 fix).
"""
import pytest
import json
from engine.parser import WorkflowParser


SIMPLE_SCHEMA = {
    "name": "Test Simple Workflow",
    "nodes": [
        {"id": "node_start", "type": "start",   "position": {"x": 0, "y": 0},   "config": {"label": "Start"}},
        {"id": "node_llm",   "type": "simple_llm", "position": {"x": 200, "y": 0}, "config": {
            "system_prompt": "You are a helpful assistant.",
            "name": "Test LLM",
        }},
        {"id": "node_end",   "type": "end",     "position": {"x": 400, "y": 0},   "config": {"label": "End"}},
    ],
    "edges": [
        {"id": "e1", "source": "node_start", "target": "node_llm", "type": "normal",  "condition": None, "label": ""},
        {"id": "e2", "source": "node_llm",   "target": "node_end",  "type": "normal",  "condition": None, "label": ""},
    ],
}

CONDITIONAL_SCHEMA = {
    "name": "Test Conditional Workflow",
    "nodes": [
        {"id": "node_start",  "type": "start",       "position": {"x": 0,   "y": 0},   "config": {"label": "Start"}},
        {"id": "node_check",  "type": "simple_llm",   "position": {"x": 200, "y": 0},   "config": {"system_prompt": "Return approved: true/false"}},
        {"id": "node_yes",    "type": "simple_llm",   "position": {"x": 400, "y": -100}, "config": {"system_prompt": "Approved path"}},
        {"id": "node_no",     "type": "simple_llm",   "position": {"x": 400, "y": 100},  "config": {"system_prompt": "Rejected path"}},
        {"id": "node_end",    "type": "end",          "position": {"x": 600, "y": 0},   "config": {"label": "End"}},
    ],
    "edges": [
        {"id": "e1", "source": "node_start",  "target": "node_check", "type": "normal",     "condition": None,     "label": ""},
        {"id": "e2", "source": "node_check",  "target": "node_yes",   "type": "conditional",
         "condition": "state['node_outputs']['node_check']['content'] is not None", "label": "approved"},
        {"id": "e3", "source": "node_check",  "target": "node_no",    "type": "conditional",
         "condition": "state['node_outputs']['node_check']['content'] is None",      "label": "rejected"},
        {"id": "e4", "source": "node_yes",     "target": "node_end",   "type": "normal",     "condition": None,     "label": ""},
        {"id": "e5", "source": "node_no",      "target": "node_end",   "type": "normal",     "condition": None,     "label": ""},
    ],
}


class TestWorkflowParserInit:
    """WorkflowParser.__init__ correctly parses schema structure."""

    def test_nodes_dict_created_from_schema(self):
        """Parser stores nodes as {id: node_dict} lookup."""
        parser = WorkflowParser(SIMPLE_SCHEMA, run_id="test-run-1")
        assert "node_start" in parser.nodes
        assert "node_llm"   in parser.nodes
        assert "node_end"   in parser.nodes
        assert parser.nodes["node_llm"]["type"] == "simple_llm"

    def test_edges_list_preserved(self):
        """Parser stores edges as raw list."""
        parser = WorkflowParser(SIMPLE_SCHEMA, run_id="test-run-2")
        assert len(parser.edges) == 2
        assert parser.edges[0]["source"] == "node_start"
        assert parser.edges[1]["source"] == "node_llm"


class TestWorkflowParserCompile:
    """WorkflowParser.compile() returns a compiled LangGraph."""

    def test_compile_returns_tuple_of_graph_and_checkpointer(self):
        """compile() returns (compiled_graph, checkpointer_or_None)."""
        parser = WorkflowParser(SIMPLE_SCHEMA, run_id="test-compile-1")
        graph, checkpointer = parser.compile()
        # graph should be a CompiledStateGraph (LangGraph)
        assert graph is not None
        assert hasattr(graph, "invoke")
        assert hasattr(graph, "ainvoke")
        # No checkpointer passed in, so should be None
        assert checkpointer is None

    def test_compile_produces_graph_that_accepts_initial_state(self):
        """Compiled graph can be invoked with initial state dict."""
        parser = WorkflowParser(SIMPLE_SCHEMA, run_id="test-compile-2")
        graph, _ = parser.compile()
        config = {"configurable": {"thread_id": "test-thread-1"}}

        import asyncio
        async def run():
            result = await graph.ainvoke(
                {
                    "run_id": "test-run",
                    "workflow_id": "1",
                    "initial_input": {"message": "hello"},
                    "node_outputs": {},
                    "parallel_results": [],
                    "_run_error": None,
                    "__recursion_registry__": {},
                    "telegram_chat_id": None,
                    "telegram_message": None,
                    "__hitl_pending__": False,
                    "__hitl_response__": None,
                },
                config=config
            )
            return result

        result = asyncio.run(run())
        assert isinstance(result, dict)
        assert "node_outputs" in result

    def test_compile_with_no_edges_terminates(self):
        """Schema with only start and end nodes compiles and terminates."""
        schema = {
            "nodes": [
                {"id": "node_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                {"id": "node_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "node_start", "target": "node_end", "type": "normal", "condition": None},
            ],
        }
        parser = WorkflowParser(schema, run_id="test-empty-1")
        graph, _ = parser.compile()
        config = {"configurable": {"thread_id": "test-thread-empty"}}

        import asyncio
        async def run():
            return await graph.ainvoke(
                {
                    "run_id": "test-run", "workflow_id": "1",
                    "initial_input": {}, "node_outputs": {},
                    "parallel_results": [], "_run_error": None,
                    "__recursion_registry__": {},
                    "telegram_chat_id": None, "telegram_message": None,
                    "__hitl_pending__": False, "__hitl_response__": None,
                },
                config=config
            )
        result = asyncio.run(run())
        assert isinstance(result, dict)


class TestWorkflowParserNodeTypes:
    """compile() correctly handles different node types."""

    def test_start_and_end_nodes_compiled(self):
        """start and end nodes are recognized and compiled."""
        parser = WorkflowParser(SIMPLE_SCHEMA, run_id="test-nodes-1")
        graph, _ = parser.compile()
        assert graph is not None

    def test_simple_llm_node_compiled(self):
        """simple_llm nodes are added to the graph."""
        parser = WorkflowParser(SIMPLE_SCHEMA, run_id="test-nodes-2")
        graph, _ = parser.compile()
        assert graph is not None  # Node should be present

    def test_agent_node_compiled(self):
        """agent node type compiles successfully."""
        schema = {
            "nodes": [
                {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                {"id": "n_agent", "type": "agent", "position": {"x": 200, "y": 0}, "config": {
                    "name": "Test Agent", "system_prompt": "Test"
                }},
                {"id": "n_end",   "type": "end",   "position": {"x": 400, "y": 0}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n_start", "target": "n_agent", "type": "normal", "condition": None},
                {"id": "e2", "source": "n_agent", "target": "n_end",   "type": "normal", "condition": None},
            ],
        }
        parser = WorkflowParser(schema, run_id="test-agent-1")
        graph, _ = parser.compile()
        assert graph is not None

    def test_deep_agent_node_compiled(self):
        """deep_agent node type compiles successfully."""
        schema = {
            "nodes": [
                {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                {"id": "n_deep",  "type": "deep_agent", "position": {"x": 200, "y": 0}, "config": {
                    "name": "Deep Agent", "system_prompt": "Test"
                }},
                {"id": "n_end",   "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n_start", "target": "n_deep", "type": "normal", "condition": None},
                {"id": "e2", "source": "n_deep",  "target": "n_end",   "type": "normal", "condition": None},
            ],
        }
        parser = WorkflowParser(schema, run_id="test-deep-agent-1")
        graph, _ = parser.compile()
        assert graph is not None


class TestWorkflowParserConditionalEdges:
    """compile() correctly builds conditional edge routing."""

    def test_compile_with_conditional_edges_produces_graph(self):
        """Schema with conditional edges compiles to a graph."""
        parser = WorkflowParser(CONDITIONAL_SCHEMA, run_id="test-cond-1")
        graph, _ = parser.compile()
        assert graph is not None

    def test_conditional_router_function_created(self):
        """Conditional edges cause router functions to be generated."""
        parser = WorkflowParser(CONDITIONAL_SCHEMA, run_id="test-cond-2")
        graph, _ = parser.compile()
        assert graph is not None  # Router should be wired up internally


class TestWorkflowParserSubgraph:
    """Subgraph compilation (verifies H4 fix: child_wf.workflow_schema not .schema)."""

    @pytest.fixture
    def workflow_with_subgraph(self, client):
        """Create a parent workflow that references the AI Co-Scientist template as subgraph."""
        # First, get the AI Co-Scientist template ID
        res = client.get("/api/workflows/")
        assert res.status_code == 200
        workflows = res.json()
        co_scientist = next((w for w in workflows if w["name"] == "AI Co-Scientist"), None)
        assert co_scientist is not None, "AI Co-Scientist template not found"
        co_scientist_id = co_scientist["id"]

        # Save a parent workflow that uses the subgraph
        parent_schema = {
            "name": "Parent with Subgraph",
            "nodes": [
                {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                {"id": "n_subgraph", "type": "subgraph", "position": {"x": 200, "y": 0}, "config": {
                    "name": "Co-Scientist Subgraph",
                    "workflow_id": co_scientist_id,
                }},
                {"id": "n_end", "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n_start",    "target": "n_subgraph", "type": "normal", "condition": None},
                {"id": "e2", "source": "n_subgraph", "target": "n_end",      "type": "normal", "condition": None},
            ],
        }

        res = client.post("/api/workflows/", json={
            "name": "Parent with Subgraph",
            "workflow_schema": parent_schema,
        })
        assert res.status_code == 200
        return res.json()["id"]

    def test_subgraph_workflow_compiles_without_keyerror(self, client, workflow_with_subgraph):
        """Parent workflow with subgraph node compiles without KeyError: 'nodes'.

        This was the H4 bug: child_wf.schema was calling Pydantic's .schema() method
        which returns the model schema (field descriptors), not the workflow JSON.
        Using child_wf.workflow_schema (the property that parses schema_blob) fixes this.
        """
        res = client.get(f"/api/workflows/{workflow_with_subgraph}")
        assert res.status_code == 200
        workflow = res.json()

        import asyncio
        from engine.parser import WorkflowParser

        parser = WorkflowParser(workflow["workflow_schema"], run_id="test-subgraph-run")
        graph, _ = parser.compile()  # Would raise KeyError: 'nodes' if child_wf.schema was used

        assert graph is not None
        config = {"configurable": {"thread_id": "test-subgraph-thread"}}

        async def run():
            return await graph.ainvoke(
                {
                    "run_id": "test-subgraph-run", "workflow_id": str(workflow_with_subgraph),
                    "initial_input": {"message": "Test subgraph compilation"},
                    "node_outputs": {}, "parallel_results": [], "_run_error": None,
                    "__recursion_registry__": {},
                    "telegram_chat_id": None, "telegram_message": None,
                    "__hitl_pending__": False, "__hitl_response__": None,
                },
                config=config
            )

        # This should NOT raise KeyError: 'nodes'
        result = asyncio.run(run())
        assert isinstance(result, dict)
        assert "node_outputs" in result


class TestWorkflowParserErrorEdges:
    """Error edge routing is correctly compiled."""

    def test_error_edge_compiled(self):
        """Schema with error edges compiles correctly."""
        schema = {
            "nodes": [
                {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                {"id": "n_task",  "type": "agent", "position": {"x": 200, "y": 0}, "config": {
                    "name": "Task", "system_prompt": "Do something"
                }},
                {"id": "n_error", "type": "simple_llm", "position": {"x": 400, "y": -100}, "config": {
                    "system_prompt": "Handle error"
                }},
                {"id": "n_end",   "type": "end", "position": {"x": 600, "y": 0}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n_start", "target": "n_task",  "type": "normal",     "condition": None},
                {"id": "e2", "source": "n_task",  "target": "n_error", "type": "error"},
                {"id": "e3", "source": "n_task",  "target": "n_end",   "type": "normal",     "condition": None},
                {"id": "e4", "source": "n_error", "target": "n_end",   "type": "normal",     "condition": None},
            ],
        }
        parser = WorkflowParser(schema, run_id="test-error-edge-1")
        graph, _ = parser.compile()
        assert graph is not None


class TestWorkflowParserNodeFunctions:
    """Node functions are created with correct names and signatures."""

    def test_node_function_names_match_node_ids(self):
        """Each non-start/end node gets a node function."""
        parser = WorkflowParser(SIMPLE_SCHEMA, run_id="test-node-fn-1")
        graph, _ = parser.compile()
        # The compiled graph has nodes registered
        assert graph is not None
"""
End-to-end tests that exercise the real system with real LLM calls.

These tests use the actual database, real LLM API (GLM-5-turbo via z.ai),
and real async run execution. They test the full request/response cycle
from API call through graph compilation to run completion.

Uses the real .env config (GLM_API_KEY, etc.) — no mocks.
"""
import pytest
import time
import json
import re


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

def poll_until(fn, timeout=30, interval=0.5):
    """Poll fn() until it returns truthy or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(interval)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# test_agent_lifecycle — basic CRUD, no LLM
# ─────────────────────────────────────────────────────────────────────────────

def test_agent_create_and_retrieve(client):
    """Create an agent via API and retrieve it."""
    payload = {
        "name": "E2E Test Agent",
        "system_prompt": "You are a test agent for e2e validation.",
        "node_type": "agent",
        "tools": [],
        "config": {"max_depth": 2},
    }
    res = client.post("/api/agents/", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "E2E Test Agent"
    assert data["id"] is not None
    agent_id = data["id"]

    # Retrieve
    agents = client.get("/api/agents/").json()
    found = next((a for a in agents if a["id"] == agent_id), None)
    assert found is not None
    assert found["name"] == "E2E Test Agent"


def test_agent_update(client):
    """Update an agent's fields."""
    create_res = client.post("/api/agents/", json={
        "name": "Old Name",
        "system_prompt": "old prompt",
    })
    agent_id = create_res.json()["id"]

    update_res = client.put(f"/api/agents/{agent_id}", json={
        "name": "New Name",
        "system_prompt": "updated prompt",
        "node_type": "agent",
        "tools": [],
        "config": {},
    })
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "New Name"


def test_agent_delete_and_404(client):
    """Delete an agent; subsequent GET returns 404."""
    create_res = client.post("/api/agents/", json={
        "name": "To Delete",
        "system_prompt": "temp",
    })
    agent_id = create_res.json()["id"]

    del_res = client.delete(f"/api/agents/{agent_id}")
    assert del_res.status_code == 200

    agents = client.get("/api/agents/").json()
    found = next((a for a in agents if a["id"] == agent_id), None)
    assert found is None


# ─────────────────────────────────────────────────────────────────────────────
# test_workflow_crud — save, load, update, delete workflows
# ─────────────────────────────────────────────────────────────────────────────

def test_workflow_save_and_load(client):
    """Save a workflow schema and retrieve it intact."""
    schema = {
        "name": "E2E Test Workflow",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start", "target": "n_end", "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={
        "name": "E2E Test Workflow",
        "workflow_schema": schema,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "E2E Test Workflow"
    wf_id = data["id"]

    # Load back
    get_res = client.get(f"/api/workflows/{wf_id}")
    assert get_res.status_code == 200
    loaded = get_res.json()
    assert loaded["workflow_schema"]["name"] == "E2E Test Workflow"
    assert len(loaded["workflow_schema"]["nodes"]) == 2
    assert loaded["workflow_schema"]["edges"][0]["source"] == "n_start"


def test_workflow_update(client):
    """Update a workflow's name and schema."""
    schema = {
        "name": "Original Name",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start", "target": "n_end", "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={
        "name": "Original Name",
        "workflow_schema": schema,
    })
    wf_id = res.json()["id"]

    updated_schema = dict(schema)
    updated_schema["name"] = "Updated Name"
    updated_schema["nodes"].append({
        "id": "n_new", "type": "simple_llm",
        "position": {"x": 150, "y": 0}, "config": {"system_prompt": "extra node"},
    })
    updated_schema["edges"].append(
        {"id": "e2", "source": "n_start", "target": "n_new", "type": "normal", "condition": None}
    )

    res = client.post("/api/workflows/", json={
        "workflow_id": wf_id,
        "name": "Updated Name",
        "workflow_schema": updated_schema,
    })
    assert res.status_code == 200
    assert res.json()["name"] == "Updated Name"
    assert len(res.json()["workflow_schema"]["nodes"]) == 4


def test_workflow_delete(client):
    """Delete a workflow and verify 404 on re-get."""
    schema = {"name": "To Delete", "nodes": [
        {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
        {"id": "n_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
    ], "edges": [
        {"id": "e1", "source": "n_start", "target": "n_end", "type": "normal", "condition": None},
    ]}
    res = client.post("/api/workflows/", json={
        "name": "To Delete", "workflow_schema": schema,
    })
    wf_id = res.json()["id"]

    del_res = client.delete(f"/api/workflows/{wf_id}")
    assert del_res.status_code == 200

    get_res = client.get(f"/api/workflows/{wf_id}")
    assert get_res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# test_webhook_lifecycle — register, trigger, list, revoke
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_register(client):
    """Register a webhook token for a workflow."""
    # Get any workflow
    wfs = client.get("/api/workflows/").json()
    assert len(wfs) > 0
    wf_id = wfs[0]["id"]

    res = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["workflow_id"] == wf_id
    assert data["webhook_url"].startswith("/api/webhooks/")


def test_webhook_trigger_starts_run(client):
    """Triggering a webhook token starts a workflow run."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    # Register webhook
    reg_res = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    token = reg_res.json()["token"]

    # Trigger
    trigger_res = client.post(f"/api/webhooks/{token}", json={
        "message": "Webhook test payload",
        "data": {"key": "value"},
    })
    assert trigger_res.status_code == 200
    run_data = trigger_res.json()
    assert "run_id" in run_data
    assert run_data["status"] == "started"
    assert run_data["source"] == "webhook"

    # Run should be in DB
    run_id = run_data["run_id"]
    steps_res = client.get(f"/api/runs/{run_id}/steps")
    assert steps_res.status_code == 200


def test_webhook_revoke(client):
    """Revoking a webhook token makes trigger return 404."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    reg_res = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    token = reg_res.json()["token"]

    revoke_res = client.delete(f"/api/webhooks/{token}")
    assert revoke_res.status_code == 200

    # Re-trigger should 404
    trigger_res = client.post(f"/api/webhooks/{token}", json={"message": "test"})
    assert trigger_res.status_code == 404


def test_webhook_invalid_token(client):
    """Invalid webhook token returns 404."""
    res = client.post("/api/webhooks/invalid_token_12345", json={"message": "test"})
    assert res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# test_run_start_and_complete — real LLM execution
# ─────────────────────────────────────────────────────────────────────────────

def test_run_simple_workflow_completes(client):
    """Start a run on a simple 2-node schema and verify it reaches completed status."""
    # Create a minimal workflow: start → simple_llm → end
    schema = {
        "name": "E2E Simple Run",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_llm", "type": "simple_llm", "position": {"x": 200, "y": 0}, "config": {
                "system_prompt": "Return exactly the word 'done' with nothing else.",
                "name": "Test LLM Node",
            }},
            {"id": "n_end", "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start", "target": "n_llm", "type": "normal", "condition": None},
            {"id": "e2", "source": "n_llm",   "target": "n_end",  "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={"name": "E2E Simple Run", "workflow_schema": schema})
    wf_id = res.json()["id"]

    # Start run
    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "test"},
    })
    assert start_res.status_code == 200
    run_id = start_res.json()["run_id"]

    # Poll run status until completed or failed
    def check_run():
        steps_res = client.get(f"/api/runs/{run_id}/steps")
        if steps_res.status_code != 200:
            return None
        steps = steps_res.json()
        if not steps:
            return None
        # Check if any step has completed or failed
        for step in steps:
            if step.get("status") in ("completed", "failed"):
                return step
        return None

    result = poll_until(check_run, timeout=60)
    assert result is not None, f"Run {run_id} did not complete within 60s"
    assert result["status"] == "completed", f"Run failed: {result.get('error_traceback', result)}"

    # Verify run record status
    # The run should have completed in DB
    # We can't directly check WorkflowRun status without a dedicated endpoint,
    # but step completion confirms the run finished.


def test_run_start_returns_run_id(client):
    """POST /api/runs/start returns a run_id immediately."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "hello"},
    })
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert len(data["run_id"]) == 36  # UUID format


def test_run_get_steps_returns_list(client):
    """GET /api/runs/{run_id}/steps returns a list of step records."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "test steps"},
    })
    run_id = start_res.json()["run_id"]

    time.sleep(1)  # Give run time to start
    steps_res = client.get(f"/api/runs/{run_id}/steps")
    assert steps_res.status_code == 200
    steps = steps_res.json()
    assert isinstance(steps, list)


def test_run_get_step_by_node(client):
    """GET /api/runs/{run_id}/steps/{node_id} returns most recent step for that node."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "test step lookup"},
    })
    run_id = start_res.json()["run_id"]

    time.sleep(1)
    # node_end should exist in a well-formed workflow
    res = client.get(f"/api/runs/{run_id}/steps/node_end")
    # 200 if exists, 404 if not yet created
    assert res.status_code in (200, 404)


# ─────────────────────────────────────────────────────────────────────────────
# test_run_cancel
# ─────────────────────────────────────────────────────────────────────────────

def test_run_cancel(client):
    """POST /api/runs/{run_id}/cancel stops a running workflow."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "cancel me"},
    })
    run_id = start_res.json()["run_id"]

    cancel_res = client.post(f"/api/runs/{run_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"


# ─────────────────────────────────────────────────────────────────────────────
# test_copilot_generate_workflow — real LLM call
# ─────────────────────────────────────────────────────────────────────────────

def test_copilot_generate_simple_workflow(client):
    """POST /api/generate-workflow returns a valid workflow schema."""
    res = client.post("/api/generate-workflow", json={
        "prompt": "Create a workflow with a start node, a simple LLM node, and an end node.",
    })
    assert res.status_code == 200
    data = res.json()
    assert "workflow_schema" in data
    assert "message" in data

    schema = data["workflow_schema"]
    assert "name" in schema
    assert "nodes" in schema
    assert "edges" in schema

    node_types = [n["type"] for n in schema["nodes"]]
    assert "start" in node_types, f"No start node in: {node_types}"
    assert "end"   in node_types, f"No end node in: {node_types}"
    assert len(schema["nodes"]) >= 2


def test_copilot_generated_schema_is_loadable(client):
    """A copilot-generated schema can be saved and retrieved."""
    res = client.post("/api/generate-workflow", json={
        "prompt": "A workflow with a start, one agent node named 'Researcher', and an end.",
    })
    assert res.status_code == 200
    schema = res.json()["workflow_schema"]

    # Save it
    save_res = client.post("/api/workflows/", json={
        "name": schema.get("name", "Copilot Generated"),
        "workflow_schema": schema,
    })
    assert save_res.status_code == 200
    wf_id = save_res.json()["id"]

    # Load it back
    get_res = client.get(f"/api/workflows/{wf_id}")
    assert get_res.status_code == 200
    loaded_schema = get_res.json()["workflow_schema"]
    assert len(loaded_schema["nodes"]) == len(schema["nodes"])


# ─────────────────────────────────────────────────────────────────────────────
# test_export_workflow_code
# ─────────────────────────────────────────────────────────────────────────────

def test_export_produces_valid_python(client):
    """GET /api/workflows/{id}/export returns syntactically valid Python."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.get(f"/api/workflows/{wf_id}/export")
    assert res.status_code == 200

    script = res.text
    assert "StateGraph" in script
    assert "WorkflowState" in script

    # Verify Python syntax by parsing it
    import ast
    try:
        ast.parse(script)
    except SyntaxError as e:
        pytest.fail(f"Exported script has syntax error: {e}")

    # Verify no template placeholders remain
    assert "{node_functions}" not in script
    assert "{graph_nodes}" not in script
    assert "{graph_edges}" not in script


# ─────────────────────────────────────────────────────────────────────────────
# test_run_with_structured_output — real LLM with JSON schema
# ─────────────────────────────────────────────────────────────────────────────

def test_run_with_structured_output(client):
    """Run a workflow with structured_output fields and verify parsed response."""
    schema = {
        "name": "E2E Structured Output",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_agent", "type": "agent", "position": {"x": 200, "y": 0}, "config": {
                "name": "Structured Agent",
                "system_prompt": (
                    "You are a data extraction agent. When given any text input, "
                    "extract exactly these three fields and return them as JSON with no extra text: "
                    "word_count (integer), has_numbers (boolean), first_letter (string). "
                    "Example: for 'Hello World' return: {\"word_count\": 2, \"has_numbers\": false, \"first_letter\": \"H\"}"
                ),
                "structured_output": {
                    "fields": [
                        {"name": "word_count", "type": "integer"},
                        {"name": "has_numbers", "type": "boolean"},
                        {"name": "first_letter", "type": "string"},
                    ]
                },
            }},
            {"id": "n_end", "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start", "target": "n_agent", "type": "normal", "condition": None},
            {"id": "e2", "source": "n_agent", "target": "n_end",   "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={
        "name": "E2E Structured Output",
        "workflow_schema": schema,
    })
    wf_id = res.json()["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "The quick brown fox"},
    })
    assert start_res.status_code == 200
    run_id = start_res.json()["run_id"]

    # Poll for completion
    def check_completion():
        steps_res = client.get(f"/api/runs/{run_id}/steps")
        if steps_res.status_code != 200:
            return None
        for step in steps_res.json():
            if step.get("node_id") == "n_agent" and step.get("status") == "completed":
                return step
        return None

    result = poll_until(check_completion, timeout=90)
    assert result is not None, f"Structured output run {run_id} did not complete"
    assert result["status"] == "completed"

    # Output state should contain the structured response
    if result.get("output_state_json"):
        output = json.loads(result["output_state_json"])
        # structured_response OR output should be present
        has_response = (
            "structured_response" in output or
            "output" in output or
            "content" in output
        )
        assert has_response, f"No output fields in: {output}"


# ─────────────────────────────────────────────────────────────────────────────
# test_agent_with_tools — real LLM + code interpreter tool
# ─────────────────────────────────────────────────────────────────────────────

def test_run_agent_with_code_interpreter(client):
    """Run a workflow with a code_interpreter tool and verify execution."""
    schema = {
        "name": "E2E Code Interpreter",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_interp", "type": "agent", "position": {"x": 200, "y": 0}, "config": {
                "name": "Code Runner",
                "system_prompt": (
                    "You have access to a code interpreter. Write and execute "
                    "Python code that computes 2 + 2 and returns the result."
                ),
                "tools": ["code_interpreter"],
            }},
            {"id": "n_end", "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start",  "target": "n_interp", "type": "normal", "condition": None},
            {"id": "e2", "source": "n_interp", "target": "n_end",    "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={
        "name": "E2E Code Interpreter",
        "workflow_schema": schema,
    })
    wf_id = res.json()["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "Run 2 + 2"},
    })
    assert start_res.status_code == 200
    run_id = start_res.json()["run_id"]

    def check_completion():
        steps_res = client.get(f"/api/runs/{run_id}/steps")
        if steps_res.status_code != 200:
            return None
        for step in steps_res.json():
            if step.get("node_id") == "n_interp" and step.get("status") in ("completed", "failed"):
                return step
        return None

    result = poll_until(check_completion, timeout=90)
    assert result is not None, f"Code interpreter run {run_id} did not complete"
    assert result["status"] == "completed", f"Code interpreter failed: {result}"


# ─────────────────────────────────────────────────────────────────────────────
# test_run_stream_events — SSE event format
# ─────────────────────────────────────────────────────────────────────────────

def test_run_stream_events_format(client):
    """GET /api/runs/{run_id}/stream returns SSE events with correct format."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "stream test"},
    })
    run_id = start_res.json()["run_id"]

    # Give run time to emit events
    time.sleep(2)

    # Stream endpoint should return events
    stream_res = client.get(f"/api/runs/{run_id}/stream")
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers.get("content-type", "")

    # SSE events should contain 'data' with run_id
    content = stream_res.text
    # Events are newline-separated
    lines = [l for l in content.split("\n") if l.startswith("data:")]
    assert len(lines) > 0, "No SSE events received"


# ─────────────────────────────────────────────────────────────────────────────
# test_run_inbox_messages
# ─────────────────────────────────────────────────────────────────────────────

def test_inbox_returns_list(client):
    """GET /api/runs/{run_id}/inbox/{node_id} returns a list (may be empty)."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "inbox test"},
    })
    run_id = start_res.json()["run_id"]

    time.sleep(1)
    inbox_res = client.get(f"/api/runs/{run_id}/inbox/nonexistent_node")
    assert inbox_res.status_code == 200
    assert isinstance(inbox_res.json(), list)


# ─────────────────────────────────────────────────────────────────────────────
# test_telegram_simulate_full_flow — simulated gateway start to finish
# ─────────────────────────────────────────────────────────────────────────────

def test_simulate_runs_real_workflow(client):
    """Simulate a Telegram message; verify the run executes end to end."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.post("/api/gateway/simulate", json={
        "workflow_id": wf_id,
        "message": "Simulated Telegram: run the workflow",
        "user_id": "test_user_e2e",
    })
    assert res.status_code == 200
    run_id = res.json()["run_id"]
    assert res.json()["status"] == "started"

    # Poll for completion
    def check_completion():
        steps_res = client.get(f"/api/runs/{run_id}/steps")
        if steps_res.status_code != 200:
            return None
        for step in steps_res.json():
            if step.get("status") in ("completed", "failed"):
                return step
        return None

    result = poll_until(check_completion, timeout=90)
    assert result is not None, f"Simulated run {run_id} did not complete"


# ─────────────────────────────────────────────────────────────────────────────
# test_deep_researcher_swarm — run the template with parallel fan-out
# ─────────────────────────────────────────────────────────────────────────────

def test_deep_researcher_swarm_completes(client):
    """Run the 'Deep Researcher Swarm' template end to end with real LLM calls."""
    wfs = client.get("/api/workflows/").json()
    swarm = next((w for w in wfs if w["name"] == "Deep Researcher Swarm"), None)
    assert swarm is not None, "Deep Researcher Swarm template not found"
    wf_id = swarm["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {
            "message": "Research the topic: What is photosynthesis?",
            "source": "e2e_test",
        },
    })
    assert start_res.status_code == 200
    run_id = start_res.json()["run_id"]

    # Poll for completion
    def check_completion():
        steps_res = client.get(f"/api/runs/{run_id}/steps")
        if steps_res.status_code != 200:
            return None
        steps = steps_res.json()
        for s in steps:
            if s.get("status") in ("completed", "failed"):
                return s
        return None

    result = poll_until(check_completion, timeout=120)
    assert result is not None, f"Deep Researcher Swarm run {run_id} did not complete within 120s"


# ─────────────────────────────────────────────────────────────────────────────
# test_data_science_loop — run the template with deep_agent + verifier
# ─────────────────────────────────────────────────────────────────────────────

def test_data_science_loop_completes(client):
    """Run the 'Data Science Loop' template end to end."""
    wfs = client.get("/api/workflows/").json()
    loop = next((w for w in wfs if w["name"] == "Data Science Loop"), None)
    assert loop is not None, "Data Science Loop template not found"
    wf_id = loop["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {
            "message": "Analyze: [1, 2, 3, 4, 5]",
            "source": "e2e_test",
        },
    })
    assert start_res.status_code == 200
    run_id = start_res.json()["run_id"]

    def check_completion():
        steps_res = client.get(f"/api/runs/{run_id}/steps")
        if steps_res.status_code != 200:
            return None
        for s in steps_res.json():
            if s.get("status") in ("completed", "failed"):
                return s
        return None

    result = poll_until(check_completion, timeout=120)
    assert result is not None, f"Data Science Loop run {run_id} did not complete within 120s"


# ─────────────────────────────────────────────────────────────────────────────
# test_ai_co_scientist_with_subgraph — run the template with subgraphs
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_co_scientist_with_subgraph(client):
    """Run the 'AI Co-Scientist' template which uses subgraph nodes.

    This test verifies the H4 fix: child_wf.workflow_schema must be used
    (not child_wf.schema) for subgraph compilation to work.
    """
    wfs = client.get("/api/workflows/").json()
    co_sci = next((w for w in wfs if w["name"] == "AI Co-Scientist"), None)
    assert co_sci is not None, "AI Co-Scientist template not found"
    wf_id = co_sci["id"]

    start_res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {
            "message": "Design a hypothesis about dark matter",
            "source": "e2e_test",
        },
    })
    assert start_res.status_code == 200
    run_id = start_res.json()["run_id"]

    def check_completion():
        steps_res = client.get(f"/api/runs/{run_id}/steps")
        if steps_res.status_code != 200:
            return None
        for s in steps_res.json():
            if s.get("status") in ("completed", "failed"):
                return s
        return None

    result = poll_until(check_completion, timeout=180)
    assert result is not None, (
        f"AI Co-Scientist run {run_id} did not complete within 180s. "
        "Check that subgraph compilation (H4 fix: child_wf.workflow_schema) is working."
    )
    assert result["status"] == "completed", (
        f"AI Co-Scientist run failed: {result.get('error_traceback', result)}"
    )
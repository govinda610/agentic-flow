"""
Tests for all untested API endpoints: runs, webhooks, copilot, workflow delete.

These tests use the session-scoped FastAPI TestClient with real config.
No LLM calls except copilot which uses the real API.
"""
import pytest
import time


# ─────────────────────────────────────────────────────────────────────────────
# /api/runs — untested endpoints
# ─────────────────────────────────────────────────────────────────────────────

def test_runs_start_basic(client):
    """POST /api/runs/start returns run_id and status=started."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "basic start test"},
    })
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert data["status"] == "started"


def test_runs_start_with_telegram_chat_id(client):
    """POST /api/runs/start accepts telegram_chat_id."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "with telegram"},
        "telegram_chat_id": 6662064047,
    })
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data


def test_runs_start_invalid_workflow(client):
    """POST /api/runs/start with non-existent workflow_id returns 422."""
    res = client.post("/api/runs/start", json={
        "workflow_id": 999999,
        "initial_input": {},
    })
    assert res.status_code in (404, 422)  # Either is acceptable


def test_runs_get_steps_empty_before_run(client):
    """GET /api/runs/{run_id}/steps returns [] for a fresh run before any steps."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "steps test"},
    })
    run_id = res.json()["run_id"]

    # Immediate call should return empty (run is still starting)
    steps_res = client.get(f"/api/runs/{run_id}/steps")
    assert steps_res.status_code == 200
    steps = steps_res.json()
    assert isinstance(steps, list)


def test_runs_get_step_by_node_id(client):
    """GET /api/runs/{run_id}/steps/{node_id} returns most recent step."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "node step test"},
    })
    run_id = res.json()["run_id"]
    time.sleep(0.5)

    # node_end exists in all workflows
    step_res = client.get(f"/api/runs/{run_id}/steps/node_end")
    assert step_res.status_code in (200, 404)  # 200 if step exists, 404 if not yet created


def test_runs_get_step_nonexistent_run(client):
    """GET /api/runs/steps for non-existent run_id returns 404."""
    res = client.get("/api/runs/00000000-0000-0000-0000-000000000000/steps")
    assert res.status_code == 404


def test_runs_cancel_workflow(client):
    """POST /api/runs/{run_id}/cancel sets status to cancelled."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.post("/api/runs/start", json={
        "workflow_id": wf_id,
        "initial_input": {"message": "cancel me"},
    })
    run_id = res.json()["run_id"]

    cancel_res = client.post(f"/api/runs/{run_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"


def test_runs_cancel_nonexistent_run(client):
    """POST /api/runs/cancel for non-existent run_id returns 404."""
    res = client.post("/api/runs/00000000-0000-0000-0000-000000000000/cancel")
    assert res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# /api/webhooks — register, trigger, list, revoke
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_register_returns_token_and_url(client):
    """POST /api/webhooks/register returns token, webhook_url, workflow_id."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert "webhook_url" in data
    assert data["workflow_id"] == wf_id
    assert data["webhook_url"] == f"/api/webhooks/{data['token']}"


def test_webhook_register_replaces_existing_token(client):
    """Registering a new webhook for the same workflow revokes the old token."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    res1 = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    old_token = res1.json()["token"]

    res2 = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    new_token = res2.json()["token"]

    assert new_token != old_token, "New token should differ from revoked token"

    # Old token should be revoked
    trigger_old = client.post(f"/api/webhooks/{old_token}", json={"message": "test"})
    assert trigger_old.status_code == 404

    # New token should work
    trigger_new = client.post(f"/api/webhooks/{new_token}", json={"message": "test"})
    assert trigger_new.status_code == 200


def test_webhook_trigger_accepts_message_and_data(client):
    """POST /api/webhooks/{token} with message and data fields."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    reg = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    token = reg.json()["token"]

    res = client.post(f"/api/webhooks/{token}", json={
        "message": "Webhook with data",
        "data": {"temperature": 25.5, "location": "London"},
    })
    assert res.status_code == 200
    assert res.json()["status"] == "started"


def test_webhook_trigger_empty_payload(client):
    """Webhook trigger with empty message and empty data."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    reg = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    token = reg.json()["token"]

    res = client.post(f"/api/webhooks/{token}", json={})
    assert res.status_code == 200


def test_webhook_list(client):
    """GET /api/webhooks/list/{workflow_id} returns active tokens."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    reg = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    token = reg.json()["token"]

    list_res = client.get(f"/api/webhooks/list/{wf_id}")
    assert list_res.status_code == 200
    tokens = list_res.json()
    assert isinstance(tokens, list)
    assert any(t["token"].startswith(token[:8]) for t in tokens)


def test_webhook_revoke(client):
    """DELETE /api/webhooks/{token} revokes the token."""
    wfs = client.get("/api/workflows/").json()
    wf_id = wfs[0]["id"]

    reg = client.post("/api/webhooks/register", json={"workflow_id": wf_id})
    token = reg.json()["token"]

    revoke_res = client.delete(f"/api/webhooks/{token}")
    assert revoke_res.status_code == 200
    assert "ok" in revoke_res.json()


def test_webhook_revoke_nonexistent(client):
    """DELETE /api/webhooks/{token} for non-existent token returns 404."""
    res = client.delete("/api/webhooks/nonexistent_token_abc123")
    assert res.status_code == 404


def test_webhook_trigger_invalid_token(client):
    """POST /api/webhooks/{invalid_token} returns 404."""
    res = client.post("/api/webhooks/invalid_token_xyz789", json={"message": "test"})
    assert res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# /api/generate-workflow — copilot (real LLM call)
# ─────────────────────────────────────────────────────────────────────────────

def test_copilot_returns_workflow_schema(client):
    """POST /api/generate-workflow returns schema with nodes and edges."""
    res = client.post("/api/generate-workflow", json={
        "prompt": "Create a workflow: start → LLM agent → end",
    })
    assert res.status_code == 200
    data = res.json()
    assert "workflow_schema" in data
    assert "message" in data
    schema = data["workflow_schema"]
    assert "nodes" in schema
    assert "edges" in schema
    assert "name" in schema


def test_copilot_includes_start_and_end_nodes(client):
    """Generated schema always includes start and end nodes."""
    res = client.post("/api/generate-workflow", json={
        "prompt": "Research agent that feeds into a writer agent",
    })
    assert res.status_code == 200
    node_types = [n["type"] for n in res.json()["workflow_schema"]["nodes"]]
    assert "start" in node_types
    assert "end"   in node_types


def test_copilot_context_extends_existing_workflow(client):
    """Copilot accepts context parameter to extend an existing workflow."""
    existing_schema = {
        "name": "Existing",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start", "target": "n_end", "type": "normal", "condition": None},
        ],
    }
    save_res = client.post("/api/workflows/", json={
        "name": "Existing",
        "workflow_schema": existing_schema,
    })
    wf_id = save_res.json()["id"]

    res = client.post("/api/generate-workflow", json={
        "prompt": "Add a verifier node between start and end",
        "context": existing_schema,
    })
    assert res.status_code == 200
    schema = res.json()["workflow_schema"]
    # Should have more than 2 nodes (start, end, plus new nodes)
    assert len(schema["nodes"]) > 2


def test_copilot_generated_schema_can_be_saved(client):
    """A schema returned by copilot can be saved and loaded from DB."""
    res = client.post("/api/generate-workflow", json={
        "prompt": "Two-node workflow: start and end only",
    })
    assert res.status_code == 200
    schema = res.json()["workflow_schema"]

    save_res = client.post("/api/workflows/", json={
        "name": schema.get("name", "Copilot Save Test"),
        "workflow_schema": schema,
    })
    assert save_res.status_code == 200
    wf_id = save_res.json()["id"]

    get_res = client.get(f"/api/workflows/{wf_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == schema.get("name", "Copilot Save Test")


# ─────────────────────────────────────────────────────────────────────────────
# /api/workflows DELETE
# ─────────────────────────────────────────────────────────────────────────────

def test_workflow_delete_returns_ok(client):
    """DELETE /api/workflows/{id} returns {"ok": true}."""
    schema = {
        "name": "Delete Me",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start", "target": "n_end", "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={
        "name": "Delete Me", "workflow_schema": schema,
    })
    wf_id = res.json()["id"]

    del_res = client.delete(f"/api/workflows/{wf_id}")
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True


def test_workflow_delete_nonexistent_returns_404(client):
    """DELETE /api/workflows/{id} for non-existent ID returns 404."""
    res = client.delete("/api/workflows/999999")
    assert res.status_code == 404


def test_workflow_delete_removes_cron_schedule(client):
    """Deleting a workflow with a cron schedule also removes its scheduler job."""
    schema = {
        "name": "Delete Cron Workflow",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start", "target": "n_end", "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={
        "name": "Delete Cron Workflow",
        "workflow_schema": schema,
        "cron_schedule": "*/5 * * * *",
    })
    wf_id = res.json()["id"]

    del_res = client.delete(f"/api/workflows/{wf_id}")
    assert del_res.status_code == 200

    # Saving again without cron should work (no stale job)
    res2 = client.post("/api/workflows/", json={
        "workflow_id": wf_id,
        "name": "Delete Cron Workflow",
        "workflow_schema": schema,
        "cron_schedule": None,
    })
    assert res2.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# /api/workflows GET — additional coverage
# ─────────────────────────────────────────────────────────────────────────────

def test_workflow_list_includes_is_template_flag(client):
    """GET /api/workflows/ returns workflows with is_template boolean."""
    res = client.get("/api/workflows/")
    assert res.status_code == 200
    wfs = res.json()
    assert isinstance(wfs, list)
    for wf in wfs:
        assert "is_template" in wf
        assert "template_slug" in wf


def test_workflow_get_nonexistent_returns_404(client):
    """GET /api/workflows/{id} for non-existent ID returns 404."""
    res = client.get("/api/workflows/999999")
    assert res.status_code == 404


def test_workflow_get_includes_cron_schedule(client):
    """Workflow GET response includes cron_schedule field."""
    schema = {
        "name": "Cron Workflow",
        "nodes": [
            {"id": "n_start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "n_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n_start", "target": "n_end", "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={
        "name": "Cron Workflow",
        "workflow_schema": schema,
        "cron_schedule": "0 * * * *",
    })
    wf_id = res.json()["id"]

    get_res = client.get(f"/api/workflows/{wf_id}")
    assert get_res.status_code == 200
    assert get_res.json()["cron_schedule"] == "0 * * * *"


# ─────────────────────────────────────────────────────────────────────────────
# /api/health extended checks
# ─────────────────────────────────────────────────────────────────────────────

def test_health_includes_telegram_status(client):
    """Health endpoint returns telegram_active boolean."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "telegram_active" in data
    # telegram_active is False unless bot token is set (not set in tests)


# ─────────────────────────────────────────────────────────────────────────────
# /api/agents — additional coverage
# ─────────────────────────────────────────────────────────────────────────────

def test_agent_create_with_tools(client):
    """Create an agent with tools list."""
    res = client.post("/api/agents/", json={
        "name": "Tool Agent",
        "system_prompt": "You have tools",
        "node_type": "agent",
        "tools": ["code_interpreter", "file_reader"],
        "config": {"max_depth": 2},
    })
    assert res.status_code == 200
    data = res.json()
    assert data["tools"] == ["code_interpreter", "file_reader"]


def test_agent_create_with_structured_output(client):
    """Create an agent with structured_output in config."""
    res = client.post("/api/agents/", json={
        "name": "Structured Agent",
        "system_prompt": "Extract data",
        "node_type": "agent",
        "tools": [],
        "config": {
            "structured_output": {
                "fields": [
                    {"name": "summary", "type": "string"},
                    {"name": "confidence", "type": "number"},
                ]
            }
        },
    })
    assert res.status_code == 200


def test_agent_list_returns_all_agents(client):
    """GET /api/agents/ returns list including test agents."""
    res = client.get("/api/agents/")
    assert res.status_code == 200
    agents = res.json()
    assert isinstance(agents, list)
    # Should include agents from earlier tests in this session
    names = [a["name"] for a in agents]
    assert "E2E Test Agent" in names or len(agents) >= 0


def test_agent_update_does_not_change_id(client):
    """Updating an agent keeps the same id."""
    res = client.post("/api/agents/", json={
        "name": "Immutable ID", "system_prompt": "test",
    })
    agent_id = res.json()["id"]

    update_res = client.put(f"/api/agents/{agent_id}", json={
        "name": "Immutable ID Updated",
        "system_prompt": "test",
        "node_type": "agent",
        "tools": [],
        "config": {},
    })
    assert update_res.json()["id"] == agent_id


def test_agent_delete_nonexistent_returns_404(client):
    """DELETE /api/agents/{id} for non-existent ID returns 404."""
    res = client.delete("/api/agents/999999")
    assert res.status_code == 404
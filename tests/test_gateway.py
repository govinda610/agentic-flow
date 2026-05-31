import pytest

def test_simulate_gateway_starts_run(client):
    """Gateway simulate: POST to /api/gateway/simulate starts a run."""
    workflows = client.get("/api/workflows/").json()
    assert len(workflows) > 0
    wf_id = workflows[0]["id"]

    res = client.post("/api/gateway/simulate", json={
        "workflow_id": wf_id,
        "message":     "Test message from simulated gateway",
        "user_id":     "test_user_123",
    })
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    assert data["status"] == "started"
    assert data["source"] == "simulated"

def test_simulate_gateway_run_appears_in_db(client):
    """Gateway simulate: created run is persisted and queryable."""
    workflows = client.get("/api/workflows/").json()
    wf_id = workflows[0]["id"]

    res = client.post("/api/gateway/simulate", json={
        "workflow_id": wf_id,
        "message":     "Hello agent!",
    })
    run_id = res.json()["run_id"]

    # Brief wait for the async background task to create the DB record
    import time
    time.sleep(0.5)

    steps_res = client.get(f"/api/runs/{run_id}/steps")
    assert steps_res.status_code == 200

def test_export_workflow_returns_python_script(client):
    """Export: exported workflow is a valid Python script with expected sections."""
    workflows = client.get("/api/workflows/").json()
    assert len(workflows) > 0
    wf_id = workflows[0]["id"]

    res = client.get(f"/api/workflows/{wf_id}/export")
    assert res.status_code == 200
    assert "text/plain" in res.headers.get("content-type", "")

    script = res.text
    assert "import asyncio" in script
    assert "StateGraph" in script
    assert "WorkflowState" in script
    assert "async def main()" in script
    # Ensure no unformatted template placeholders remain
    assert "{node_functions}" not in script
    assert "{graph_nodes}"    not in script

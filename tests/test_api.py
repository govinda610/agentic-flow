import pytest
import json

def test_health(client):
    """Health check returns 200."""
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_create_agent(client):
    """Agent CRUD: create an agent and retrieve it."""
    payload = {
        "name": "Test Agent",
        "system_prompt": "You are a test agent.",
        "node_type": "agent",
        "tools": [],
        "config": {},
    }
    res = client.post("/api/agents/", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Test Agent"
    assert data["id"] is not None

    # Retrieve by listing
    res = client.get("/api/agents/")
    assert res.status_code == 200
    agents = res.json()
    assert any(a["name"] == "Test Agent" for a in agents)

def test_update_agent(client):
    """Agent CRUD: update an existing agent."""
    res = client.post("/api/agents/", json={"name": "Old Name", "system_prompt": "old"})
    agent_id = res.json()["id"]
    res = client.put(f"/api/agents/{agent_id}", json={"name": "New Name", "system_prompt": "new"})
    assert res.status_code == 200
    assert res.json()["name"] == "New Name"

def test_delete_agent(client):
    """Agent CRUD: delete an agent."""
    res = client.post("/api/agents/", json={"name": "Delete Me", "system_prompt": "temp"})
    agent_id = res.json()["id"]
    res = client.delete(f"/api/agents/{agent_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

def test_templates_seeded(client):
    """Startup seeder: templates are present."""
    res = client.get("/api/workflows/")
    assert res.status_code == 200
    workflows = res.json()
    template_names = [w["name"] for w in workflows]
    assert "Data Science Loop"       in template_names
    assert "Deep Researcher Swarm"   in template_names
    assert "AI Co-Scientist"         in template_names

def test_templates_have_slug(client):
    """Templates have non-null template_slug for sub-workflow tool naming."""
    res = client.get("/api/workflows/")
    templates = [w for w in res.json() if w.get("is_template")]
    for t in templates:
        assert t.get("template_slug") is not None, f"Template '{t['name']}' missing template_slug"

def test_save_and_load_workflow(client):
    """Workflow CRUD: save a schema and load it back intact."""
    schema = {
        "name": "Test Workflow",
        "nodes": [
            {"id": "node_start", "type": "start", "position": {"x": 0, "y": 0},   "config": {}},
            {"id": "node_end",   "type": "end",   "position": {"x": 300, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "node_start", "target": "node_end",
             "type": "normal", "condition": None},
        ],
    }
    res = client.post("/api/workflows/", json={"name": "Test Workflow", "workflow_schema": schema})
    assert res.status_code == 200
    wf_id = res.json()["id"]

    res = client.get(f"/api/workflows/{wf_id}")
    assert res.status_code == 200
    returned_schema = res.json()["workflow_schema"]
    assert len(returned_schema["nodes"]) == 2
    assert returned_schema["edges"][0]["source"] == "node_start"

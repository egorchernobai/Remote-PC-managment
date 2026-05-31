import bcrypt
import pytest
from app import db
from app.models import Agent


def test_register_agent_missing_fields(client):
    response = client.post("/api/v1/agents/register", json={"hostname": "host-only"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing fields"


def test_register_agent_invalid_hostname(client):
    response = client.post(
        "/api/v1/agents/register",
        json={"hostname": "bad*host", "os_info": {"platform": "windows"}}
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid hostname"


def test_register_agent_success(client):
    response = client.post(
        "/api/v1/agents/register",
        json={"hostname": "good-host", "os_info": {"platform": "windows"}}
    )
    assert response.status_code == 201
    data = response.get_json()
    assert "agent_id" in data
    assert "token" in data


def test_list_agents_requires_viewer(client, operator_headers):
    response = client.get("/api/v1/agents/", headers=operator_headers)
    assert response.status_code == 200


def test_get_agent_not_found(client, viewer_headers):
    response = client.get("/api/v1/agents/nonexistent", headers=viewer_headers)
    assert response.status_code == 404
    assert response.get_json()["error"] == "Not found"


def test_get_agent_returns_agent(client, viewer_headers):
    token_hash = bcrypt.hashpw(b"secret-token", bcrypt.gensalt()).decode()
    agent = Agent(hostname="agent-1", token_hash=token_hash, os_info={"platform": "linux"}, status="offline")
    db.session.add(agent)
    db.session.commit()

    response = client.get(f"/api/v1/agents/{agent.id}", headers=viewer_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["hostname"] == "agent-1"
    assert data["status"] == "offline"


def test_delete_agent_requires_admin(client, operator_headers):
    token_hash = bcrypt.hashpw(b"secret-token", bcrypt.gensalt()).decode()
    agent = Agent(hostname="agent-2", token_hash=token_hash, os_info={"platform": "linux"}, status="offline")
    db.session.add(agent)
    db.session.commit()

    response = client.delete(f"/api/v1/agents/{agent.id}", headers=operator_headers)
    assert response.status_code == 403
    assert response.get_json()["error"] == "Insufficient permissions"


def test_delete_agent_success(client, admin_headers):
    token_hash = bcrypt.hashpw(b"secret-token", bcrypt.gensalt()).decode()
    agent = Agent(hostname="agent-3", token_hash=token_hash, os_info={"platform": "linux"}, status="offline")
    db.session.add(agent)
    db.session.commit()

    response = client.delete(f"/api/v1/agents/{agent.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json()["status"] == "deleted"
    assert db.session.get(Agent, agent.id) is None


def test_heartbeat_updates_agent(client):
    raw_token = "heartbeat-token-123"
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    agent = Agent(hostname="agent-heartbeat", token_hash=token_hash, os_info={"platform": "linux"}, status="offline")
    db.session.add(agent)
    db.session.commit()

    response = client.post(
        f"/api/v1/agents/{agent.id}/heartbeat",
        json={"sysinfo": {"cpu": "4 cores"}},
        headers={"X-Agent-ID": agent.id, "X-Agent-Token": raw_token}
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    updated = db.session.get(Agent, agent.id)
    assert updated.status == "online"
    assert updated.os_info["cpu"] == "4 cores"

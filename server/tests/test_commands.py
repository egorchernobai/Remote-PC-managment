import bcrypt
import pytest
from app import db
from app.models import Command, Agent


def test_issue_command_missing_fields(client, operator_headers):
    response = client.post("/api/v1/commands/", json={"agent_id": "x"}, headers=operator_headers)
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing fields"


def test_issue_command_type_not_allowed(client, operator_headers):
    response = client.post(
        "/api/v1/commands/",
        json={"agent_id": "x", "command": "echo hi", "cmd_type": "unknown"},
        headers=operator_headers
    )
    assert response.status_code == 403
    assert "not allowed" in response.get_json()["error"]


def test_issue_command_blocked_pattern(client, operator_headers):
    response = client.post(
        "/api/v1/commands/",
        json={"agent_id": "x", "command": "rm -rf /", "cmd_type": "shell"},
        headers=operator_headers
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "Command blocked by security policy"


def test_issue_command_agent_not_found(client, operator_headers):
    response = client.post(
        "/api/v1/commands/",
        json={"agent_id": "nonexistent", "command": "echo ok", "cmd_type": "shell"},
        headers=operator_headers
    )
    assert response.status_code == 404
    assert response.get_json()["error"] == "Agent not found"


def test_issue_command_success(client, operator_headers):
    raw_token = "agent-token-233"
    agent = Agent(
        hostname="cmd-agent",
        token_hash=bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode(),
        os_info={"platform": "linux"},
        status="online"
    )
    db.session.add(agent)
    db.session.commit()

    response = client.post(
        "/api/v1/commands/",
        json={"agent_id": agent.id, "command": "echo hello", "cmd_type": "shell"},
        headers=operator_headers
    )

    assert response.status_code == 201
    assert "command_id" in response.get_json()
    cmd_id = response.get_json()["command_id"]
    created = db.session.get(Command, cmd_id)
    assert created is not None
    assert created.command == "echo hello"


def test_submit_result_unauthorized(client):
    response = client.post("/api/v1/commands/nonexistent/result", json={"output": "ok", "exit_code": 0})
    assert response.status_code == 401


def test_submit_result_command_not_found(client):
    raw_token = "agent-token-234"
    agent = Agent(
        hostname="result-agent",
        token_hash=bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode(),
        os_info={"platform": "linux"},
        status="online"
    )
    db.session.add(agent)
    db.session.commit()

    response = client.post(
        "/api/v1/commands/nonexistent/result",
        headers={"X-Agent-ID": agent.id, "X-Agent-Token": raw_token},
        json={"output": "ok", "exit_code": 0}
    )
    assert response.status_code == 404
    assert response.get_json()["error"] == "Not found"


def test_submit_result_success(client):
    raw_token = "agent-token-235"
    agent = Agent(
        hostname="result-agent-2",
        token_hash=bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode(),
        os_info={"platform": "linux"},
        status="online"
    )
    db.session.add(agent)
    db.session.commit()
    cmd = Command(
        agent_id=agent.id,
        issued_by="issuer",
        command="echo ok",
        cmd_type="shell",
        status="pending"
    )
    db.session.add(cmd)
    db.session.commit()

    response = client.post(
        f"/api/v1/commands/{cmd.id}/result",
        headers={"X-Agent-ID": agent.id, "X-Agent-Token": raw_token},
        json={"output": "done", "exit_code": 0}
    )
    assert response.status_code == 200
    result = db.session.get(Command, cmd.id)
    assert result.status == "done"
    assert result.output == "done"


def test_get_result_not_found(client, viewer_headers):
    response = client.get("/api/v1/commands/nonexistent/result", headers=viewer_headers)
    assert response.status_code == 404
    assert response.get_json()["error"] == "Command not found"


def test_get_result_success(client, viewer_headers):
    raw_token = "agent-token-236"
    agent = Agent(
        hostname="get-result-agent",
        token_hash=bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode(),
        os_info={"platform": "linux"},
        status="online"
    )
    db.session.add(agent)
    db.session.commit()
    cmd = Command(
        agent_id=agent.id,
        issued_by="issuer",
        command="echo output",
        cmd_type="shell",
        status="done",
        output="output text",
        exit_code=0
    )
    db.session.add(cmd)
    db.session.commit()

    response = client.get(f"/api/v1/commands/{cmd.id}/result", headers=viewer_headers)
    assert response.status_code == 200
    assert response.get_json()["output"] == "output text"


def test_list_agent_commands(client, viewer_headers):
    raw_token = "agent-token-237"
    agent = Agent(
        hostname="list-agent",
        token_hash=bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode(),
        os_info={"platform": "linux"},
        status="online"
    )
    db.session.add(agent)
    db.session.commit()
    for i in range(3):
        cmd = Command(
            agent_id=agent.id,
            issued_by="issuer",
            command=f"echo {i}",
            cmd_type="shell",
            status="done"
        )
        db.session.add(cmd)
    db.session.commit()

    response = client.get(f"/api/v1/commands/agent/{agent.id}", headers=viewer_headers)
    assert response.status_code == 200
    assert len(response.get_json()) == 3


def test_get_pending_returns_pending_command(client):
    raw_token = "agent-token-238"
    agent = Agent(
        hostname="pending-agent",
        token_hash=bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode(),
        os_info={"platform": "linux"},
        status="online"
    )
    db.session.add(agent)
    db.session.commit()
    cmd = Command(
        agent_id=agent.id,
        issued_by="issuer",
        command="echo pending",
        cmd_type="shell",
        status="pending"
    )
    db.session.add(cmd)
    db.session.commit()

    response = client.get(
        f"/api/v1/commands/agent/{agent.id}/pending",
        headers={"X-Agent-ID": agent.id, "X-Agent-Token": raw_token}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["command"] == "echo pending"
    updated = db.session.get(Command, cmd.id)
    assert updated.status == "running"

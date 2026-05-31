import io
import os
import bcrypt
import pytest
from app import db
from app.models import FileTransfer, Agent, Command


def test_upload_to_agent_no_file(client, operator_headers):
    response = client.post("/api/v1/files/upload/agent-1", headers=operator_headers)
    assert response.status_code == 400
    assert response.get_json()["error"] == "No file"


def test_upload_to_agent_disallowed_extension(client, operator_headers, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.files.Config.UPLOAD_FOLDER", str(tmp_path))
    response = client.post(
        "/api/v1/files/upload/agent-1",
        data={"file": (io.BytesIO(b"data"), "malware.exe")},
        content_type="multipart/form-data",
        headers=operator_headers
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "File type not allowed"


def test_upload_to_agent_success(client, operator_headers, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.files.Config.UPLOAD_FOLDER", str(tmp_path))
    raw_token = "upload-token-1"
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    agent = Agent(hostname="upload-agent", token_hash=token_hash, os_info={"platform": "linux"}, status="online")
    db.session.add(agent)
    db.session.commit()

    response = client.post(
        f"/api/v1/files/upload/{agent.id}",
        data={"file": (io.BytesIO(b"hello world"), "hello.txt")},
        content_type="multipart/form-data",
        headers=operator_headers
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "transfer_id" in data
    assert "sha256" in data
    transfer = db.session.get(FileTransfer, data["transfer_id"])
    assert transfer is not None
    assert transfer.filename == "hello.txt"
    assert (tmp_path / transfer.id / "hello.txt").read_bytes() == b"hello world"
    command = db.session.get(Command, data["command_id"])
    assert command is not None
    assert command.cmd_type == "file_upload"


def test_agent_fetch_file_unauthorized(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.files.Config.UPLOAD_FOLDER", str(tmp_path))
    response = client.get("/api/v1/files/fetch/doesntmatter")
    assert response.status_code == 401
    assert response.get_json()["error"] == "Unauthorized"


def test_agent_fetch_file_success(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.files.Config.UPLOAD_FOLDER", str(tmp_path))
    raw_token = "fetch-token-1"
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    agent = Agent(hostname="fetch-agent", token_hash=token_hash, os_info={"platform": "linux"}, status="online")
    db.session.add(agent)
    db.session.commit()
    transfer_id = "transfer123"
    transfer_dir = tmp_path / transfer_id
    transfer_dir.mkdir(parents=True, exist_ok=True)
    file_path = transfer_dir / "hello.txt"
    file_path.write_bytes(b"hello")
    transfer = FileTransfer(
        agent_id=agent.id,
        initiated_by="user1",
        direction="upload",
        filename="hello.txt",
        sha256="abc123",
        size_bytes=5,
        status="ready"
    )
    transfer.id = transfer_id
    db.session.add(transfer)
    db.session.commit()

    response = client.get(
        f"/api/v1/files/fetch/{transfer_id}",
        headers={"X-Agent-ID": agent.id, "X-Agent-Token": raw_token}
    )
    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment")
    assert response.data == b"hello"

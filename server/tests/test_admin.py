import bcrypt
import io
import json
import zipfile
from app import db
from app.models import User, AuditLog


def test_list_users_requires_admin(client, operator_headers):
    response = client.get("/api/v1/admin/users", headers=operator_headers)
    assert response.status_code == 403


def test_create_user_success(client, admin_headers):
    response = client.post(
        "/api/v1/admin/users",
        json={"username": "newuser", "password": "LongPassword123!", "role": "viewer"},
        headers=admin_headers
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["username"] == "newuser"
    assert db.session.query(User).filter_by(username="newuser").first() is not None


def test_create_user_invalid_username(client, admin_headers):
    response = client.post(
        "/api/v1/admin/users",
        json={"username": "no space", "password": "LongPassword123!", "role": "viewer"},
        headers=admin_headers
    )
    assert response.status_code == 400


def test_create_user_short_password(client, admin_headers):
    response = client.post(
        "/api/v1/admin/users",
        json={"username": "shortpw", "password": "short", "role": "viewer"},
        headers=admin_headers
    )
    assert response.status_code == 400
    assert "Password must be at least 12 characters" in response.get_json()["error"]


def test_update_user_change_role_and_active(client, admin_headers):
    user = User(username="updatable", password_hash=bcrypt.hashpw(b"Password123!", bcrypt.gensalt()).decode(), role="viewer")
    db.session.add(user)
    db.session.commit()

    response = client.patch(
        f"/api/v1/admin/users/{user.id}",
        json={"role": "operator", "is_active": False},
        headers=admin_headers
    )
    assert response.status_code == 200
    updated = db.session.get(User, user.id)
    assert updated.role == "operator"
    assert updated.is_active is False


def test_delete_user_self_fails(client, admin_user, admin_headers):
    response = client.delete(f"/api/v1/admin/users/{admin_user.id}", headers=admin_headers)
    assert response.status_code == 400
    assert response.get_json()["error"] == "Cannot delete yourself"


def test_delete_user_success(client, admin_headers):
    user = User(username="victim", password_hash=bcrypt.hashpw(b"Password123!", bcrypt.gensalt()).decode(), role="viewer")
    db.session.add(user)
    db.session.commit()

    response = client.delete(f"/api/v1/admin/users/{user.id}", headers=admin_headers)
    assert response.status_code == 200
    assert db.session.get(User, user.id) is None


def test_get_audit_logs(client, operator_headers):
    log = AuditLog(actor_id="actor1", actor_type="user", action="test_action", target="target1", details={"x": 1})
    db.session.add(log)
    db.session.commit()

    response = client.get("/api/v1/admin/logs", headers=operator_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["items"][0]["action"] == "test_action"


def test_download_agent_package(client, admin_headers, monkeypatch, tmp_path):
    binary = tmp_path / "rmm-agent.exe"
    binary.write_bytes(b"agent-bin")
    agent_ca = tmp_path / "ca.crt"
    agent_cert = tmp_path / "agent.crt"
    agent_key = tmp_path / "agent.key"
    agent_ca.write_text("ca")
    agent_cert.write_text("cert")
    agent_key.write_text("key")

    monkeypatch.setattr("app.api.admin._build_agent", lambda _target="native": binary)
    monkeypatch.setattr("app.api.admin.ensure_certificates", lambda _config: {
        "agent_ca": str(agent_ca),
        "agent_cert": str(agent_cert),
        "agent_key": str(agent_key),
    })

    response = client.get("/api/v1/admin/agent-package", headers=admin_headers)
    assert response.status_code == 200
    assert response.mimetype == "application/zip"

    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        names = set(archive.namelist())
        assert {"rmm-agent.exe", "config.json", "ca.crt", "agent.crt", "agent.key"} <= names
        config = json.loads(archive.read("config.json"))
        assert config["server_url"].startswith("https://")
        assert config["ca_cert_path"] == "ca.crt"


def test_download_agent_package_target(client, admin_headers, monkeypatch, tmp_path):
    binary = tmp_path / "rmm-agent.exe"
    binary.write_bytes(b"agent-bin")
    agent_ca = tmp_path / "ca.crt"
    agent_cert = tmp_path / "agent.crt"
    agent_key = tmp_path / "agent.key"
    agent_ca.write_text("ca")
    agent_cert.write_text("cert")
    agent_key.write_text("key")
    requested_targets = []

    def fake_build_agent(target):
        requested_targets.append(target)
        return binary

    monkeypatch.setattr("app.api.admin._build_agent", fake_build_agent)
    monkeypatch.setattr("app.api.admin.ensure_certificates", lambda _config: {
        "agent_ca": str(agent_ca),
        "agent_cert": str(agent_cert),
        "agent_key": str(agent_key),
    })

    response = client.get("/api/v1/admin/agent-package?target=windows-x64", headers=admin_headers)
    assert response.status_code == 200
    assert requested_targets == ["windows-x64"]
    assert response.headers["Content-Disposition"].endswith("rmm-agent-package-windows-x64.zip")


def test_download_agent_package_invalid_target(client, admin_headers):
    response = client.get("/api/v1/admin/agent-package?target=bad-target", headers=admin_headers)
    assert response.status_code == 400
    assert "Unsupported agent build target" in response.get_json()["error"]

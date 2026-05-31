import bcrypt
import os
import tempfile
from datetime import timedelta
import pytest
from flask_jwt_extended import create_access_token

from app import create_app, db
from app.config import Config
from app.models import User, Agent, Command, FileTransfer

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(minutes=10)
    RATELIMIT_ENABLED = False
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_user(username: str, role: str = "viewer", password: str = "Password123!", is_active: bool = True):
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active
    )
    db.session.add(user)
    db.session.commit()
    return user


def create_agent(hostname: str = "agent1", os_info: dict | None = None,
                 status: str = "offline", raw_token: str = "agent-token-123"):
    if os_info is None:
        os_info = {"platform": "windows"}
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    agent = Agent(
        hostname=hostname,
        token_hash=token_hash,
        os_info=os_info,
        status=status
    )
    db.session.add(agent)
    db.session.commit()
    return agent, raw_token


def create_command(agent_id: str, issued_by: str,
                   command: str = "echo test", cmd_type: str = "shell",
                   status: str = "pending"):
    cmd = Command(
        agent_id=agent_id,
        issued_by=issued_by,
        command=command,
        cmd_type=cmd_type,
        status=status
    )
    db.session.add(cmd)
    db.session.commit()
    return cmd


def create_file_transfer(agent_id: str, initiated_by: str, filename: str,
                         sha256: str, size_bytes: int, direction: str = "upload"):
    transfer = FileTransfer(
        agent_id=agent_id,
        initiated_by=initiated_by,
        direction=direction,
        filename=filename,
        sha256=sha256,
        size_bytes=size_bytes,
        status="ready"
    )
    db.session.add(transfer)
    db.session.commit()
    return transfer


def make_auth_headers(user_id: str, role: str = "viewer") -> dict[str, str]:
    access = create_access_token(identity=user_id, additional_claims={"role": role})
    return {"Authorization": f"Bearer {access}"}


@pytest.fixture
def test_app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def admin_user(test_app):
    return create_user("admin", role="admin")


@pytest.fixture
def operator_user(test_app):
    return create_user("operator", role="operator")


@pytest.fixture
def viewer_user(test_app):
    return create_user("viewer", role="viewer")


@pytest.fixture
def admin_headers(admin_user):
    return make_auth_headers(admin_user.id, "admin")


@pytest.fixture
def operator_headers(operator_user):
    return make_auth_headers(operator_user.id, "operator")


@pytest.fixture
def viewer_headers(viewer_user):
    return make_auth_headers(viewer_user.id, "viewer")


@pytest.fixture
def test_user(test_app):
    return create_user("testuser", role="admin")

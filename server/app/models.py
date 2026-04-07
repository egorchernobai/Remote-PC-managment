import uuid
from datetime import datetime, timezone
from app import db

def new_uuid():
    return str(uuid.uuid4())

class User(db.Model):
    __tablename__ = "users"
    id           = db.Column(db.String(36), primary_key=True, default=new_uuid)
    username     = db.Column(db.String(64), unique=True, nullable=False)
    password_hash= db.Column(db.String(256), nullable=False)
    role         = db.Column(db.String(32), nullable=False, default="viewer")
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Agent(db.Model):
    __tablename__ = "agents"
    id               = db.Column(db.String(36), primary_key=True, default=new_uuid)
    hostname         = db.Column(db.String(256), nullable=False)
    token_hash       = db.Column(db.String(256), nullable=False)
    cert_fingerprint = db.Column(db.String(128))
    os_info          = db.Column(db.JSON)
    last_seen        = db.Column(db.DateTime)
    status           = db.Column(db.String(16), default="offline")
    registered_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    commands         = db.relationship("Command", backref="agent", lazy=True)

class Command(db.Model):
    __tablename__ = "commands"
    id           = db.Column(db.String(36), primary_key=True, default=new_uuid)
    agent_id     = db.Column(db.String(36), db.ForeignKey("agents.id"), nullable=False)
    issued_by    = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    command      = db.Column(db.Text, nullable=False)
    cmd_type     = db.Column(db.String(32))
    status       = db.Column(db.String(16), default="pending")
    output       = db.Column(db.Text)
    exit_code    = db.Column(db.Integer)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime)

class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id         = db.Column(db.String(36), primary_key=True, default=new_uuid)
    actor_id   = db.Column(db.String(36))
    actor_type = db.Column(db.String(16))
    action     = db.Column(db.String(128), nullable=False)
    target     = db.Column(db.String(256))
    details    = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class FileTransfer(db.Model):
    __tablename__ = "file_transfers"
    id           = db.Column(db.String(36), primary_key=True, default=new_uuid)
    agent_id     = db.Column(db.String(36), db.ForeignKey("agents.id"))
    initiated_by = db.Column(db.String(36), db.ForeignKey("users.id"))
    direction    = db.Column(db.String(8))
    filename     = db.Column(db.String(512))
    sha256       = db.Column(db.String(64))
    size_bytes   = db.Column(db.BigInteger)
    status       = db.Column(db.String(16), default="pending")
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

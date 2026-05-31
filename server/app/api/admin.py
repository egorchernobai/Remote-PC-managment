import io
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path

import bcrypt
from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity

from app import db, limiter
from app.audit import log_action
from app.auth import role_required
from app.cert_bootstrap import ensure_certificates
from app.models import AuditLog, User


admin_bp = Blueprint("admin", __name__)

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{3,64}$")
VALID_ROLES = {"admin", "operator", "viewer"}
AGENT_BUILD_TIMEOUT_SECS = 180


def _hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"]).resolve()


def _agent_binary_name() -> str:
    return "rmm-agent.exe" if os.name == "nt" else "rmm-agent"


def _windows_x64_rust_target() -> str:
    return "x86_64-pc-windows-msvc" if os.name == "nt" else "x86_64-pc-windows-gnu"


AGENT_BUILD_TARGETS = {
    "native": {
        "label": "Current machine",
        "rust_target": lambda: None,
        "binary": _agent_binary_name,
    },
    "windows-x64": {
        "label": "Windows x64",
        "rust_target": _windows_x64_rust_target,
        "binary": lambda: "rmm-agent.exe",
    },
    "linux-x64": {
        "label": "Linux x64",
        "rust_target": lambda: "x86_64-unknown-linux-gnu",
        "binary": lambda: "rmm-agent",
    },
    "linux-arm64": {
        "label": "Linux ARM64",
        "rust_target": lambda: "aarch64-unknown-linux-gnu",
        "binary": lambda: "rmm-agent",
    },
}


def _agent_build_target(target_key: str) -> dict[str, object]:
    target = AGENT_BUILD_TARGETS.get(target_key)
    if not target:
        raise ValueError(f"Unsupported agent build target: {target_key}")
    return target


def _build_agent(target_key: str = "native") -> Path:
    target = _agent_build_target(target_key)
    rust_target = target["rust_target"]()
    binary_name = target["binary"]()
    profile = os.environ.get("AGENT_BUILD_PROFILE", "debug").lower()
    if profile not in {"debug", "release"}:
        profile = "debug"

    agent_dir = _project_root() / "agent"
    command = ["cargo", "build"]
    if rust_target:
        command.extend(["--target", rust_target])
    if profile == "release":
        command.append("--release")

    try:
        subprocess.run(
            command,
            cwd=agent_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=AGENT_BUILD_TIMEOUT_SECS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Cargo is not installed or not available in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Agent build timed out") from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(output[-2000:] or "Agent build failed") from exc

    binary_dir = agent_dir / "target"
    if rust_target:
        binary_dir = binary_dir / rust_target
    binary = binary_dir / profile / binary_name
    if not binary.exists():
        raise RuntimeError(f"Built agent binary not found: {binary}")
    return binary


def _agent_server_host() -> str:
    explicit = os.environ.get("AGENT_SERVER_HOST", "").strip()
    if explicit:
        return explicit

    public_hosts = os.environ.get("SERVER_PUBLIC_HOSTS", "")
    for host in public_hosts.split(","):
        host = host.strip()
        if host:
            return _with_request_port(host)

    return request.host


def _with_request_port(host: str) -> str:
    if ":" in host:
        return host
    port = request.host.rsplit(":", 1)[1] if ":" in request.host else ""
    return f"{host}:{port}" if port else host


def _agent_config() -> dict:
    scheme = "https" if str(current_app.config.get("USE_TLS", "")).lower() == "true" else request.scheme
    ws_scheme = "wss" if scheme == "https" else "ws"
    host = _agent_server_host()
    return {
        "server_url": f"{scheme}://{host}",
        "ws_url": f"{ws_scheme}://{host}/ws/agent",
        "ca_cert_path": "ca.crt",
        "agent_cert": "agent.crt",
        "agent_key": "agent.key",
        "state_file": "agent_state.json",
        "heartbeat_secs": 30,
    }


def _write_archive(binary: Path, cert_info: dict[str, object]) -> io.BytesIO:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(binary, arcname=binary.name)
        zf.writestr("config.json", json.dumps(_agent_config(), indent=2, ensure_ascii=False))
        zf.write(str(cert_info["agent_ca"]), arcname="ca.crt")
        zf.write(str(cert_info["agent_cert"]), arcname="agent.crt")
        zf.write(str(cert_info["agent_key"]), arcname="agent.key")
    archive.seek(0)
    return archive


@admin_bp.route("/users", methods=["GET"])
@role_required("admin")
def list_users():
    users = User.query.all()
    return jsonify([{
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": str(user.created_at),
    } for user in users])


@admin_bp.route("/agent-package", methods=["GET"])
@role_required("admin")
def download_agent_package():
    target_key = request.args.get("target", "native")
    try:
        cert_info = ensure_certificates(current_app.config)
        _agent_build_target(target_key)
        binary = _build_agent(target_key)
        archive = _write_archive(binary, cert_info)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    log_action(
        get_jwt_identity(),
        "user",
        "agent_package_generated",
        details={"binary": str(binary), "target": target_key},
    )
    return send_file(
        archive,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"rmm-agent-package-{target_key}.zip",
    )


@admin_bp.route("/users", methods=["POST"])
@role_required("admin")
@limiter.limit("20/hour")
def create_user():
    data = request.get_json(force=True)
    username = str(data.get("username", ""))
    password = str(data.get("password", ""))
    role = str(data.get("role", "viewer"))

    if not USERNAME_RE.match(username):
        return jsonify({"error": "Invalid username format"}), 400
    if role not in VALID_ROLES:
        return jsonify({"error": f"Role must be one of {VALID_ROLES}"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    try:
        pw_hash = _hash_password(password)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    user = User(username=username, password_hash=pw_hash, role=role)
    db.session.add(user)
    db.session.commit()

    log_action(get_jwt_identity(), "user", "user_created", target=username, details={"role": role})
    return jsonify({"id": user.id, "username": user.username}), 201


@admin_bp.route("/users/<user_id>", methods=["PATCH"])
@role_required("admin")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(force=True)
    changes = {}

    if "role" in data:
        if data["role"] not in VALID_ROLES:
            return jsonify({"error": "Invalid role"}), 400
        user.role = data["role"]
        changes["role"] = data["role"]

    if "is_active" in data:
        user.is_active = bool(data["is_active"])
        changes["is_active"] = user.is_active

    if "password" in data:
        try:
            user.password_hash = _hash_password(str(data["password"]))
            changes["password"] = "changed"
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    db.session.commit()
    log_action(get_jwt_identity(), "user", "user_updated", target=user.username, details=changes)
    return jsonify({"status": "updated"})


@admin_bp.route("/users/<user_id>", methods=["DELETE"])
@role_required("admin")
def delete_user(user_id):
    current_user_id = get_jwt_identity()
    if user_id == current_user_id:
        return jsonify({"error": "Cannot delete yourself"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404

    log_action(current_user_id, "user", "user_deleted", target=user.username)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "deleted"})


@admin_bp.route("/logs", methods=["GET"])
@role_required("operator")
def get_audit_logs():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    actor = request.args.get("actor")
    action = request.args.get("action")

    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    if actor:
        query = query.filter(AuditLog.actor_id == actor)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "total": paginated.total,
        "page": page,
        "pages": paginated.pages,
        "items": [{
            "id": log.id,
            "actor_id": log.actor_id,
            "actor_type": log.actor_type,
            "action": log.action,
            "target": log.target,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": str(log.created_at),
        } for log in paginated.items],
    })

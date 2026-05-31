import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app import db, limiter
from app.audit import log_action
from app.auth import role_required, verify_agent_token
from app.command_queue import pop_pending, push_command
from app.config import Config
from app.models import Agent, Command


commands_bp = Blueprint("commands", __name__)

BLOCKED_PATTERNS = [
    r"(rm\s+-rf\s*/)",
    r"(mkfs\.)",
    r"(>\s*/dev/sd)",
    r"(wget|curl).*\|\s*(bash|sh|python)",
    r"(base64\s+-d.*\|)",
]


def is_safe_command(cmd: str) -> bool:
    return not any(re.search(pattern, cmd, re.IGNORECASE) for pattern in BLOCKED_PATTERNS)


@commands_bp.route("/", methods=["POST"])
@role_required("operator")
@limiter.limit("60/minute")
def issue_command():
    data = request.get_json(force=True)
    required = {"agent_id", "command", "cmd_type"}
    if not required.issubset(data.keys()):
        return jsonify({"error": "Missing fields"}), 400

    cmd_type = data["cmd_type"]
    if cmd_type not in Config.ALLOWED_COMMANDS:
        return jsonify({"error": f"Command type '{cmd_type}' not allowed"}), 403

    command_text = str(data["command"])[:8192]
    if not is_safe_command(command_text):
        log_action(
            get_jwt_identity(),
            "user",
            "blocked_dangerous_command",
            details={"cmd": command_text[:200]},
        )
        return jsonify({"error": "Command blocked by security policy"}), 403

    agent = db.session.get(Agent, data["agent_id"])
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    cmd = Command(
        agent_id=agent.id,
        issued_by=get_jwt_identity(),
        command=command_text,
        cmd_type=cmd_type,
        status="pending",
    )
    db.session.add(cmd)
    db.session.commit()

    push_command(agent.id, cmd.id)
    log_action(
        get_jwt_identity(),
        "user",
        "command_issued",
        target=agent.hostname,
        details={"cmd_id": cmd.id, "type": cmd_type},
    )
    return jsonify({"command_id": cmd.id}), 201


@commands_bp.route("/<cmd_id>/result", methods=["POST"])
def submit_result(cmd_id):
    agent = verify_agent_token(
        request.headers.get("X-Agent-ID"),
        request.headers.get("X-Agent-Token"),
    )
    if not agent:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True)
    cmd = db.session.get(Command, cmd_id)
    if not cmd or cmd.agent_id != agent.id:
        return jsonify({"error": "Not found"}), 404

    cmd.output = str(data.get("output", ""))[:65536]
    cmd.exit_code = int(data.get("exit_code", -1))
    cmd.status = "done" if cmd.exit_code == 0 else "failed"
    cmd.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"status": "ok"})


@commands_bp.route("/<cmd_id>/result", methods=["GET"])
@role_required("viewer")
def get_result(cmd_id):
    cmd = db.session.get(Command, cmd_id)
    if not cmd:
        return jsonify({"error": "Command not found"}), 404
    return jsonify({
        "id": cmd.id,
        "agent_id": cmd.agent_id,
        "command": cmd.command,
        "cmd_type": cmd.cmd_type,
        "status": cmd.status,
        "output": cmd.output,
        "exit_code": cmd.exit_code,
        "created_at": str(cmd.created_at),
        "completed_at": str(cmd.completed_at) if cmd.completed_at else None,
    })


@commands_bp.route("/agent/<agent_id>", methods=["GET"])
@role_required("viewer")
def list_agent_commands(agent_id):
    limit = min(request.args.get("limit", 20, type=int), 100)
    cmds = (
        Command.query.filter_by(agent_id=agent_id)
        .order_by(Command.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify([{
        "id": c.id,
        "command": c.command,
        "cmd_type": c.cmd_type,
        "status": c.status,
        "exit_code": c.exit_code,
        "created_at": str(c.created_at),
        "completed_at": str(c.completed_at) if c.completed_at else None,
    } for c in cmds])


@commands_bp.route("/agent/<agent_id>/pending", methods=["GET"])
def get_pending(agent_id):
    agent = verify_agent_token(
        request.headers.get("X-Agent-ID"),
        request.headers.get("X-Agent-Token"),
    )
    if not agent or agent.id != agent_id:
        return jsonify({"error": "Unauthorized"}), 401

    cmd_ids = pop_pending(agent_id)
    db_cmds = Command.query.filter_by(agent_id=agent_id, status="pending").all()
    all_ids = list(set(cmd_ids + [c.id for c in db_cmds]))

    result = []
    for cmd_id in all_ids:
        cmd = db.session.get(Command, cmd_id)
        if cmd and cmd.status == "pending":
            cmd.status = "running"
            db.session.commit()
            result.append({
                "id": cmd.id,
                "command": cmd.command,
                "cmd_type": cmd.cmd_type,
            })

    return jsonify(result)

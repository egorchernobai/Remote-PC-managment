import secrets
from datetime import datetime, timezone

import bcrypt
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app import db, limiter
from app.audit import log_action
from app.auth import agent_auth_required, role_required
from app.models import Agent


agents_bp = Blueprint("agents", __name__)


@agents_bp.route("/register", methods=["POST"])
@limiter.limit("10/hour")
def register_agent():
    data = request.get_json(force=True)
    required = {"hostname", "os_info"}
    if not required.issubset(data.keys()):
        return jsonify({"error": "Missing fields"}), 400

    hostname = str(data["hostname"])[:256]
    if not hostname.replace("-", "").replace(".", "").replace("_", "").isalnum():
        return jsonify({"error": "Invalid hostname"}), 400

    raw_token = secrets.token_urlsafe(48)
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt(12)).decode()

    agent = Agent(
        hostname=hostname,
        token_hash=token_hash,
        os_info=data["os_info"],
        status="online",
        last_seen=datetime.now(timezone.utc),
    )
    db.session.add(agent)
    db.session.commit()

    log_action(agent.id, "agent", "registered", target=hostname)
    return jsonify({"agent_id": agent.id, "token": raw_token}), 201


@agents_bp.route("/", methods=["GET"])
@role_required("viewer")
def list_agents():
    agents = Agent.query.all()
    return jsonify([{
        "id": a.id,
        "hostname": a.hostname,
        "status": a.status,
        "last_seen": str(a.last_seen),
        "os_info": a.os_info,
    } for a in agents])


@agents_bp.route("/<agent_id>/heartbeat", methods=["POST"])
@agent_auth_required
def heartbeat(agent_id):
    data = request.get_json(force=True)
    agent = request.agent
    agent.last_seen = datetime.now(timezone.utc)
    agent.status = "online"
    if "sysinfo" in data:
        agent.os_info = {**(agent.os_info or {}), **data["sysinfo"]}
    db.session.commit()
    return jsonify({"status": "ok"})


@agents_bp.route("/<agent_id>", methods=["DELETE"])
@role_required("admin")
def delete_agent(agent_id):
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return jsonify({"error": "Not found"}), 404
    log_action(get_jwt_identity(), "user", "agent_deleted", target=agent.hostname)
    db.session.delete(agent)
    db.session.commit()
    return jsonify({"status": "deleted"})


@agents_bp.route("/<agent_id>", methods=["GET"])
@role_required("viewer")
def get_agent(agent_id):
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "id": agent.id,
        "hostname": agent.hostname,
        "status": agent.status,
        "os_info": agent.os_info,
        "last_seen": str(agent.last_seen) if agent.last_seen else None,
        "registered_at": str(agent.registered_at),
    })

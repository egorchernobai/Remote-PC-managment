from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from app import db
from app.models import Agent


ROLE_HIERARCHY = {"viewer": 0, "operator": 1, "admin": 2}


def role_required(minimum_role: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            user_role = claims.get("role", "viewer")
            if ROLE_HIERARCHY.get(user_role, 0) < ROLE_HIERARCHY.get(minimum_role, 99):
                return jsonify({"error": "Insufficient permissions"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def verify_agent_token(agent_id: str, raw_token: str) -> Agent | None:
    from bcrypt import checkpw

    if not agent_id or not raw_token:
        return None

    agent = db.session.get(Agent, agent_id)
    if not agent:
        return None
    if checkpw(raw_token.encode(), agent.token_hash.encode()):
        return agent
    return None


def agent_auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        agent_id = request.headers.get("X-Agent-ID")
        token = request.headers.get("X-Agent-Token")
        if not agent_id or not token:
            return jsonify({"error": "Missing agent credentials"}), 401
        agent = verify_agent_token(agent_id, token)
        if not agent:
            return jsonify({"error": "Invalid agent credentials"}), 401
        request.agent = agent
        return fn(*args, **kwargs)

    return wrapper

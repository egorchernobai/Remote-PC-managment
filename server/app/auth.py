from functools import wraps
from flask import request, jsonify, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from app.models import Agent
from app import db
import hashlib, hmac

# ── RBAC декораторы ──────────────────────────────────────────

ROLE_HIERARCHY = {"viewer": 0, "operator": 1, "admin": 2}

def role_required(minimum_role: str):
    """Проверяет, что роль пользователя >= требуемой."""
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

# ── Аутентификация агентов ───────────────────────────────────

def verify_agent_token(agent_id: str, raw_token: str) -> Agent | None:
    """Проверяет токен агента через bcrypt-хеш. Защита от timing attacks."""
    from bcrypt import checkpw
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return None
    token_bytes = raw_token.encode()
    stored_hash = agent.token_hash.encode()
    if checkpw(token_bytes, stored_hash):
        return agent
    return None

def agent_auth_required(fn):
    """Декоратор для эндпоинтов, вызываемых агентом."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        agent_id = request.headers.get("X-Agent-ID")
        token    = request.headers.get("X-Agent-Token")
        if not agent_id or not token:
            return jsonify({"error": "Missing agent credentials"}), 401
        agent = verify_agent_token(agent_id, token)
        if not agent:
            return jsonify({"error": "Invalid agent credentials"}), 401
        request.agent = agent
        return fn(*args, **kwargs)
    return wrapper

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app import db, limiter
from app.models import User, AuditLog
from app.auth import role_required
from app.audit import log_action
import bcrypt, re

admin_bp = Blueprint("admin", __name__)

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{3,64}$")
VALID_ROLES  = {"admin", "operator", "viewer"}


def _hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


@admin_bp.route("/users", methods=["GET"])
@role_required("admin")
def list_users():
    users = User.query.all()
    return jsonify([{
        "id": u.id, "username": u.username,
        "role": u.role, "is_active": u.is_active,
        "created_at": str(u.created_at)
    } for u in users])


@admin_bp.route("/users", methods=["POST"])
@role_required("admin")
@limiter.limit("20/hour")
def create_user():
    data = request.get_json(force=True)
    username = str(data.get("username", ""))
    password = str(data.get("password", ""))
    role     = str(data.get("role", "viewer"))

    if not USERNAME_RE.match(username):
        return jsonify({"error": "Invalid username format"}), 400
    if role not in VALID_ROLES:
        return jsonify({"error": f"Role must be one of {VALID_ROLES}"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    try:
        pw_hash = _hash_password(password)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    user = User(username=username, password_hash=pw_hash, role=role)
    db.session.add(user)
    db.session.commit()

    log_action(get_jwt_identity(), "user", "user_created",
               target=username, details={"role": role})
    return jsonify({"id": user.id, "username": user.username}), 201


@admin_bp.route("/users/<user_id>", methods=["PATCH"])
@role_required("admin")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404

    data    = request.get_json(force=True)
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
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    db.session.commit()
    log_action(get_jwt_identity(), "user", "user_updated",
               target=user.username, details=changes)
    return jsonify({"status": "updated"})


@admin_bp.route("/users/<user_id>", methods=["DELETE"])
@role_required("admin")
def delete_user(user_id):
    me = get_jwt_identity()
    if user_id == me:
        return jsonify({"error": "Cannot delete yourself"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404

    log_action(me, "user", "user_deleted", target=user.username)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "deleted"})


@admin_bp.route("/logs", methods=["GET"])
@role_required("operator")
def get_audit_logs():
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    actor    = request.args.get("actor")
    action   = request.args.get("action")

    q = AuditLog.query.order_by(AuditLog.created_at.desc())
    if actor:
        q = q.filter(AuditLog.actor_id == actor)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))

    paginated = q.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "total":   paginated.total,
        "page":    page,
        "pages":   paginated.pages,
        "items": [{
            "id":         l.id,
            "actor_id":   l.actor_id,
            "actor_type": l.actor_type,
            "action":     l.action,
            "target":     l.target,
            "details":    l.details,
            "ip_address": l.ip_address,
            "created_at": str(l.created_at)
        } for l in paginated.items]
    })

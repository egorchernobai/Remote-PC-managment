from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from app.models import User
from app import db, limiter
import bcrypt

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10/minute")
def login():
    data = request.get_json(force=True)
    username = str(data.get("username", ""))[:64]
    password = str(data.get("password", ""))

    user = User.query.filter_by(username=username, is_active=True).first()
    # Всегда выполняем checkpw, даже если user=None (anti-timing)
    dummy = b"$2b$12$AAAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    stored = user.password_hash.encode() if user else dummy
    valid = bcrypt.checkpw(password.encode(), stored) and user is not None

    if not valid:
        return jsonify({"error": "Invalid credentials"}), 401

    access  = create_access_token(identity=user.id,
                                   additional_claims={"role": user.role})
    refresh = create_refresh_token(identity=user.id)
    return jsonify({"access_token": access, "refresh_token": refresh})

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    access = create_access_token(identity=user.id,
                                  additional_claims={"role": user.role})
    return jsonify({"access_token": access})

from functools import wraps

import bcrypt
from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token

from app.models import User


views_bp = Blueprint("views", __name__)


def get_current_user():
    token = session.get("access_token")
    if not token:
        return None
    try:
        return decode_token(token)
    except Exception:
        return None


def login_required_view(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("views.login"))
        return fn(*args, **kwargs)

    return wrapper


@views_bp.route("/")
def index():
    return redirect(url_for("views.dashboard"))


@views_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username, is_active=True).first()
        dummy = b"$2b$12$AAAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        stored = user.password_hash.encode() if user else dummy
        valid = bcrypt.checkpw(password.encode(), stored) and user is not None

        if valid:
            access = create_access_token(identity=user.id, additional_claims={"role": user.role})
            refresh = create_refresh_token(identity=user.id)
            session["access_token"] = access
            session["refresh_token"] = refresh
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("views.dashboard"))

        error = "Invalid username or password"

    return render_template("login.html", error=error)


@views_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("views.login"))


@views_bp.route("/dashboard")
@login_required_view
def dashboard():
    return render_page("dashboard.html", "dashboard")


@views_bp.route("/agents")
@login_required_view
def agents():
    return render_page("dashboard.html", "agents")


@views_bp.route("/agents/<agent_id>")
@login_required_view
def agent_detail(agent_id):
    return render_page("agent_detail.html", "agents", agent_id=agent_id)


@views_bp.route("/logs")
@login_required_view
def logs():
    return render_page("logs.html", "logs")


@views_bp.route("/admin")
@login_required_view
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("views.dashboard"))
    return render_page("admin.html", "admin")


def render_page(template: str, active: str, **context):
    return render_template(
        template,
        active=active,
        username=session.get("username"),
        role=session.get("role"),
        **context,
    )

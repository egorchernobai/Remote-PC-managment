from flask import Blueprint, render_template, redirect, url_for, request, session
from flask_jwt_extended import decode_token
from jwt.exceptions import InvalidTokenError

views_bp = Blueprint("views", __name__)


def get_current_user():
    """Читает JWT из сессии и возвращает payload или None."""
    token = session.get("access_token")
    if not token:
        return None
    try:
        from flask import current_app
        data = decode_token(token)
        return data
    except Exception:
        return None


def login_required_view(fn):
    """Декоратор для HTML-страниц: редирект на /login если нет сессии."""
    from functools import wraps
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

        from app.models import User
        from app import db
        import bcrypt
        from flask_jwt_extended import create_access_token, create_refresh_token

        user = User.query.filter_by(username=username, is_active=True).first()
        dummy = b"$2b$12$AAAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        stored = user.password_hash.encode() if user else dummy
        valid  = bcrypt.checkpw(password.encode(), stored) and user is not None

        if valid:
            access  = create_access_token(
                identity=user.id,
                additional_claims={"role": user.role}
            )
            refresh = create_refresh_token(identity=user.id)
            session["access_token"]  = access
            session["refresh_token"] = refresh
            session["username"]      = user.username
            session["role"]          = user.role
            return redirect(url_for("views.dashboard"))
        else:
            error = "Неверный логин или пароль"

    return render_template("login.html", error=error)


@views_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("views.login"))


@views_bp.route("/dashboard")
@login_required_view
def dashboard():
    user = get_current_user()
    return render_template("dashboard.html",
                           active="dashboard",
                           username=session.get("username"),
                           role=session.get("role"))


@views_bp.route("/agents")
@login_required_view
def agents():
    return render_template("dashboard.html",
                           active="agents",
                           username=session.get("username"),
                           role=session.get("role"))


@views_bp.route("/agents/<agent_id>")
@login_required_view
def agent_detail(agent_id):
    return render_template("agent_detail.html",
                           agent_id=agent_id,
                           active="agents",
                           username=session.get("username"),
                           role=session.get("role"))


@views_bp.route("/logs")
@login_required_view
def logs():
    return render_template("logs.html",
                           active="logs",
                           username=session.get("username"),
                           role=session.get("role"))


@views_bp.route("/admin")
@login_required_view
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("views.dashboard"))
    return render_template("admin.html",
                           active="admin",
                           username=session.get("username"),
                           role=session.get("role"))

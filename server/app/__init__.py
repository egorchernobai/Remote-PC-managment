import logging

from flask import Flask
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sock import Sock
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address)
sock = Sock()


def create_app(config_class="app.config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    db.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)
    sock.init_app(app)
    app.extensions.setdefault("sock", sock)

    logging.basicConfig(
        format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
        level=logging.INFO,
    )

    from app.api.admin import admin_bp
    from app.api.agents import agents_bp
    from app.api.auth_routes import auth_bp
    from app.api.commands import commands_bp
    from app.api.files import files_bp
    from app.views import views_bp
    from app.websocket import register_ws

    app.register_blueprint(agents_bp, url_prefix="/api/v1/agents")
    app.register_blueprint(commands_bp, url_prefix="/api/v1/commands")
    app.register_blueprint(files_bp, url_prefix="/api/v1/files")
    app.register_blueprint(admin_bp, url_prefix="/api/v1/admin")
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(views_bp)
    register_ws(app)

    return app

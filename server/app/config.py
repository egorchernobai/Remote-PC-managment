import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost/rmm_dev",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    RATELIMIT_DEFAULT = "100/hour"
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024

    ALLOWED_COMMANDS = {
        "file_download",
        "file_upload",
        "process_kill",
        "process_list",
        "script",
        "service_list",
        "service_start",
        "service_stop",
        "shell",
        "sysinfo",
    }

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-windows-change-in-prod-abc123")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret-windows-change-in-prod-xyz789")
    FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", SECRET_KEY)

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))

    SERVER_CERT = os.environ.get(
        "SERVER_CERT",
        os.path.normpath(os.path.join(BASE_DIR, "..", "certs", "server.crt")),
    )
    SERVER_KEY = os.environ.get(
        "SERVER_KEY",
        os.path.normpath(os.path.join(BASE_DIR, "..", "certs", "server.key")),
    )
    AGENT_CA = os.environ.get(
        "AGENT_CA",
        os.path.normpath(os.path.join(BASE_DIR, "..", "certs", "ca.crt")),
    )
    AGENT_CERT_EXPORT_DIR = os.environ.get(
        "AGENT_CERT_EXPORT_DIR",
        os.path.normpath(os.path.join(PROJECT_ROOT, "agent", "certs")),
    )

    USE_TLS = os.environ.get("USE_TLS", "true")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin_Win_123!")
    UPLOAD_FOLDER = os.path.abspath(os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(PROJECT_ROOT, "uploads"),
    ))

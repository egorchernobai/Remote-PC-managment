import os
from datetime import timedelta

class Config:
    # SECRET_KEY = os.environ["FLASK_SECRET_KEY"]
    # JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
    # JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
    # JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///rmm.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # # TLS / mTLS
    # SERVER_CERT = os.environ.get("SERVER_CERT", "certs/server.crt")
    # SERVER_KEY  = os.environ.get("SERVER_KEY",  "certs/server.key")
    # AGENT_CA    = os.environ.get("AGENT_CA",    "certs/agent-ca.crt")  # для mTLS
    
    # Rate limiting
    RATELIMIT_DEFAULT = "100/hour"
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")
    
    # Безопасность файлов
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/var/rmm/uploads")
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB

    # Список разрешённых команд (whitelist режим)
    ALLOWED_COMMANDS = {"shell", "script", "process_list", "process_kill",
                        "service_list", "service_start", "service_stop",
                        "file_upload", "file_download", "sysinfo"}

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-windows-change-in-prod-abc123")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret-windows-change-in-prod-xyz789")

    # Optional compatibility alias for older config name
    FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", SECRET_KEY)

    # DATABASE_URL="sqlite:///rmm_dev.db"
    SERVER_CERT="..\certs\server.crt"
    SERVER_KEY="..\certs\server.key"
    AGENT_CA="..\certs\ca.crt"
    USE_TLS="true"
    ADMIN_PASSWORD="Admin_Win_123!"
    UPLOAD_FOLDER="C:\\rmm-project\\uploads"


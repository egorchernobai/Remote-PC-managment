# import os
# import ssl
# from app import create_app, db
# from app.models import User
# import bcrypt
# from dotenv import load_dotenv
# import os

# load_dotenv(os.path.join(os.path.dirname(__file__), "\\.env"))

# # print("FLASK_SECRET_KEY =", os.environ.get("FLASK_SECRET_KEY"))
# app = create_app()


# def init_db():
#     """Инициализация БД и создание первого admin-пользователя."""
#     with app.app_context():
#         db.create_all()

#         # Создаём admin только если пользователей нет
#         if not User.query.first():
#             raw_pw = os.environ.get("ADMIN_PASSWORD", "Admin_Win_123!")
#             pw_hash = bcrypt.hashpw(raw_pw.encode(), bcrypt.gensalt(12)).decode()
#             admin = User(username="admin", password_hash=pw_hash, role="admin")
#             db.session.add(admin)
#             db.session.commit()
#             print(f"[INIT] Created default admin user")
#             print(raw_pw)
#             if raw_pw == "ChangeMe_12345!":
#                 print("[WARN] Using default password — change it immediately!")


# if __name__ == "__main__":
#     init_db()

#     # use_tls = os.environ.get("USE_TLS", "false").lower() == "true"
#     use_tls = "true"

#     if use_tls:
#         context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
#         context.load_cert_chain(
#             certfile=app.config["SERVER_CERT"],
#             keyfile=app.config["SERVER_KEY"]
#         )
#         # mTLS: требуем клиентский сертификат от агентов
#         context.verify_mode = ssl.CERT_OPTIONAL
#         context.load_verify_locations(cafile=app.config["AGENT_CA"])

#         app.run(
#             host="0.0.0.0",
#             port=int(os.environ.get("PORT", 8443)),
#             ssl_context=context,
#             debug=False
#         )
#     else:
#         # Режим разработки без TLS
#         app.run(
#             host="127.0.0.1",
#             port=int(os.environ.get("PORT", 5000)),
#             debug=True
#         )


import os
import ssl
from app import create_app, db
from app.models import User
import bcrypt

app = create_app()


def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.first():
            raw_pw = os.environ.get("ADMIN_PASSWORD", "Admin_Win_123!")
            pw_hash = bcrypt.hashpw(raw_pw.encode(), bcrypt.gensalt(12)).decode()
            admin = User(username="admin", password_hash=pw_hash, role="admin")
            db.session.add(admin)
            db.session.commit()
            print("[INIT] Created default admin user")
            if raw_pw == "ChangeMe_12345!":
                print("[WARN] Using default password — change it immediately!")


if __name__ == "__main__":
    init_db()

    use_tls = os.environ.get("USE_TLS", "true").lower() == "true"

    if use_tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(
            certfile=app.config["SERVER_CERT"],
            keyfile=app.config["SERVER_KEY"]
        )
        # ✅ CERT_OPTIONAL вместо CERT_REQUIRED — браузер может подключаться без сертификата
        # Проверка клиентского сертификата агента делается в auth.py по fingerprint
        context.verify_mode = ssl.CERT_OPTIONAL
        context.load_verify_locations(cafile=app.config["AGENT_CA"])

        # Минимальная версия TLS 1.2
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        print(f"[TLS] Server cert: {app.config['SERVER_CERT']}")
        print(f"[TLS] Agent CA:    {app.config['AGENT_CA']}")

        app.run(
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8443)),
            ssl_context=context,
            debug=False
        )
    else:
        app.run(
            host="127.0.0.1",
            port=int(os.environ.get("PORT", 5000)),
            debug=True
        )

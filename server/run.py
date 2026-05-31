import os
import ssl

import bcrypt

from app import create_app, db
from app.cert_bootstrap import ensure_certificates
from app.models import User


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
                print("[WARN] Using default password - change it immediately")


def build_ssl_context():
    cert_info = ensure_certificates(app.config)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        certfile=app.config["SERVER_CERT"],
        keyfile=app.config["SERVER_KEY"],
    )
    context.verify_mode = ssl.CERT_OPTIONAL
    context.load_verify_locations(cafile=app.config["AGENT_CA"])
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    print(f"[TLS] Server cert: {app.config['SERVER_CERT']}")
    print(f"[TLS] Agent CA:    {app.config['AGENT_CA']}")
    print(f"[TLS] Server SANs: {', '.join(cert_info['hosts'])}")
    print(f"[TLS] Agent cert:  {cert_info['agent_cert']}")
    print(f"[TLS] Agent key:   {cert_info['agent_key']}")
    return context


if __name__ == "__main__":
    init_db()

    use_tls = os.environ.get("USE_TLS", "true").lower() == "true"
    ssl_context = build_ssl_context() if use_tls else None

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        ssl_context=ssl_context,
        debug=not use_tls,
    )

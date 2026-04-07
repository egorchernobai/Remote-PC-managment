from flask import request
from app.models import AuditLog
from app import db
import logging

logger = logging.getLogger("audit")

def log_action(actor_id: str, actor_type: str, action: str,
               target: str = None, details: dict = None):
    ip = request.remote_addr if request else None
    entry = AuditLog(
        actor_id=actor_id, actor_type=actor_type,
        action=action, target=target,
        details=details, ip_address=ip
    )
    db.session.add(entry)
    db.session.commit()
    logger.info(f"AUDIT | {actor_type}:{actor_id} | {action} | target={target}")

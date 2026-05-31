import logging

from flask import has_request_context, request

from app import db
from app.models import AuditLog


logger = logging.getLogger("audit")


def log_action(actor_id: str, actor_type: str, action: str, target: str = None, details: dict = None):
    entry = AuditLog(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        target=target,
        details=details,
        ip_address=request.remote_addr if has_request_context() else None,
    )
    db.session.add(entry)
    db.session.commit()
    logger.info("AUDIT | %s:%s | %s | target=%s", actor_type, actor_id, action, target)

import json
import logging
from datetime import datetime, timezone

from flask_sock import Sock

from app import db
from app.auth import verify_agent_token
from app.command_queue import register_listener, unregister_listener
from app.models import Agent, Command


logger = logging.getLogger("ws")


def register_ws(app):
    sock: Sock = app.extensions["sock"]

    @sock.route("/ws/agent")
    def agent_ws(ws):
        try:
            raw = ws.receive(timeout=10)
            auth = json.loads(raw)
        except Exception:
            ws.close(message="Auth timeout")
            return

        agent = verify_agent_token(auth.get("agent_id"), auth.get("token"))
        if not agent:
            ws.send(json.dumps({"type": "error", "msg": "Unauthorized"}))
            ws.close()
            return

        agent.status = "online"
        agent.last_seen = datetime.now(timezone.utc)
        db.session.commit()

        ws.send(json.dumps({"type": "auth_ok"}))
        logger.info("Agent connected: %s (%s)", agent.hostname, agent.id)

        def send_command(command_id: str):
            try:
                cmd = db.session.get(Command, command_id)
                if cmd:
                    ws.send(json.dumps({
                        "type": "execute",
                        "command_id": cmd.id,
                        "command": cmd.command,
                        "cmd_type": cmd.cmd_type,
                    }))
                    logger.info("Pushed command %s to agent %s", command_id, agent.id)
            except Exception as exc:
                logger.warning("Failed to push command %s: %s", command_id, exc)

        register_listener(agent.id, send_command)

        try:
            while True:
                msg = ws.receive(timeout=60)
                if msg is None:
                    break
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from agent %s", agent.id)
                    continue
                _handle_agent_message(agent, data)
        except Exception as exc:
            logger.warning("WS error for %s: %s", agent.id, exc)
        finally:
            unregister_listener(agent.id)
            agent.status = "offline"
            db.session.commit()
            logger.info("Agent disconnected: %s", agent.hostname)


def _handle_agent_message(agent: Agent, data: dict):
    msg_type = data.get("type")

    if msg_type == "sysinfo":
        agent.os_info = {**(agent.os_info or {}), **data.get("payload", {})}
        agent.last_seen = datetime.now(timezone.utc)
        db.session.commit()

    elif msg_type == "command_result":
        cmd_id = data.get("command_id")
        cmd = db.session.get(Command, cmd_id)
        if cmd and cmd.agent_id == agent.id:
            cmd.output = str(data.get("output", ""))[:65536]
            cmd.exit_code = int(data.get("exit_code", -1))
            cmd.status = "done" if cmd.exit_code == 0 else "failed"
            cmd.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.info("Command %s finished, exit=%s", cmd_id, cmd.exit_code)

    elif msg_type == "pong":
        agent.last_seen = datetime.now(timezone.utc)
        db.session.commit()

import json
import logging
from datetime import datetime, timezone

from flask_sock import Sock
from app.auth import verify_agent_token
from app.models import Agent
from app import db
from app.command_queue import register_listener, unregister_listener

logger = logging.getLogger("ws")


def register_ws(app):
    sock: Sock = app.extensions["sock"]

    @sock.route("/ws/agent")
    def agent_ws(ws):
        # Аутентификация по первому сообщению
        try:
            raw  = ws.receive(timeout=10)
            auth = json.loads(raw)
        except Exception:
            ws.close(message="Auth timeout")
            return

        agent = verify_agent_token(auth.get("agent_id"), auth.get("token"))
        if not agent:
            ws.send(json.dumps({"type": "error", "msg": "Unauthorized"}))
            ws.close()
            return

        agent.status   = "online"
        agent.last_seen = datetime.now(timezone.utc)
        db.session.commit()

        ws.send(json.dumps({"type": "auth_ok"}))
        logger.info(f"Agent connected: {agent.hostname} ({agent.id})")

        # ✅ Регистрируем callback — когда придёт команда, отправим её в WS
        def send_command(command_id: str):
            try:
                cmd = db.session.get(__import__('app.models', fromlist=['Command']).Command, command_id)
                if cmd:
                    ws.send(json.dumps({
                        "type":       "execute",
                        "command_id": cmd.id,
                        "command":    cmd.command,
                        "cmd_type":   cmd.cmd_type,
                    }))
                    logger.info(f"Pushed command {command_id} to agent {agent.id}")
            except Exception as e:
                logger.warning(f"Failed to push command {command_id}: {e}")

        register_listener(agent.id, send_command)

        try:
            while True:
                msg = ws.receive(timeout=60)
                if msg is None:
                    break
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from agent {agent.id}")
                    continue
                _handle_agent_message(agent, data)
        except Exception as e:
            logger.warning(f"WS error for {agent.id}: {e}")
        finally:
            unregister_listener(agent.id)
            agent.status = "offline"
            db.session.commit()
            logger.info(f"Agent disconnected: {agent.hostname}")


def _handle_agent_message(agent: Agent, data: dict):
    msg_type = data.get("type")

    if msg_type == "sysinfo":
        agent.os_info   = {**(agent.os_info or {}), **data.get("payload", {})}
        agent.last_seen = datetime.now(timezone.utc)
        db.session.commit()

    elif msg_type == "command_result":
        from app.models import Command
        cmd_id = data.get("command_id")
        cmd    = db.session.get(Command, cmd_id)
        if cmd and cmd.agent_id == agent.id:
            cmd.output       = str(data.get("output", ""))[:65536]
            cmd.exit_code    = int(data.get("exit_code", -1))
            cmd.status       = "done" if cmd.exit_code == 0 else "failed"
            cmd.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.info(f"Command {cmd_id} finished, exit={cmd.exit_code}")

    elif msg_type == "pong":
        agent.last_seen = datetime.now(timezone.utc)
        db.session.commit()

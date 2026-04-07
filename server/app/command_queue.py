import threading
import logging
from collections import defaultdict
from typing import Callable

logger = logging.getLogger("command_queue")

_queue:     dict[str, list[str]] = defaultdict(list)
_listeners: dict[str, Callable]  = {}
_lock = threading.Lock()


def push_command(agent_id: str, command_id: str) -> None:
    with _lock:
        _queue[agent_id].append(command_id)
        cb = _listeners.get(agent_id)

    if cb:
        try:
            cb(command_id)
            logger.info(f"Command {command_id} pushed via WS to agent {agent_id}")
        except Exception as e:
            logger.warning(f"WS push failed for {agent_id}: {e}")
    else:
        logger.info(f"Agent {agent_id} offline — command {command_id} queued for polling")


def pop_pending(agent_id: str) -> list[str]:
    with _lock:
        return _queue.pop(agent_id, [])


def register_listener(agent_id: str, callback: Callable) -> None:
    with _lock:
        _listeners[agent_id] = callback

        # ✅ Если есть накопившиеся команды — отправляем сразу
        pending = _queue.pop(agent_id, [])

    for cmd_id in pending:
        try:
            callback(cmd_id)
            logger.info(f"Flushed queued command {cmd_id} to agent {agent_id}")
        except Exception as e:
            logger.warning(f"Failed to flush {cmd_id}: {e}")


def unregister_listener(agent_id: str) -> None:
    with _lock:
        _listeners.pop(agent_id, None)

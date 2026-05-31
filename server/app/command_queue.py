import logging
import threading
from collections import defaultdict
from typing import Callable


logger = logging.getLogger("command_queue")

_queue: dict[str, list[str]] = defaultdict(list)
_listeners: dict[str, Callable] = {}
_lock = threading.Lock()


def push_command(agent_id: str, command_id: str) -> None:
    with _lock:
        _queue[agent_id].append(command_id)
        callback = _listeners.get(agent_id)

    if callback:
        try:
            callback(command_id)
            logger.info("Command %s pushed via WS to agent %s", command_id, agent_id)
        except Exception as exc:
            logger.warning("WS push failed for %s: %s", agent_id, exc)
    else:
        logger.info("Agent %s offline - command %s queued for polling", agent_id, command_id)


def pop_pending(agent_id: str) -> list[str]:
    with _lock:
        return _queue.pop(agent_id, [])


def register_listener(agent_id: str, callback: Callable) -> None:
    with _lock:
        _listeners[agent_id] = callback
        pending = _queue.pop(agent_id, [])

    for command_id in pending:
        try:
            callback(command_id)
            logger.info("Flushed queued command %s to agent %s", command_id, agent_id)
        except Exception as exc:
            logger.warning("Failed to flush %s: %s", command_id, exc)


def unregister_listener(agent_id: str) -> None:
    with _lock:
        _listeners.pop(agent_id, None)

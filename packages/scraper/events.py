import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_listeners: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)


def on(event: str, fn: Callable[[dict[str, Any]], None]) -> None:
    _listeners[event].append(fn)


def emit(event: str, payload: dict[str, Any]) -> None:
    for fn in _listeners.get(event, []):
        try:
            fn(payload)
        except Exception:
            logger.exception("event listener failed for %s", event)

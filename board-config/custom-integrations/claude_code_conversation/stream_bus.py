"""In-process broadcast of Claude answer progress to panel subscribers.

Модуль навмисно тримає підписників у власному словнику, а не на шині подій
Home Assistant: події з дельтами тексту були б видимі в журналі подій і
засмічували б його на кожен токен. Підписка доступна лише адміністраторам
через WebSocket-команду інтеграції.
"""

from collections.abc import Callable
from typing import Any

_SUBSCRIBERS: dict[str, set[Callable[[dict[str, Any]], None]]] = {}


def subscribe(
    conversation_id: str, callback: Callable[[dict[str, Any]], None]
) -> Callable[[], None]:
    """Register a listener for one conversation and return its unsubscribe."""
    listeners = _SUBSCRIBERS.setdefault(conversation_id, set())
    listeners.add(callback)

    def _unsubscribe() -> None:
        listeners.discard(callback)
        if not listeners:
            _SUBSCRIBERS.pop(conversation_id, None)

    return _unsubscribe


def broadcast(conversation_id: str | None, event: dict[str, Any]) -> None:
    """Send an event to every subscriber of the conversation, never raising."""
    if not conversation_id:
        return
    for callback in tuple(_SUBSCRIBERS.get(conversation_id, ())):
        try:
            callback(event)
        except Exception:  # noqa: BLE001 - one dead client must not stop others
            pass

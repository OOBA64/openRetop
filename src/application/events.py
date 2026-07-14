"""Typed synchronous events for the V3 application layer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from itertools import count
from types import MappingProxyType
from typing import Generic, TypeVar

from application.selection import SelectionSnapshot


def _readonly_metadata(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


class ApplicationEvent:
    """Marker base for events published within the application process."""


@dataclass(frozen=True, slots=True)
class StateChangedEvent(ApplicationEvent):
    reason: str
    changed_fields: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _readonly_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class SelectionChangedEvent(ApplicationEvent):
    selection: SelectionSnapshot
    reason: str = "selection_changed"


@dataclass(frozen=True, slots=True)
class SceneChangedEvent(ApplicationEvent):
    reason: str
    object_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DirtyChangedEvent(ApplicationEvent):
    dirty: bool


class CommandPhase(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class CommandEvent(ApplicationEvent):
    command_id: str
    phase: CommandPhase
    action_id: str | None = None
    success: bool | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActiveToolChangedEvent(ApplicationEvent):
    tool_id: str | None
    previous_tool_id: str | None = None


class StatusLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class StatusEvent(ApplicationEvent):
    message: str
    level: StatusLevel = StatusLevel.INFO


EventT = TypeVar("EventT", bound=ApplicationEvent)


class Subscription(Generic[EventT]):
    """Idempotently removable event subscription."""

    def __init__(
        self,
        publisher: EventPublisher,
        event_type: type[EventT],
        token: int,
    ) -> None:
        self._publisher = publisher
        self._event_type = event_type
        self._token = token
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    def cancel(self) -> None:
        if not self._active:
            return
        self._publisher._unsubscribe(self._event_type, self._token)
        self._active = False


class EventPublisher:
    """Small typed publisher; delivery is synchronous and registration ordered."""

    def __init__(self) -> None:
        self._subscribers: dict[
            type[ApplicationEvent], dict[int, Callable[[ApplicationEvent], None]]
        ] = {}
        self._tokens = count(1)

    def subscribe(
        self,
        event_type: type[EventT],
        callback: Callable[[EventT], None],
    ) -> Subscription[EventT]:
        if not isinstance(event_type, type) or not issubclass(
            event_type, ApplicationEvent
        ):
            raise TypeError("event_type must be an ApplicationEvent type.")
        if not callable(callback):
            raise TypeError("callback must be callable.")
        token = next(self._tokens)
        callbacks = self._subscribers.setdefault(event_type, {})
        callbacks[token] = callback  # type: ignore[assignment]
        return Subscription(self, event_type, token)

    def publish(self, event: EventT) -> EventT:
        if not isinstance(event, ApplicationEvent):
            raise TypeError("event must derive from ApplicationEvent.")
        callbacks: list[tuple[int, Callable[[ApplicationEvent], None]]] = []
        for event_type, registered in tuple(self._subscribers.items()):
            if isinstance(event, event_type):
                callbacks.extend(tuple(registered.items()))
        for _token, callback in sorted(callbacks, key=lambda item: item[0]):
            callback(event)
        return event

    def _unsubscribe(self, event_type: type[ApplicationEvent], token: int) -> None:
        callbacks = self._subscribers.get(event_type)
        if callbacks is None:
            return
        callbacks.pop(token, None)
        if not callbacks:
            self._subscribers.pop(event_type, None)

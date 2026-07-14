"""Command protocol and dispatcher for the UI-agnostic application layer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from application.dependencies import ApplicationDependencies
from application.events import CommandEvent, CommandPhase
from application.results import CommandResult


_COMMAND_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")


@runtime_checkable
class Command(Protocol):
    command_id: str
    action_id: str | None
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class CommandRequest:
    command_id: str
    action_id: str | None = None
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if _COMMAND_ID_PATTERN.fullmatch(self.command_id) is None:
            raise ValueError("command_id must be a stable lower-case dotted identifier.")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class CommandRejected(RuntimeError):
    """Expected command rejection that should become a structured failure."""


CommandHandler = Callable[[Command, ApplicationDependencies], CommandResult]


class CommandDispatcher:
    """Instance-scoped command router with explicit injected dependencies."""

    def __init__(self, dependencies: ApplicationDependencies) -> None:
        if not isinstance(dependencies, ApplicationDependencies):
            raise TypeError("dependencies must be ApplicationDependencies.")
        self._dependencies = dependencies
        self._handlers: dict[str, CommandHandler] = {}

    @property
    def dependencies(self) -> ApplicationDependencies:
        return self._dependencies

    @property
    def handler_ids(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def register(self, command_id: str, handler: CommandHandler) -> None:
        normalized_id = str(command_id)
        if _COMMAND_ID_PATTERN.fullmatch(normalized_id) is None:
            raise ValueError("command_id must be a stable lower-case dotted identifier.")
        if not callable(handler):
            raise TypeError("handler must be callable.")
        if normalized_id in self._handlers:
            raise ValueError(f"Command handler is already registered: {normalized_id}")
        self._handlers[normalized_id] = handler

    def dispatch(self, command: Command) -> CommandResult:
        if not isinstance(command, Command):
            raise TypeError("command must implement the Command protocol.")
        self._dependencies.events.publish(
            CommandEvent(
                command_id=command.command_id,
                action_id=command.action_id,
                phase=CommandPhase.STARTED,
            )
        )
        handler = self._handlers.get(command.command_id)
        if handler is None:
            result = CommandResult.failure(
                f"No handler is registered for command '{command.command_id}'."
            )
            self._publish_completed(command, result)
            return result

        try:
            result = handler(command, self._dependencies)
        except CommandRejected as exc:
            result = CommandResult.failure(str(exc))
        except Exception as exc:
            self._dependencies.events.publish(
                CommandEvent(
                    command_id=command.command_id,
                    action_id=command.action_id,
                    phase=CommandPhase.COMPLETED,
                    success=False,
                    errors=(f"{type(exc).__name__}: {exc}",),
                )
            )
            raise

        if not isinstance(result, CommandResult):
            error = TypeError("Command handlers must return CommandResult.")
            self._dependencies.events.publish(
                CommandEvent(
                    command_id=command.command_id,
                    action_id=command.action_id,
                    phase=CommandPhase.COMPLETED,
                    success=False,
                    errors=(str(error),),
                )
            )
            raise error
        self._publish_completed(command, result)
        return result

    def _publish_completed(self, command: Command, result: CommandResult) -> None:
        self._dependencies.events.publish(
            CommandEvent(
                command_id=command.command_id,
                action_id=command.action_id,
                phase=CommandPhase.COMPLETED,
                success=result.success,
                errors=result.errors,
            )
        )

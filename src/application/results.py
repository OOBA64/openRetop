"""Structured, presentation-neutral command results and requests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import math
from types import MappingProxyType
from typing import Protocol, runtime_checkable


Vector3 = tuple[float, float, float]


@runtime_checkable
class UndoPayload(Protocol):
    """Undo entry contract accepted by application results."""

    name: str

    def undo(self) -> None:
        """Restore the state before the operation."""

    def redo(self) -> None:
        """Reapply the operation."""


class ViewportRequestKind(str, Enum):
    REFRESH = "refresh"
    FRAME_ALL = "frame_all"
    FRAME_BOUNDS = "frame_bounds"
    RENDER = "render"


@dataclass(frozen=True, slots=True)
class ViewportRequest:
    kind: ViewportRequestKind
    minimum_bound: Vector3 | None = None
    maximum_bound: Vector3 | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        has_minimum = self.minimum_bound is not None
        has_maximum = self.maximum_bound is not None
        if has_minimum != has_maximum:
            raise ValueError("Viewport bounds require both minimum and maximum values.")
        if self.kind is ViewportRequestKind.FRAME_BOUNDS and not has_minimum:
            raise ValueError("FRAME_BOUNDS requires finite minimum and maximum bounds.")
        for bound in (self.minimum_bound, self.maximum_bound):
            if bound is None:
                continue
            if len(bound) != 3 or not all(
                math.isfinite(float(value)) for value in bound
            ):
                raise ValueError("Viewport bounds must contain three finite values.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @classmethod
    def frame_all(cls) -> ViewportRequest:
        return cls(ViewportRequestKind.FRAME_ALL)

    @classmethod
    def frame_bounds(
        cls,
        minimum_bound: Vector3,
        maximum_bound: Vector3,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> ViewportRequest:
        return cls(
            ViewportRequestKind.FRAME_BOUNDS,
            tuple(float(value) for value in minimum_bound),  # type: ignore[arg-type]
            tuple(float(value) for value in maximum_bound),  # type: ignore[arg-type]
            metadata or {},
        )


class UIRequestKind(str, Enum):
    REFRESH_ACTIONS = "refresh_actions"
    REFRESH_SCENE_BROWSER = "refresh_scene_browser"
    SYNC_WORKFLOW = "sync_workflow"


@dataclass(frozen=True, slots=True)
class UIRequest:
    kind: UIRequestKind
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Complete outcome of an application command."""

    success: bool = True
    status: str = ""
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    changed: bool = False
    dirty: bool = False
    viewport_requests: tuple[ViewportRequest, ...] = ()
    ui_requests: tuple[UIRequest, ...] = ()
    undo_payload: UndoPayload | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        object.__setattr__(self, "errors", tuple(str(item) for item in self.errors))
        object.__setattr__(self, "viewport_requests", tuple(self.viewport_requests))
        object.__setattr__(self, "ui_requests", tuple(self.ui_requests))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        if self.success and self.errors:
            raise ValueError("A successful CommandResult cannot contain errors.")

    @classmethod
    def ok(
        cls,
        *,
        status: str = "",
        changed: bool = False,
        dirty: bool = False,
        warnings: tuple[str, ...] = (),
        viewport_requests: tuple[ViewportRequest, ...] = (),
        ui_requests: tuple[UIRequest, ...] = (),
        undo_payload: UndoPayload | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> CommandResult:
        return cls(
            success=True,
            status=status,
            changed=changed,
            dirty=dirty,
            warnings=warnings,
            viewport_requests=viewport_requests,
            ui_requests=ui_requests,
            undo_payload=undo_payload,
            metadata=metadata or {},
        )

    @classmethod
    def failure(
        cls,
        *errors: str,
        status: str = "",
        warnings: tuple[str, ...] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> CommandResult:
        normalized_errors = tuple(str(item) for item in errors if str(item))
        if not normalized_errors:
            normalized_errors = ("Command failed.",)
        return cls(
            success=False,
            status=status,
            warnings=warnings,
            errors=normalized_errors,
            metadata=metadata or {},
        )

"""Stable action definitions and the initial V3 action registry.

Actions describe user intent. They deliberately do not contain Tk callbacks or
VTK operations; presentation adapters resolve an action to its command ID.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from types import MappingProxyType
from typing import Iterable, Mapping


_STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")


class ActionCondition(str, Enum):
    """Named, UI-independent conditions used by registered actions."""

    ALWAYS = "always"
    HAS_SCENE_OBJECTS = "has_scene_objects"
    HAS_SCENE_SELECTION = "has_scene_selection"
    CAN_UNDO = "can_undo"
    CAN_REDO = "can_redo"


@dataclass(frozen=True, slots=True)
class ActionContext:
    """Typed state used to evaluate action availability."""

    has_scene_objects: bool = False
    has_scene_selection: bool = False
    can_undo: bool = False
    can_redo: bool = False

    def satisfies(self, condition: ActionCondition) -> bool:
        if condition is ActionCondition.ALWAYS:
            return True
        if condition is ActionCondition.HAS_SCENE_OBJECTS:
            return self.has_scene_objects
        if condition is ActionCondition.HAS_SCENE_SELECTION:
            return self.has_scene_selection
        if condition is ActionCondition.CAN_UNDO:
            return self.can_undo
        if condition is ActionCondition.CAN_REDO:
            return self.can_redo
        raise ValueError(f"Unsupported action condition: {condition!r}")


@dataclass(frozen=True, slots=True)
class ActionState:
    """Resolved presentation state for an action."""

    enabled: bool = True
    visible: bool = True
    checked: bool = False


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Authoritative, stable description of one user-facing action."""

    id: str
    label: str
    description: str
    category: str
    shortcut: str | None
    command_id: str
    enabled_when: tuple[ActionCondition, ...] = (ActionCondition.ALWAYS,)
    visible_when: tuple[ActionCondition, ...] = (ActionCondition.ALWAYS,)
    checkable: bool = False
    checked_when: ActionCondition | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("id", "label", "description", "category", "command_id"):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"ActionDefinition.{field_name} must not be empty.")
        if _STABLE_ID_PATTERN.fullmatch(self.id) is None:
            raise ValueError(
                "ActionDefinition.id must be a stable lower-case dotted identifier."
            )
        if _STABLE_ID_PATTERN.fullmatch(self.command_id) is None:
            raise ValueError(
                "ActionDefinition.command_id must be a stable lower-case dotted identifier."
            )
        if not self.enabled_when:
            raise ValueError("ActionDefinition.enabled_when must contain a condition.")
        if not self.visible_when:
            raise ValueError("ActionDefinition.visible_when must contain a condition.")
        if self.checked_when is not None and not self.checkable:
            raise ValueError("checked_when requires checkable=True.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def action_id(self) -> str:
        """Compatibility spelling for callers that prefer an explicit name."""

        return self.id

    def resolve(self, context: ActionContext) -> ActionState:
        return ActionState(
            enabled=all(context.satisfies(item) for item in self.enabled_when),
            visible=all(context.satisfies(item) for item in self.visible_when),
            checked=(
                context.satisfies(self.checked_when)
                if self.checkable and self.checked_when is not None
                else False
            ),
        )


class ActionRegistry:
    """Ordered registry that rejects unstable or duplicate action contracts."""

    def __init__(self, actions: Iterable[ActionDefinition] = ()) -> None:
        self._actions: dict[str, ActionDefinition] = {}
        for action in actions:
            self.register(action)

    def register(self, action: ActionDefinition) -> None:
        if not isinstance(action, ActionDefinition):
            raise TypeError("action must be an ActionDefinition.")
        if action.id in self._actions:
            raise ValueError(f"Action ID is already registered: {action.id}")
        self._actions[action.id] = action

    def get(self, action_id: str) -> ActionDefinition | None:
        return self._actions.get(str(action_id))

    def require(self, action_id: str) -> ActionDefinition:
        action = self.get(action_id)
        if action is None:
            raise KeyError(f"Unknown action ID: {action_id}")
        return action

    def state(self, action_id: str, context: ActionContext) -> ActionState:
        return self.require(action_id).resolve(context)

    @property
    def definitions(self) -> tuple[ActionDefinition, ...]:
        return tuple(self._actions.values())

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._actions)


ACTION_FRAME_ALL = "view.frame_all"
ACTION_FRAME_SELECTED = "view.frame_selected"
ACTION_SHOW_ALL = "scene.show_all"
ACTION_TOGGLE_VISIBILITY = "scene.toggle_visibility"
ACTION_UNDO = "edit.undo"
ACTION_REDO = "edit.redo"


REPRESENTATIVE_ACTIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition(
        id=ACTION_FRAME_ALL,
        label="Frame All",
        description="Frame the visible scene in the viewport.",
        category="View",
        shortcut=None,
        command_id="viewport.frame_all",
        metadata={"legacy_handler": "frame_all", "migration_task": 75},
    ),
    ActionDefinition(
        id=ACTION_FRAME_SELECTED,
        label="Frame Selected",
        description="Frame the current scene selection in the viewport.",
        category="View",
        shortcut="F",
        command_id="viewport.frame_selected",
        enabled_when=(ActionCondition.HAS_SCENE_SELECTION,),
        metadata={"legacy_handler": "frame_selected", "migration_task": 75},
    ),
    ActionDefinition(
        id=ACTION_SHOW_ALL,
        label="Show All",
        description="Make all persistent scene objects visible.",
        category="Scene",
        shortcut="Alt+H",
        command_id="scene.show_all",
        enabled_when=(ActionCondition.HAS_SCENE_OBJECTS,),
        metadata={"legacy_handler": "show_all_scene_objects", "migration_task": 75},
    ),
    ActionDefinition(
        id=ACTION_TOGGLE_VISIBILITY,
        label="Toggle Visibility",
        description="Toggle visibility for the current scene selection.",
        category="Scene",
        shortcut="H",
        command_id="scene.toggle_visibility",
        enabled_when=(ActionCondition.HAS_SCENE_SELECTION,),
        metadata={
            "legacy_handler": "toggle_selected_scene_objects",
            "migration_task": 75,
        },
    ),
    ActionDefinition(
        id=ACTION_UNDO,
        label="Undo",
        description="Undo the most recent undoable scene edit.",
        category="Edit",
        shortcut="Ctrl+Z",
        command_id="history.undo",
        enabled_when=(ActionCondition.CAN_UNDO,),
        metadata={"legacy_handler": "undo", "migration_task": 75},
    ),
    ActionDefinition(
        id=ACTION_REDO,
        label="Redo",
        description="Redo the most recently undone scene edit.",
        category="Edit",
        shortcut="Ctrl+Y",
        command_id="history.redo",
        enabled_when=(ActionCondition.CAN_REDO,),
        metadata={"legacy_handler": "redo", "migration_task": 75},
    ),
)


def create_core_action_registry() -> ActionRegistry:
    """Return a fresh registry containing the Task 75 representative slice."""

    return ActionRegistry(REPRESENTATIVE_ACTIONS)

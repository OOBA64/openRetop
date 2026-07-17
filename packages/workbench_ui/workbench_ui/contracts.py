"""Headless contracts backing the PySide6 workbench widgets."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Iterable, Mapping, Sequence


ActionCallback = Callable[[Mapping[str, object]], object]


@dataclass
class ActionDefinition:
    id: str
    label: str
    category: str = "General"
    description: str = ""
    icon_key: str | None = None
    shortcut: str | None = None
    enabled: bool = True
    visible: bool = True
    checkable: bool = False
    checked: bool = False
    dispatch: ActionCallback | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or self.id.strip() != self.id:
            raise ValueError("Action IDs must be non-empty and trimmed.")
        if not self.label:
            raise ValueError("Action labels must be non-empty.")


class ActionRegistry:
    def __init__(self, definitions: Iterable[ActionDefinition] = ()) -> None:
        self._definitions: dict[str, ActionDefinition] = {}
        self._listeners: list[Callable[[ActionDefinition], None]] = []
        for definition in definitions:
            self.register(definition)

    @property
    def definitions(self) -> tuple[ActionDefinition, ...]:
        return tuple(self._definitions.values())

    def register(self, definition: ActionDefinition) -> ActionDefinition:
        if definition.id in self._definitions:
            raise ValueError(f"Action already registered: {definition.id}")
        self._definitions[definition.id] = definition
        return definition

    def shortcut_conflicts(self) -> dict[str, tuple[str, ...]]:
        """Return duplicate shortcuts without assuming contextual actions conflict."""

        owners: dict[str, list[str]] = {}
        for definition in self._definitions.values():
            shortcut = (definition.shortcut or "").strip().casefold()
            if shortcut:
                owners.setdefault(shortcut, []).append(definition.id)
        return {
            shortcut: tuple(action_ids)
            for shortcut, action_ids in owners.items()
            if len(action_ids) > 1
        }

    def require(self, action_id: str) -> ActionDefinition:
        try:
            return self._definitions[action_id]
        except KeyError as exc:
            raise KeyError(f"Unknown action: {action_id}") from exc

    def subscribe(self, listener: Callable[[ActionDefinition], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def cancel() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return cancel

    def update(self, action_id: str, **changes: object) -> ActionDefinition:
        definition = self.require(action_id)
        for field_name, value in changes.items():
            if field_name not in {"enabled", "visible", "checked", "label", "shortcut"}:
                raise ValueError(f"Unsupported action state field: {field_name}")
            setattr(definition, field_name, value)
        for listener in tuple(self._listeners):
            listener(definition)
        return definition

    def invoke(self, action_id: str, payload: Mapping[str, object] | None = None) -> object:
        definition = self.require(action_id)
        if not definition.visible or not definition.enabled:
            return False
        if definition.dispatch is None:
            return None
        result = definition.dispatch(payload or {})
        if definition.checkable and isinstance(result, bool):
            definition.checked = result
        return result


@dataclass(frozen=True)
class MenuItem:
    action_id: str | None = None
    title: str | None = None
    separator: bool = False
    children: tuple["MenuItem", ...] = ()


@dataclass(frozen=True)
class MenuSchema:
    title: str
    items: tuple[MenuItem, ...]


@dataclass(frozen=True)
class ToolbarItem:
    action_id: str


@dataclass(frozen=True)
class ToolbarSchema:
    title: str
    items: tuple[ToolbarItem, ...]


@dataclass(frozen=True)
class PanelDescriptor:
    id: str
    title: str
    area: str = "right"
    closable: bool = True
    floatable: bool = True
    visible: bool = True


class PanelRegistry:
    def __init__(self) -> None:
        self._panels: dict[str, PanelDescriptor] = {}

    def register(self, descriptor: PanelDescriptor) -> PanelDescriptor:
        if descriptor.id in self._panels:
            raise ValueError(f"Panel already registered: {descriptor.id}")
        self._panels[descriptor.id] = descriptor
        return descriptor

    def require(self, panel_id: str) -> PanelDescriptor:
        try:
            return self._panels[panel_id]
        except KeyError as exc:
            raise KeyError(f"Unknown panel: {panel_id}") from exc

    @property
    def descriptors(self) -> tuple[PanelDescriptor, ...]:
        return tuple(self._panels.values())


class DockLayoutManager:
    """Stores opaque toolkit layout bytes and recovers from corrupt state."""

    def __init__(self, *, schema_version: int = 1) -> None:
        self.schema_version = int(schema_version)
        self._state: bytes = b""

    def save(self, state: bytes | bytearray | memoryview) -> bytes:
        self._state = bytes(state)
        return self._state

    def restore(self, state: bytes | bytearray | memoryview | None) -> bool:
        if state is None:
            self._state = b""
            return False
        try:
            self._state = bytes(state)
        except (TypeError, ValueError):
            self._state = b""
            return False
        return bool(self._state)

    def reset(self) -> None:
        self._state = b""

    @property
    def state(self) -> bytes:
        return self._state


@dataclass(frozen=True)
class SelectionContext:
    ids: tuple[str, ...] = ()
    primary_id: str | None = None
    kind: str | None = None

    @property
    def has_selection(self) -> bool:
        return bool(self.ids)


@dataclass(frozen=True)
class ToolState:
    id: str | None = None
    phase: str = "inactive"
    instructions: str = ""
    payload: Mapping[str, object] = field(default_factory=dict)


class ToolModeManager:
    def __init__(self) -> None:
        self.state = ToolState()
        self._listeners: list[Callable[[ToolState], None]] = []

    def subscribe(self, listener: Callable[[ToolState], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def cancel() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return cancel

    def _set(self, state: ToolState) -> ToolState:
        self.state = state
        for listener in tuple(self._listeners):
            listener(state)
        return state

    def enter(self, tool_id: str, instructions: str = "", **payload: object) -> ToolState:
        if not tool_id:
            raise ValueError("tool_id is required")
        return self._set(ToolState(tool_id, "active", instructions, dict(payload)))

    @property
    def active(self) -> bool:
        return self.state.id is not None and self.state.phase not in {"inactive", "finished"}

    def set_phase(self, phase: str, instructions: str | None = None) -> ToolState:
        return self._set(
            ToolState(
                self.state.id,
                str(phase),
                self.state.instructions if instructions is None else instructions,
                self.state.payload,
            )
        )

    def apply(self) -> ToolState:
        if not self.active:
            raise RuntimeError("No active tool can be applied.")
        return self.set_phase("applied")

    def finish(self) -> ToolState:
        if not self.active:
            return self.state
        return self._set(ToolState(self.state.id, "finished", "", self.state.payload))

    def cancel(self) -> ToolState:
        return self._set(ToolState())


@dataclass(frozen=True)
class FieldDefinition:
    id: str
    label: str
    value: object = None
    editor: str = "text"
    validator: Callable[[object], str | None] | None = None
    advanced: bool = False
    group: str = "General"
    options: tuple[object, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    decimals: int = 3
    read_only: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or self.id.strip() != self.id:
            raise ValueError("Field IDs must be non-empty and trimmed.")
        if self.editor not in {
            "text", "number", "slider", "checkbox", "combo", "color", "vector", "readonly"
        }:
            raise ValueError(f"Unsupported property editor: {self.editor}")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Field minimum cannot exceed maximum.")


class PropertyInspectorModel:
    def __init__(self, fields: Iterable[FieldDefinition] = (), *, mode: str = "live") -> None:
        if mode not in {"live", "apply"}:
            raise ValueError("Inspector mode must be 'live' or 'apply'.")
        self.mode = mode
        self._fields: dict[str, FieldDefinition] = {}
        self._pending: dict[str, object] = {}
        self.replace(fields)

    @property
    def fields(self) -> tuple[FieldDefinition, ...]:
        return tuple(self._fields.values())

    @property
    def pending(self) -> Mapping[str, object]:
        return dict(self._pending)

    def replace(self, fields: Iterable[FieldDefinition]) -> None:
        values = list(fields)
        ids = [item.id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("Property field IDs must be unique.")
        self._fields = {item.id: item for item in values}
        self._pending.clear()

    def set_value(self, field_id: str, value: object, *, commit: bool | None = None) -> None:
        field = self._fields[field_id]
        if field.read_only or field.editor == "readonly":
            raise ValueError("Read-only properties cannot be changed.")
        if field.validator is not None:
            message = field.validator(value)
            if message:
                raise ValueError(message)
        should_commit = self.mode == "live" if commit is None else bool(commit)
        if not should_commit:
            self._pending[field_id] = value
            return
        self._fields[field_id] = _field_with_value(field, value)
        self._pending.pop(field_id, None)

    def apply(self) -> Mapping[str, object]:
        applied = dict(self._pending)
        for field_id, value in applied.items():
            self._fields[field_id] = _field_with_value(self._fields[field_id], value)
        self._pending.clear()
        return applied

    def cancel(self) -> None:
        self._pending.clear()

    def value(self, field_id: str) -> object:
        return self._pending.get(field_id, self._fields[field_id].value)


def _field_with_value(field: FieldDefinition, value: object) -> FieldDefinition:
    return FieldDefinition(
        id=field.id,
        label=field.label,
        value=value,
        editor=field.editor,
        validator=field.validator,
        advanced=field.advanced,
        group=field.group,
        options=field.options,
        minimum=field.minimum,
        maximum=field.maximum,
        step=field.step,
        decimals=field.decimals,
        read_only=field.read_only,
        metadata=field.metadata,
    )


@dataclass
class SceneNode:
    id: str
    label: str
    kind: str = "object"
    parent_id: str | None = None
    visible: bool = True
    selectable: bool = True
    renameable: bool = True
    reorderable: bool = False
    checkable: bool = True
    metadata: dict[str, object] = field(default_factory=dict)


class SceneTreeModel:
    def __init__(self, nodes: Iterable[SceneNode] = ()) -> None:
        self.nodes: dict[str, SceneNode] = {}
        self.selected_ids: tuple[str, ...] = ()
        self.replace(nodes)

    def replace(self, nodes: Iterable[SceneNode]) -> None:
        values = list(nodes)
        ids = [node.id for node in values]
        if len(set(ids)) != len(ids):
            raise ValueError("Scene node IDs must be unique.")
        self.nodes = {node.id: node for node in values}
        self.selected_ids = tuple(item for item in self.selected_ids if item in self.nodes)

    def children(self, parent_id: str | None = None) -> tuple[SceneNode, ...]:
        return tuple(node for node in self.nodes.values() if node.parent_id == parent_id)

    def select(self, ids: Iterable[str]) -> SelectionContext:
        self.selected_ids = tuple(dict.fromkeys(item for item in ids if item in self.nodes))
        return SelectionContext(self.selected_ids, self.selected_ids[0] if self.selected_ids else None)

    def set_visible(self, node_id: str, visible: bool) -> None:
        self.nodes[node_id].visible = bool(visible)

    def rename(self, node_id: str, label: str) -> None:
        node = self.nodes[node_id]
        if not node.renameable:
            raise ValueError("Scene node cannot be renamed.")
        normalized = str(label).strip()
        if not normalized:
            raise ValueError("Scene node name cannot be empty.")
        node.label = normalized

    def remove(self, node_ids: Iterable[str]) -> tuple[str, ...]:
        requested = set(str(item) for item in node_ids)
        removed: list[str] = []
        while requested:
            node_id = requested.pop()
            if node_id not in self.nodes:
                continue
            requested.update(child.id for child in self.children(node_id))
            removed.append(node_id)
            del self.nodes[node_id]
        self.selected_ids = tuple(item for item in self.selected_ids if item in self.nodes)
        return tuple(removed)

    def reorder(self, node_id: str, before_id: str | None) -> None:
        node = self.nodes[node_id]
        if not node.reorderable:
            raise ValueError("Scene node cannot be reordered.")
        if before_id is not None:
            before = self.nodes[before_id]
            if before.parent_id != node.parent_id:
                raise ValueError("Scene nodes can only be reordered within one parent.")
        ordered = list(self.nodes.values())
        ordered.remove(node)
        index = len(ordered) if before_id is None else ordered.index(self.nodes[before_id])
        ordered.insert(index, node)
        self.nodes = {item.id: item for item in ordered}


class CommandPalette:
    def __init__(self, registry: ActionRegistry) -> None:
        self.registry = registry

    def search(self, query: str) -> tuple[ActionDefinition, ...]:
        needle = str(query).strip().casefold()
        candidates = [item for item in self.registry.definitions if item.visible and item.enabled]
        if not needle:
            return tuple(candidates)
        return tuple(
            item
            for item in candidates
            if needle in item.label.casefold()
            or needle in item.id.casefold()
            or needle in item.description.casefold()
        )


@dataclass(frozen=True)
class Theme:
    name: str
    colors: Mapping[str, str]
    spacing: Mapping[str, int] = field(default_factory=lambda: {"small": 4, "medium": 8, "large": 16})
    typography: Mapping[str, str] = field(default_factory=lambda: {"body": "9pt", "heading": "10pt"})
    icons: Mapping[str, str] = field(default_factory=dict)


class ThemeManager:
    def __init__(self, theme: Theme | None = None) -> None:
        self.theme = theme or Theme(
            "dark",
            {"window": "#202225", "panel": "#2b2d31", "text": "#f2f3f5", "accent": "#00d1ff"},
        )

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme

    @staticmethod
    def built_in(name: str) -> Theme:
        normalized = str(name).strip().casefold()
        if normalized == "light":
            return Theme(
                "light",
                {"window": "#f3f4f6", "panel": "#ffffff", "text": "#17191c", "accent": "#0078d4"},
            )
        if normalized == "dark":
            return Theme(
                "dark",
                {"window": "#202225", "panel": "#2b2d31", "text": "#f2f3f5", "accent": "#00d1ff"},
            )
        raise ValueError(f"Unknown built-in theme: {name}")

    def stylesheet(self) -> str:
        colors = self.theme.colors
        return (
            "QMainWindow, QWidget {"
            f"background-color: {colors.get('window', '#202225')};"
            f"color: {colors.get('text', '#f2f3f5')};"
            "} QDockWidget, QMenu, QToolBar {"
            f"background-color: {colors.get('panel', '#2b2d31')};"
            "} QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
            f"selection-background-color: {colors.get('accent', '#00d1ff')};"
            "}"
        )


@dataclass
class FrameworkSettings:
    version: int = 1
    theme: str = "dark"
    layout_state: bytes = b""
    future: dict[str, object] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {"version": self.version, "theme": self.theme, "layout_state": self.layout_state.hex(), "future": self.future},
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, value: str) -> "FrameworkSettings":
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError("Framework settings must be an object.")
        version = int(data.get("version", 1))
        if version < 1:
            raise ValueError("Unsupported framework settings version.")
        future = data.get("future", {})
        if not isinstance(future, dict):
            raise ValueError("Framework settings future data must be an object.")
        try:
            layout_state = bytes.fromhex(str(data.get("layout_state", "")))
        except ValueError as exc:
            raise ValueError("Framework layout state is corrupt.") from exc
        return cls(
            version=version,
            theme=str(data.get("theme", "dark")),
            layout_state=layout_state,
            future=dict(future),
        )

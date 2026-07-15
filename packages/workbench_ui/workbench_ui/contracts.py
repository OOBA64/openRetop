"""Headless contracts backing the PySide6 workbench widgets."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Iterable, Mapping


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
        return self._panels[panel_id]

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
        return self.set_phase("applied")

    def finish(self) -> ToolState:
        return self.set_phase("finished")

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


class PropertyInspectorModel:
    def __init__(self, fields: Iterable[FieldDefinition] = ()) -> None:
        self._fields = {field.id: field for field in fields}

    @property
    def fields(self) -> tuple[FieldDefinition, ...]:
        return tuple(self._fields.values())

    def set_value(self, field_id: str, value: object) -> None:
        field = self._fields[field_id]
        if field.validator is not None:
            message = field.validator(value)
            if message:
                raise ValueError(message)
        self._fields[field_id] = FieldDefinition(
            field.id,
            field.label,
            value,
            field.editor,
            field.validator,
            field.advanced,
        )

    def value(self, field_id: str) -> object:
        return self._fields[field_id].value


@dataclass
class SceneNode:
    id: str
    label: str
    kind: str = "object"
    parent_id: str | None = None
    visible: bool = True
    selectable: bool = True
    renameable: bool = True
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
        return cls(
            version=int(data.get("version", 1)),
            theme=str(data.get("theme", "dark")),
            layout_state=bytes.fromhex(str(data.get("layout_state", ""))),
            future=dict(data.get("future", {})),
        )

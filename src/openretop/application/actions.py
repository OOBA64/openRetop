"""Stable action definitions and the initial V3 action registry.

Actions describe user intent. They deliberately do not contain Tk callbacks or
VTK operations; presentation adapters resolve an action to its command ID.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
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
    HAS_MESH = "has_mesh"
    NOT_BUSY = "not_busy"
    SINGLE_SELECTION = "single_selection"
    MULTI_SELECTION = "multi_selection"
    HAS_SECTION_PLANE = "has_section_plane"
    HAS_SECTION_RESULT = "has_section_result"
    HAS_REGION = "has_region"
    CAN_TRANSFORM = "can_transform"
    TRANSFORM_ACTIVE = "transform_active"
    REGION_TOOL_ACTIVE = "region_tool_active"
    MEASURE_TOOL_ACTIVE = "measure_tool_active"
    HAS_MEASUREMENTS = "has_measurements"
    HAS_MODEL = "has_model"
    HAS_MODEL_SELECTION = "has_model_selection"
    MODEL_TOOL_ACTIVE = "model_tool_active"


# What to tell a user when a command is unavailable because ``condition`` is unmet.
# Phrased as a requirement ("Needs ..."), shown in tooltips and the command palette.
CONDITION_REQUIREMENTS: Mapping[ActionCondition, str] = MappingProxyType(
    {
        ActionCondition.HAS_SCENE_OBJECTS: "something in the scene",
        ActionCondition.HAS_SCENE_SELECTION: "a selection in the scene",
        ActionCondition.CAN_UNDO: "something to undo",
        ActionCondition.CAN_REDO: "something to redo",
        ActionCondition.HAS_MESH: "a loaded scan (File > Open Model)",
        ActionCondition.NOT_BUSY: "the current task to finish",
        ActionCondition.SINGLE_SELECTION: "exactly one item selected",
        ActionCondition.MULTI_SELECTION: "more than one item selected",
        ActionCondition.HAS_SECTION_PLANE: "a section plane",
        ActionCondition.HAS_SECTION_RESULT: "a computed section",
        ActionCondition.HAS_REGION: "a selected region (Create > Region Select)",
        ActionCondition.CAN_TRANSFORM: "the model or a section plane selected",
        ActionCondition.TRANSFORM_ACTIVE: "a move/rotate in progress",
        ActionCondition.REGION_TOOL_ACTIVE: "the region tool active",
        ActionCondition.MEASURE_TOOL_ACTIVE: "the measure tool active",
        ActionCondition.HAS_MEASUREMENTS: "a measurement on the scan (Inspect > Measure Distance)",
        ActionCondition.HAS_MODEL: "a surface in the model (Surfacing > Fit Surface)",
        ActionCondition.HAS_MODEL_SELECTION: "a selected model surface",
        ActionCondition.MODEL_TOOL_ACTIVE: "a surfacing tool open",
    }
)


@dataclass(frozen=True, slots=True)
class ActionContext:
    """Typed state used to evaluate action availability."""

    has_scene_objects: bool = False
    has_scene_selection: bool = False
    can_undo: bool = False
    can_redo: bool = False
    mesh_loaded: bool = False
    busy: bool = False
    selection_count: int = 0
    has_section_plane: bool = False
    has_section_result: bool = False
    has_region: bool = False
    can_transform: bool = False
    transform_active: bool = False
    region_tool_active: bool = False
    measure_tool_active: bool = False
    has_measurements: bool = False
    model_count: int = 0
    selected_model_count: int = 0
    model_tool_active: bool = False

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
        if condition is ActionCondition.HAS_MESH:
            return self.mesh_loaded
        if condition is ActionCondition.NOT_BUSY:
            return not self.busy
        if condition is ActionCondition.SINGLE_SELECTION:
            return self.selection_count == 1
        if condition is ActionCondition.MULTI_SELECTION:
            return self.selection_count > 1
        if condition is ActionCondition.HAS_SECTION_PLANE:
            return self.has_section_plane
        if condition is ActionCondition.HAS_SECTION_RESULT:
            return self.has_section_result
        if condition is ActionCondition.HAS_REGION:
            return self.has_region
        if condition is ActionCondition.MEASURE_TOOL_ACTIVE:
            return self.measure_tool_active
        if condition is ActionCondition.HAS_MEASUREMENTS:
            return self.has_measurements
        if condition is ActionCondition.CAN_TRANSFORM:
            return self.can_transform
        if condition is ActionCondition.TRANSFORM_ACTIVE:
            return self.transform_active
        if condition is ActionCondition.REGION_TOOL_ACTIVE:
            return self.region_tool_active
        if condition is ActionCondition.HAS_MODEL:
            return self.model_count > 0
        if condition is ActionCondition.HAS_MODEL_SELECTION:
            return self.selected_model_count > 0
        if condition is ActionCondition.MODEL_TOOL_ACTIVE:
            return self.model_tool_active
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

    def unmet_requirements(self, context: ActionContext) -> tuple[str, ...]:
        """Plain-language reasons this action is currently unavailable (empty if it is available)."""

        return tuple(
            CONDITION_REQUIREMENTS[condition]
            for condition in self.enabled_when
            if not context.satisfies(condition)
        )

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
        shortcut="Home",
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


# Specific help text for the commands people use most; everything else gets a generic line.
_DESCRIPTIONS: Mapping[str, str] = MappingProxyType(
    {
        "section.add_plane": "Add a cutting plane. Slide it along an axis in the Properties panel, then compute the section.",
        "section.compute": "Slice the scan with the active section plane; the outline becomes a curve.",
        "section.clear_active": "Remove the active section result and its curves.",
        "section.clear_all": "Remove every section result and its curves.",
        "model.sketch": "Draw curves on the scan: click points, Enter finishes, click the first point to close, snap to points to connect curves. Drag a point to move it.",
        "model.sketch_face": "A face inside the selected closed curve, or loop of connected curves, fitted to the scan inside it.",
        "model.sketch_loft": "A surface through the selected sketch curves (two or more).",
        "model.edit_feature": "Change a feature of the history (an extrude's depths, draft or mode); everything after it is rebuilt.",
        "model.rebuild": "Replay the whole design history in the kernel: sketches, extrudes and the bodies they make.",
        "model.extrude": "Extrude a sketch into a solid: the depth comes from the scan (each hole its own), with draft; as a new body, or added to / cut from one.",
        "model.plane_sketch": "Draw a sketch on a plane through the scan (its cut shown to draw over): lines, rectangles, circles and arcs, held by constraints and dimensions; extrude it into a solid.",
        "model.sketch2d_dimension": "Dimension the selection: a line's length, two points' distance, a point to a line, two lines' angle (or distance), a circle's diameter, an arc's radius.",
        "model.sketch2d_construction": "Make the selected sketch curves construction geometry (guides that do not form profiles), or back.",
        "model.sketch2d_finish": "Keep the sketch: its closed regions become profiles to extrude; editing it later rebuilds what was made from it.",
        "model.section_sketch": "Sketch on a plane through the scan: its section is fitted with exact lines and arcs (sharp corners, tangent fillets, H/V snap), ready to extrude.",
        "model.fit_surface": "Fit a surface to an area of the scan: select it (click or brush), choose the type (auto, freeform, plane, cylinder, ...), Fit, Create.",
        "model.loft": "A surface through two or more selected curves (e.g. curves drawn on the scan).",
        "model.fill": "Fill a gap bounded by curves and surface edges; edges can join smoothly (tangent).",
        "model.extend": "Grow the selected surfaces past their edges, so they can be trimmed against neighbours.",
        "model.trim": "Split the surfaces by each other, keep the pieces lying on the scan, and sew them (into a solid when closed).",
        "model.compare": "Colour the scan by its distance to the model surfaces.",
        "model.delete_selected": "Delete the selected model surfaces and bodies.",
        "model.finish": "Close the surfacing tool.",
        "region.start": "Click a smooth area of the scan to select it; the threshold controls how far it spreads.",
        "measure.distance": "Click two points on the scan to measure the distance between them in the project's units.",
        "measure.model_size": "Show the scan's overall size (X x Y x Z and diagonal) to check it against the real part.",
        "measure.clear": "Remove every measurement from the view.",
        "measure.finish": "Leave the measure tool; finished measurements stay on screen.",
        "region.extract_boundary": "Turn the outline of the selected region into curves.",
        "view.frame_all": "Fit everything in the view.",
        "view.frame_selected": "Fit the selected objects in the view.",
        "view.reset": "Return to the default camera.",
        "transform.move": "Move the selected object. Type X, Y or Z to constrain; Enter confirms, Esc cancels.",
        "transform.rotate": "Rotate the selected object. Type X, Y or Z to constrain; Enter confirms, Esc cancels.",
        "edit.undo": "Undo the last change.",
        "edit.redo": "Redo the change you just undid.",
        "scene.show_all": "Show every hidden object.",
        "scene.delete_selected": "Delete the selected objects (can be undone).",
    }
)

# Named-view shortcuts follow the common CAD convention (Ctrl+1..7).
_VIEW_SHORTCUTS: Mapping[str, str] = MappingProxyType(
    {
        "view.frame_all": "Home",
        "view.named.front": "Ctrl+1",
        "view.named.back": "Ctrl+2",
        "view.named.left": "Ctrl+3",
        "view.named.right": "Ctrl+4",
        "view.named.top": "Ctrl+5",
        "view.named.bottom": "Ctrl+6",
        "view.named.isometric": "Ctrl+7",
    }
)


def _workflow_action(
    action_id: str,
    label: str,
    category: str,
    legacy_handler: str,
    *,
    enabled_when: tuple[ActionCondition, ...] = (ActionCondition.ALWAYS,),
    visible_when: tuple[ActionCondition, ...] = (ActionCondition.ALWAYS,),
    shortcut: str | None = None,
    description: str | None = None,
    **metadata: object,
) -> ActionDefinition:
    return ActionDefinition(
        id=action_id,
        label=label,
        description=description or _DESCRIPTIONS.get(action_id) or f"{label} in the current workflow.",
        category=category,
        shortcut=shortcut or _VIEW_SHORTCUTS.get(action_id),
        command_id=action_id,
        enabled_when=enabled_when,
        visible_when=visible_when,
        metadata={
            "legacy_handler": legacy_handler,
            "migration_task": 76,
            **metadata,
        },
    )


_ALWAYS = (ActionCondition.ALWAYS,)
_NOT_BUSY = (ActionCondition.NOT_BUSY,)
_MESH = (ActionCondition.HAS_MESH, ActionCondition.NOT_BUSY)
_SELECTION = (ActionCondition.HAS_SCENE_SELECTION,)
_REGION = (ActionCondition.HAS_REGION, ActionCondition.NOT_BUSY)


WORKFLOW_ACTIONS: tuple[ActionDefinition, ...] = (
    # Scene selection, naming, visibility, and deletion.
    _workflow_action("scene.select_model", "Select Model", "Scene", "select_model", enabled_when=(ActionCondition.HAS_MESH,)),
    _workflow_action("scene.select_section_plane", "Select Section Plane", "Scene", "select_section_plane", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_SECTION_PLANE)),
    _workflow_action("scene.delete_mesh", "Delete Mesh", "Scene", "delete_mesh", enabled_when=_MESH),
    _workflow_action("scene.toggle_mesh_visibility", "Toggle Mesh Visibility", "Scene", "_on_mesh_visibility_changed", enabled_when=(ActionCondition.HAS_MESH,)),
    _workflow_action("scene.clear_selection", "Clear Selection", "Scene", "clear_selection", enabled_when=_SELECTION),
    _workflow_action("scene.rename_selected", "Rename Selected", "Scene", "rename_selected", enabled_when=(ActionCondition.SINGLE_SELECTION,), shortcut="F2"),
    _workflow_action("scene.delete_selected", "Delete Selected", "Scene", "delete_selected_scene_objects", enabled_when=_SELECTION, shortcut="Delete"),
    _workflow_action("scene.hide_selected", "Hide Selected", "Scene", "hide_selected_scene_objects", enabled_when=_SELECTION),
    _workflow_action("scene.show_selected", "Show Selected", "Scene", "show_selected_scene_objects", enabled_when=_SELECTION),
    _workflow_action("scene.set_visibility", "Set Visibility", "Scene", "set_scene_visibility"),
    _workflow_action("scene.isolate_selected", "Isolate Selected", "Scene", "hide_unselected_scene_objects", enabled_when=_SELECTION, shortcut="Shift+H"),

    # View commands without file or dialog ownership. Task 77 retains camera math.
    _workflow_action("view.frame_region", "Frame Region", "View", "frame_selected_region", enabled_when=_REGION),
    _workflow_action("view.reset", "Reset View", "View", "reset_view"),
    *tuple(
        _workflow_action(
            f"view.named.{name.lower()}",
            name,
            "View",
            "set_named_view",
            handler_args=(name,),
        )
        for name in ("Top", "Bottom", "Front", "Back", "Left", "Right", "Isometric")
    ),
    _workflow_action("view.roll_left", "Roll View Left", "View", "roll_view", handler_args=(-15.0,)),
    _workflow_action("view.roll_right", "Roll View Right", "View", "roll_view", handler_args=(15.0,)),
    _workflow_action("view.toggle_grid", "Show Grid", "View", "_on_view_option_changed"),
    _workflow_action("view.toggle_axes", "Show Axes", "View", "_on_view_option_changed"),
    _workflow_action("view.toggle_axis_gizmo", "Show XYZ Axes", "View", "_on_view_option_changed"),
    _workflow_action("view.toggle_view_controls", "Show View Cube", "View", "_on_view_option_changed"),
    _workflow_action("view.toggle_normals", "Show Normals", "View", "_on_view_option_changed", enabled_when=(ActionCondition.HAS_MESH,)),
    _workflow_action("view.proxy_quality", "Display Proxy Quality", "View", "_on_proxy_quality_changed", enabled_when=(ActionCondition.HAS_MESH,), requires_payload=True),

    # Transform and origin workflows.
    _workflow_action("transform.move", "Move", "Transform", "start_move_transform", enabled_when=(ActionCondition.CAN_TRANSFORM, ActionCondition.NOT_BUSY), shortcut="G"),
    _workflow_action("transform.rotate", "Rotate", "Transform", "start_rotate_transform", enabled_when=(ActionCondition.CAN_TRANSFORM, ActionCondition.NOT_BUSY), shortcut="R"),
    _workflow_action("transform.confirm", "Confirm Transform", "Transform", "_end_active_transform", enabled_when=(ActionCondition.TRANSFORM_ACTIVE,), visible_when=(ActionCondition.TRANSFORM_ACTIVE,), handler_kwargs={"commit": True, "status": "Transform confirmed"}),
    _workflow_action("transform.cancel", "Cancel Transform", "Transform", "_end_active_transform", enabled_when=(ActionCondition.TRANSFORM_ACTIVE,), visible_when=(ActionCondition.TRANSFORM_ACTIVE,), shortcut="Esc", handler_kwargs={"commit": False, "status": "Transform cancelled"}),
    *tuple(
        _workflow_action(
            f"transform.constrain_{axis.lower()}",
            label,
            "Transform",
            "_set_transform_axis_constraint",
            enabled_when=(ActionCondition.TRANSFORM_ACTIVE,),
            visible_when=(ActionCondition.TRANSFORM_ACTIVE,),
            handler_args=(axis,),
            shortcut=axis,
        )
        for axis, label in (
            ("X", "Lock to X Axis"),
            ("Y", "Lock to Y Axis"),
            ("Z", "Lock to Z Axis"),
            ("N", "Lock to Plane Normal"),
        )
    ),
    *tuple(
        _workflow_action(
            f"transform.constrain_plane_{axis.lower()}",
            f"Lock to {plane} Plane",
            "Transform",
            "_set_transform_axis_constraint",
            enabled_when=(ActionCondition.TRANSFORM_ACTIVE,),
            visible_when=(ActionCondition.TRANSFORM_ACTIVE,),
            handler_args=(plane,),
            shortcut=f"Shift+{axis}",
        )
        for axis, plane in (("X", "YZ"), ("Y", "XZ"), ("Z", "XY"))
    ),
    _workflow_action("transform.apply_numeric", "Apply Transform", "Transform", "_on_object_transform_changed", enabled_when=(ActionCondition.HAS_MESH,), requires_payload=True),
    _workflow_action("transform.origin_to_geometry", "Set Origin to Geometry", "Transform", "set_origin_to_geometry", enabled_when=(ActionCondition.HAS_MESH,)),
    _workflow_action("transform.origin_to_world", "Move Origin to World Origin", "Transform", "move_origin_to_world_origin", enabled_when=(ActionCondition.HAS_MESH,)),
    _workflow_action("transform.center_geometry", "Center Geometry on Origin", "Transform", "center_geometry_on_origin", enabled_when=(ActionCondition.HAS_MESH,)),
    _workflow_action("transform.reset", "Reset Object Transform", "Transform", "reset_object_transform", enabled_when=(ActionCondition.HAS_MESH,)),

    # Section workflows.
    _workflow_action("section.add_plane", "Add Section Plane", "Sections", "add_section_plane", enabled_when=_MESH),
    _workflow_action("section.delete_plane", "Delete Section Plane", "Sections", "delete_active_section_plane", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_SECTION_PLANE, ActionCondition.NOT_BUSY)),
    _workflow_action("section.compute", "Compute Section", "Sections", "compute_section", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_SECTION_PLANE, ActionCondition.NOT_BUSY)),
    _workflow_action("section.clear_active", "Clear Section", "Sections", "clear_active_section_result", enabled_when=(ActionCondition.HAS_SECTION_RESULT, ActionCondition.NOT_BUSY)),
    _workflow_action("section.clear_all", "Clear All Sections", "Sections", "clear_all_section_results", enabled_when=(ActionCondition.HAS_SECTION_RESULT, ActionCondition.NOT_BUSY)),
    _workflow_action("section.set_axis", "Set Section Axis", "Sections", "_on_section_axis_changed", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_SECTION_PLANE), requires_payload=True),
    _workflow_action("section.set_offset", "Set Section Offset", "Sections", "_set_section_offset", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_SECTION_PLANE), requires_payload=True),
    _workflow_action("section.toggle_plane_visibility", "Toggle Section Plane Visibility", "Sections", "_on_section_plane_visibility_changed", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_SECTION_PLANE)),
    _workflow_action("section.toggle_result_visibility", "Toggle Section Result Visibility", "Sections", "_on_section_result_visibility_changed", enabled_when=(ActionCondition.HAS_SECTION_RESULT,)),

    # Stored-curve processing; manual-curve geometry remains Task 74-owned.

    # Task 74 manual-curve controller actions, now centrally discoverable.

    # Measuring the scan.
    _workflow_action("measure.distance", "Measure Distance", "Inspect", "start_measure_mode", enabled_when=_MESH, shortcut="M"),
    _workflow_action("measure.model_size", "Show Model Size", "Inspect", "show_model_size", enabled_when=_MESH),
    _workflow_action("measure.clear", "Clear Measurements", "Inspect", "clear_measurements", enabled_when=(ActionCondition.HAS_MEASUREMENTS,)),
    _workflow_action("measure.finish", "Done Measuring", "Inspect", "finish_measure_mode", enabled_when=(ActionCondition.MEASURE_TOOL_ACTIVE,), visible_when=(ActionCondition.MEASURE_TOOL_ACTIVE,)),

    # Surfacing toolset (milestone S): each opens a tool panel; the panel's buttons are the
    # payload actions below it.
    _workflow_action("model.sketch", "Surface Sketch", "Surfacing", "start_sketch", enabled_when=_MESH),
    _workflow_action("model.sketch_finish", "Finish Curve", "Surfacing", "sketch_finish", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch_close", "Close Curve", "Surfacing", "sketch_close", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch_undo_point", "Remove Last Point", "Surfacing", "sketch_undo_point", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch_delete", "Delete Sketch Curves", "Surfacing", "sketch_delete", enabled_when=(ActionCondition.NOT_BUSY,)),
    _workflow_action("model.sketch_delete_point", "Delete Sketch Point", "Surfacing", "sketch_delete_point", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch_insert_point", "Add Point to Curve", "Surfacing", "sketch_insert_point", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.sketch_split", "Split Curve at Point", "Surfacing", "sketch_split", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch_toggle_closed", "Open / Close Curve", "Surfacing", "sketch_toggle_closed", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch_reverse", "Reverse Curve", "Surfacing", "sketch_reverse", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch_options", "Curve Options", "Surfacing", "sketch_options", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.sketch_loft", "Loft Sketch Curves", "Surfacing", "sketch_loft", enabled_when=(ActionCondition.NOT_BUSY,)),
    _workflow_action("model.sketch_face", "Face From Curves", "Surfacing", "sketch_face", enabled_when=(ActionCondition.NOT_BUSY,)),
    _workflow_action("model.section_sketch", "Section Sketch", "Surfacing", "start_section_sketch", enabled_when=_MESH),
    _workflow_action("model.plane_sketch", "3D Sketch", "Surfacing", "start_plane_sketch", enabled_when=(ActionCondition.NOT_BUSY,)),
    _workflow_action("model.sketch2d_tool", "Sketch Tool", "Surfacing", "sketch2d_tool", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.sketch2d_plane", "Sketch Plane", "Surfacing", "sketch2d_set_plane", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.sketch2d_constrain", "Add Constraint", "Surfacing", "sketch2d_constrain", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.sketch2d_dimension", "Dimension", "Surfacing", "sketch2d_dimension", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), shortcut="D"),
    _workflow_action("model.sketch2d_set_dimension", "Change Dimension", "Surfacing", "sketch2d_set_dimension", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.sketch2d_delete_constraint", "Delete Constraint", "Surfacing", "sketch2d_delete_constraint", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.sketch2d_delete", "Delete Sketch Items", "Surfacing", "sketch2d_delete", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch2d_construction", "Construction", "Surfacing", "sketch2d_construction", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.sketch2d_finish", "Finish Sketch", "Surfacing", "sketch2d_finish", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.section_plane", "Set Sketch Plane", "Surfacing", "set_section_plane", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.section_edit", "Edit Sketch", "Surfacing", "section_edit_entity", enabled_when=(ActionCondition.HAS_MODEL_SELECTION, ActionCondition.NOT_BUSY)),
    _workflow_action("model.edit_feature", "Edit Feature", "Surfacing", "edit_feature", enabled_when=(ActionCondition.HAS_MODEL, ActionCondition.NOT_BUSY), requires_payload=True),
    _workflow_action("model.rebuild", "Rebuild History", "Surfacing", "rebuild", enabled_when=(ActionCondition.HAS_MODEL, ActionCondition.NOT_BUSY)),
    _workflow_action("model.section_profile_edit", "Edit Sketch Profile", "Surfacing", "section_profile_edit", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.section_fit", "Fit Profile", "Surfacing", "fit_section_profile", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.section_create", "Create Sketch", "Surfacing", "create_section_sketch", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.extrude", "Extrude", "Surfacing", "start_extrude", enabled_when=(ActionCondition.HAS_MODEL, ActionCondition.NOT_BUSY)),
    _workflow_action("model.extrude_measure", "Depth From Scan", "Surfacing", "extrude_measure", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.extrude_preview", "Preview Extrude", "Surfacing", "extrude_preview", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.extrude_apply", "Create Extrusion", "Surfacing", "extrude_apply", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.fit_surface", "Fit Surface", "Surfacing", "start_fit_surface", enabled_when=_MESH),
    _workflow_action("model.loft", "Loft", "Surfacing", "start_loft", enabled_when=_NOT_BUSY),
    _workflow_action("model.fill", "Fill Surface", "Surfacing", "start_fill", enabled_when=_NOT_BUSY),
    _workflow_action("model.extend", "Extend Surface", "Surfacing", "start_extend", enabled_when=(ActionCondition.HAS_MODEL, ActionCondition.NOT_BUSY)),
    _workflow_action("model.trim", "Trim Surfaces", "Surfacing", "start_trim", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_MODEL, ActionCondition.NOT_BUSY)),
    _workflow_action("model.compare", "Compare", "Surfacing", "start_compare", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_MODEL, ActionCondition.NOT_BUSY)),
    _workflow_action("model.delete_selected", "Delete Model Items", "Surfacing", "delete_model_items", enabled_when=(ActionCondition.HAS_MODEL_SELECTION, ActionCondition.NOT_BUSY)),
    _workflow_action("model.finish", "Close Surfacing Tool", "Surfacing", "finish_model_tool", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.configure", "Surfacing Options", "Surfacing", "configure_model_tool", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.select_clear", "Clear Scan Selection", "Surfacing", "clear_scan_selection", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.select_invert", "Invert Scan Selection", "Surfacing", "invert_scan_selection", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.fit_preview", "Fit", "Surfacing", "fit_surface_preview", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.fit_create", "Create Fitted Surface", "Surfacing", "fit_surface_create", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.loft_apply", "Loft Selected Curves", "Surfacing", "loft_selected_curves", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.fill_apply", "Fill", "Surfacing", "fill_boundary", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.fill_clear", "Clear Fill Boundary", "Surfacing", "clear_fill_boundary", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.fill_continuity", "Set Fill Side Continuity", "Surfacing", "set_fill_continuity", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE,), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,), requires_payload=True),
    _workflow_action("model.extend_apply", "Extend Selected Surfaces", "Surfacing", "extend_selected_surfaces", enabled_when=(ActionCondition.HAS_MODEL_SELECTION, ActionCondition.NOT_BUSY)),
    _workflow_action("model.trim_compute", "Automatic Trim", "Surfacing", "trim_compute", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.trim_apply", "Apply Trim", "Surfacing", "trim_apply", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
    _workflow_action("model.compare_apply", "Compute Deviation", "Surfacing", "compare_model", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_MODEL, ActionCondition.NOT_BUSY)),
    _workflow_action("model.compare_clear", "Clear Deviation Map", "Surfacing", "clear_deviation", enabled_when=_ALWAYS),

    # Region selection and derived-boundary workflows.
    _workflow_action("region.start", "Region Select", "Regions", "start_region_select_mode", enabled_when=_MESH),
    _workflow_action("region.recompute", "Recompute Region", "Regions", "recompute_region_selection", enabled_when=_REGION),
    _workflow_action("region.clear", "Clear Region", "Regions", "clear_region_selection", enabled_when=_REGION),
    _workflow_action("region.hide", "Hide Region", "Regions", "hide_region_selection", enabled_when=_REGION),
    _workflow_action("region.show", "Show Region", "Regions", "show_region_selection", enabled_when=_REGION),
    _workflow_action("region.delete", "Delete Region", "Regions", "delete_region_selection", enabled_when=_REGION),
    _workflow_action("region.rename", "Rename Region", "Regions", "_on_region_name_changed", enabled_when=_REGION),
    _workflow_action("region.finish", "Done Region Select", "Regions", "_exit_region_select_mode", enabled_when=(ActionCondition.REGION_TOOL_ACTIVE,), visible_when=(ActionCondition.REGION_TOOL_ACTIVE,)),
    _workflow_action("region.extract_boundary", "Extract Region Boundary", "Regions", "extract_region_boundary", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_REGION, ActionCondition.NOT_BUSY)),
    _workflow_action("region.threshold", "Region Threshold", "Regions", "_on_region_threshold_slider_changed", enabled_when=(ActionCondition.HAS_MESH,), requires_payload=True),
    _workflow_action("region.max_triangles", "Region Maximum Triangles", "Regions", "_on_region_max_triangle_entry_changed", enabled_when=(ActionCondition.HAS_MESH,)),

    # Preview surfaces, BREP records, and editable feature workflows.

    # Read-only analysis actions.
)


CORE_ACTIONS: tuple[ActionDefinition, ...] = (*REPRESENTATIVE_ACTIONS, *WORKFLOW_ACTIONS)


def create_core_action_registry() -> ActionRegistry:
    """Return a fresh registry containing all non-file-dialog application actions."""

    return ActionRegistry(CORE_ACTIONS)

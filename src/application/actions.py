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
    HAS_MESH = "has_mesh"
    NOT_BUSY = "not_busy"
    SINGLE_SELECTION = "single_selection"
    MULTI_SELECTION = "multi_selection"
    HAS_SECTION_PLANE = "has_section_plane"
    HAS_SECTION_RESULT = "has_section_result"
    HAS_CURVES = "has_curves"
    HAS_CURVE_SELECTION = "has_curve_selection"
    SINGLE_CURVE = "single_curve"
    TWO_CURVES = "two_curves"
    AT_LEAST_TWO_CURVES = "at_least_two_curves"
    AT_LEAST_THREE_CURVES = "at_least_three_curves"
    FOUR_CURVES = "four_curves"
    SINGLE_CLOSED_CURVE = "single_closed_curve"
    SINGLE_OPEN_CURVE = "single_open_curve"
    SINGLE_EDITABLE_CURVE = "single_editable_curve"
    HAS_SURFACE_SELECTION = "has_surface_selection"
    SINGLE_SURFACE = "single_surface"
    HAS_REGION = "has_region"
    HAS_BREP_SELECTION = "has_brep_selection"
    HAS_LOFT_FEATURE = "has_loft_feature"
    HAS_SOURCE_CURVES = "has_source_curves"
    CAN_TRANSFORM = "can_transform"
    TRANSFORM_ACTIVE = "transform_active"
    MANUAL_CURVE_ACTIVE = "manual_curve_active"
    MANUAL_CURVE_IDLE = "manual_curve_idle"
    MANUAL_CURVE_CREATING = "manual_curve_creating"
    MANUAL_CURVE_EDITING = "manual_curve_editing"
    CAN_ADD_MANUAL_POINT = "can_add_manual_point"
    HAS_MANUAL_CONTROL_POINT = "has_manual_control_point"
    REGION_TOOL_ACTIVE = "region_tool_active"
    HAS_REGION_BOUNDARY_CURVES = "has_region_boundary_curves"
    SELECTED_REGION_BOUNDARY_CURVE = "selected_region_boundary_curve"
    CAD_AVAILABLE = "cad_available"
    HAS_RUNTIME_BREP = "has_runtime_brep"


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
    has_curves: bool = False
    selected_curve_count: int = 0
    selected_curve_closed: bool = False
    selected_curve_open: bool = False
    selected_curve_editable: bool = False
    selected_surface_count: int = 0
    has_region: bool = False
    selected_brep_count: int = 0
    has_loft_feature: bool = False
    has_source_curves: bool = False
    can_transform: bool = False
    transform_active: bool = False
    manual_curve_active: bool = False
    manual_curve_idle: bool = False
    manual_curve_creating: bool = False
    manual_curve_editing: bool = False
    can_add_manual_point: bool = False
    has_manual_control_point: bool = False
    region_tool_active: bool = False
    has_region_boundary_curves: bool = False
    selected_region_boundary_curve: bool = False
    cad_available: bool = False
    has_runtime_brep: bool = False

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
        if condition is ActionCondition.HAS_CURVES:
            return self.has_curves
        if condition is ActionCondition.HAS_CURVE_SELECTION:
            return self.selected_curve_count > 0
        if condition is ActionCondition.SINGLE_CURVE:
            return self.selected_curve_count == 1
        if condition is ActionCondition.TWO_CURVES:
            return self.selected_curve_count == 2
        if condition is ActionCondition.AT_LEAST_TWO_CURVES:
            return self.selected_curve_count >= 2
        if condition is ActionCondition.AT_LEAST_THREE_CURVES:
            return self.selected_curve_count >= 3
        if condition is ActionCondition.FOUR_CURVES:
            return self.selected_curve_count == 4
        if condition is ActionCondition.SINGLE_CLOSED_CURVE:
            return self.selected_curve_count == 1 and self.selected_curve_closed
        if condition is ActionCondition.SINGLE_OPEN_CURVE:
            return self.selected_curve_count == 1 and self.selected_curve_open
        if condition is ActionCondition.SINGLE_EDITABLE_CURVE:
            return self.selected_curve_count == 1 and self.selected_curve_editable
        if condition is ActionCondition.HAS_SURFACE_SELECTION:
            return self.selected_surface_count > 0
        if condition is ActionCondition.SINGLE_SURFACE:
            return self.selected_surface_count == 1
        if condition is ActionCondition.HAS_REGION:
            return self.has_region
        if condition is ActionCondition.HAS_BREP_SELECTION:
            return self.selected_brep_count > 0
        if condition is ActionCondition.HAS_LOFT_FEATURE:
            return self.has_loft_feature
        if condition is ActionCondition.HAS_SOURCE_CURVES:
            return self.has_source_curves
        if condition is ActionCondition.CAN_TRANSFORM:
            return self.can_transform
        if condition is ActionCondition.TRANSFORM_ACTIVE:
            return self.transform_active
        if condition is ActionCondition.MANUAL_CURVE_ACTIVE:
            return self.manual_curve_active
        if condition is ActionCondition.MANUAL_CURVE_IDLE:
            return self.manual_curve_idle
        if condition is ActionCondition.MANUAL_CURVE_CREATING:
            return self.manual_curve_creating
        if condition is ActionCondition.MANUAL_CURVE_EDITING:
            return self.manual_curve_editing
        if condition is ActionCondition.CAN_ADD_MANUAL_POINT:
            return self.can_add_manual_point
        if condition is ActionCondition.HAS_MANUAL_CONTROL_POINT:
            return self.has_manual_control_point
        if condition is ActionCondition.REGION_TOOL_ACTIVE:
            return self.region_tool_active
        if condition is ActionCondition.HAS_REGION_BOUNDARY_CURVES:
            return self.has_region_boundary_curves
        if condition is ActionCondition.SELECTED_REGION_BOUNDARY_CURVE:
            return self.selected_region_boundary_curve
        if condition is ActionCondition.CAD_AVAILABLE:
            return self.cad_available
        if condition is ActionCondition.HAS_RUNTIME_BREP:
            return self.has_runtime_brep
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
        description=description or f"{label} in the current workflow.",
        category=category,
        shortcut=shortcut,
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
_CURVES = (ActionCondition.HAS_CURVE_SELECTION, ActionCondition.NOT_BUSY)
_ONE_CURVE = (ActionCondition.SINGLE_CURVE, ActionCondition.NOT_BUSY)
_TWO_CURVES = (ActionCondition.TWO_CURVES, ActionCondition.NOT_BUSY)
_SURFACE = (ActionCondition.HAS_SURFACE_SELECTION, ActionCondition.NOT_BUSY)
_REGION = (ActionCondition.HAS_REGION, ActionCondition.NOT_BUSY)
_MANUAL = (ActionCondition.MANUAL_CURVE_ACTIVE,)
_MANUAL_IDLE = (ActionCondition.MANUAL_CURVE_IDLE,)
_MANUAL_CREATE = (ActionCondition.MANUAL_CURVE_CREATING,)
_MANUAL_EDIT = (ActionCondition.MANUAL_CURVE_EDITING,)
_MANUAL_POINT = (
    ActionCondition.MANUAL_CURVE_EDITING,
    ActionCondition.HAS_MANUAL_CONTROL_POINT,
)
_MANUAL_CAN_ADD = (ActionCondition.CAN_ADD_MANUAL_POINT,)


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
    _workflow_action("scene.select_source_curves", "Select Source Curves", "Scene", "select_source_curves_for_active_surface", enabled_when=(ActionCondition.HAS_SOURCE_CURVES,)),
    _workflow_action("scene.isolate_source_curves", "Isolate Source Curves", "Scene", "isolate_source_curves_for_active_surface", enabled_when=(ActionCondition.HAS_SOURCE_CURVES,)),
    _workflow_action("scene.show_source_curves", "Show Source Curves", "Scene", "show_source_curves_for_active_surface", enabled_when=(ActionCondition.HAS_SOURCE_CURVES,)),

    # View commands without file or dialog ownership. Task 77 retains camera math.
    _workflow_action("view.frame_region", "Frame Region", "View", "frame_selected_region", enabled_when=_REGION),
    _workflow_action("view.frame_source_curves", "Frame Source Curves", "View", "frame_source_curves_for_active_surface", enabled_when=(ActionCondition.HAS_SOURCE_CURVES,)),
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
    _workflow_action("view.toggle_grid", "Show Grid", "View", "_on_view_option_changed"),
    _workflow_action("view.toggle_axes", "Show Axes", "View", "_on_view_option_changed"),
    _workflow_action("view.toggle_axis_gizmo", "Show Axis Gizmo", "View", "_on_view_option_changed"),
    _workflow_action("view.toggle_view_controls", "Show View Controls", "View", "_on_view_option_changed"),
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
            f"Constrain {axis}",
            "Transform",
            "_set_transform_axis_constraint",
            enabled_when=(ActionCondition.TRANSFORM_ACTIVE,),
            visible_when=(ActionCondition.TRANSFORM_ACTIVE,),
            handler_args=(axis,),
        )
        for axis in ("X", "Y", "Z", "N")
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
    _workflow_action("curve.join", "Join Selected Curves", "Curves", "join_selected_curves", enabled_when=(ActionCondition.AT_LEAST_TWO_CURVES, ActionCondition.NOT_BUSY)),
    _workflow_action("curve.auto_close", "Auto-Close Selected Curve", "Curves", "auto_close_selected_curve", enabled_when=(ActionCondition.SINGLE_OPEN_CURVE, ActionCondition.NOT_BUSY)),
    _workflow_action("curve.simplify", "Simplify Selected Curve", "Curves", "simplify_selected_curve", enabled_when=_ONE_CURVE),
    _workflow_action("curve.smooth", "Smooth Selected Curve", "Curves", "smooth_selected_curve", enabled_when=_ONE_CURVE),
    _workflow_action("curve.project", "Project Selected Curve to Mesh", "Curves", "project_selected_curve_to_mesh", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.SINGLE_CURVE, ActionCondition.MANUAL_CURVE_IDLE, ActionCondition.NOT_BUSY)),
    _workflow_action("curve.rebuild", "Rebuild Selected Curve", "Curves", "rebuild_selected_curve", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.SINGLE_CURVE, ActionCondition.MANUAL_CURVE_IDLE, ActionCondition.NOT_BUSY)),
    _workflow_action("curve.validate_fill", "Validate Selected Curve", "Curves", "validate_selected_curve", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.SINGLE_CURVE, ActionCondition.MANUAL_CURVE_IDLE, ActionCondition.NOT_BUSY)),
    _workflow_action("curve.validate_loft", "Validate Selected Curves for Loft", "Curves", "validate_selected_curves_for_loft", enabled_when=_TWO_CURVES),
    _workflow_action("curve.convert_smooth", "Convert to Smooth Curve", "Curves", "convert_selected_curve_to_smooth_guide", enabled_when=(ActionCondition.SINGLE_EDITABLE_CURVE, ActionCondition.MANUAL_CURVE_IDLE, ActionCondition.NOT_BUSY)),
    _workflow_action("curve.simplify_guide", "Reduce Guide Curve", "Curves", "reduce_simplify_selected_guide_curve", enabled_when=(ActionCondition.SINGLE_EDITABLE_CURVE, ActionCondition.MANUAL_CURVE_IDLE, ActionCondition.NOT_BUSY)),
    _workflow_action("curve.hide_selected", "Hide Selected Curves", "Curves", "hide_selected_curves", enabled_when=_CURVES),
    _workflow_action("curve.isolate_selected", "Hide Unselected Curves", "Curves", "hide_unselected_curves", enabled_when=_CURVES),
    _workflow_action("curve.show_all", "Show All Curves", "Curves", "show_all_curves", enabled_when=(ActionCondition.HAS_CURVES,)),
    _workflow_action("curve.select_tiny", "Select Tiny Curves", "Curves", "select_tiny_curves", enabled_when=(ActionCondition.HAS_CURVES,)),
    _workflow_action("curve.hide_tiny", "Hide Tiny Curves", "Curves", "hide_tiny_curves", enabled_when=(ActionCondition.HAS_CURVES,)),
    _workflow_action("curve.delete_tiny", "Delete Tiny Curves", "Curves", "delete_tiny_curves", enabled_when=(ActionCondition.HAS_CURVES, ActionCondition.NOT_BUSY)),
    _workflow_action("curve.delete_selected", "Delete Selected Curve", "Curves", "delete_selected_curve", enabled_when=_CURVES),
    _workflow_action("curve.toggle_visibility", "Toggle Curve Visibility", "Curves", "_on_curve_visibility_changed", enabled_when=_CURVES),

    # Task 74 manual-curve controller actions, now centrally discoverable.
    _workflow_action("manual_curve.create", "Create Manual Curve", "Manual Curve", "start_manual_curve_mode", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.MANUAL_CURVE_IDLE, ActionCondition.NOT_BUSY)),
    _workflow_action("manual_curve.edit", "Edit Selected Curve", "Manual Curve", "start_manual_curve_edit_mode", enabled_when=(ActionCondition.SINGLE_EDITABLE_CURVE, ActionCondition.MANUAL_CURVE_IDLE, ActionCondition.NOT_BUSY)),
    _workflow_action("manual_curve.finish", "Finish Manual Curve", "Manual Curve", "_finish_manual_curve_action", enabled_when=_MANUAL, visible_when=_MANUAL),
    _workflow_action("manual_curve.apply", "Apply Curve Edits", "Manual Curve", "apply_manual_curve_edits", enabled_when=_MANUAL_EDIT, visible_when=_MANUAL_EDIT),
    _workflow_action("manual_curve.cancel", "Cancel Manual Curve", "Manual Curve", "_cancel_manual_curve_mode", enabled_when=_MANUAL, visible_when=_MANUAL),
    _workflow_action("manual_curve.remove_last", "Remove Last Point", "Manual Curve", "_remove_last_manual_curve_point", enabled_when=_MANUAL_CREATE, visible_when=_MANUAL),
    _workflow_action("manual_curve.toggle_closed", "Toggle Closed", "Manual Curve", "_toggle_manual_curve_closed", enabled_when=_MANUAL, visible_when=_MANUAL),
    _workflow_action("manual_curve.add_point", "Add Point", "Manual Curve", "activate_manual_curve_add_point", enabled_when=_MANUAL_CAN_ADD, visible_when=_MANUAL),
    _workflow_action("manual_curve.insert_point", "Insert Point", "Manual Curve", "activate_manual_curve_insert_point", enabled_when=_MANUAL_EDIT, visible_when=_MANUAL_EDIT),
    _workflow_action("manual_curve.delete_point", "Delete Selected Point", "Manual Curve", "delete_selected_manual_curve_point", enabled_when=_MANUAL_POINT, visible_when=_MANUAL_EDIT),
    _workflow_action("manual_curve.point_smooth", "Set Point Smooth", "Manual Curve", "set_selected_manual_curve_point_smooth", enabled_when=_MANUAL_POINT, visible_when=_MANUAL_EDIT),
    _workflow_action("manual_curve.point_corner", "Set Point Corner", "Manual Curve", "set_selected_manual_curve_point_corner", enabled_when=_MANUAL_POINT, visible_when=_MANUAL_EDIT),
    _workflow_action("manual_curve.toggle_point_type", "Toggle Point Type", "Manual Curve", "toggle_selected_manual_curve_point_type", enabled_when=_MANUAL, visible_when=_MANUAL),
    _workflow_action("manual_curve.auto_corners", "Auto Detect Corners", "Manual Curve", "auto_detect_manual_curve_corners", enabled_when=_MANUAL, visible_when=_MANUAL),
    _workflow_action("manual_curve.clear_auto_corners", "Clear Auto Corners", "Manual Curve", "clear_auto_detected_manual_curve_corners", enabled_when=_MANUAL, visible_when=_MANUAL),
    _workflow_action("manual_curve.smooth_span", "Smooth Selected Span", "Manual Curve", "smooth_selected_manual_curve_span", enabled_when=_MANUAL_EDIT, visible_when=_MANUAL_EDIT),
    _workflow_action("manual_curve.straighten_span", "Straighten Selected Span", "Manual Curve", "straighten_selected_manual_curve_span", enabled_when=_MANUAL_EDIT, visible_when=_MANUAL_EDIT),
    _workflow_action("manual_curve.snap_option", "Manual Curve Snap", "Manual Curve", "_on_manual_curve_snap_to_mesh_changed", enabled_when=(ActionCondition.HAS_MESH,)),
    _workflow_action("manual_curve.smoothness_option", "Manual Curve Smoothness", "Manual Curve", "_on_manual_curve_smoothness_changed", enabled_when=_ALWAYS),
    _workflow_action("manual_curve.type_option", "Manual Curve Type", "Manual Curve", "_on_manual_curve_type_changed", enabled_when=_MANUAL),
    _workflow_action("manual_curve.sample_count_option", "Manual Curve Sample Count", "Manual Curve", "_on_manual_curve_sample_count_changed", enabled_when=_MANUAL),
    _workflow_action("manual_curve.corner_threshold_option", "Manual Curve Corner Threshold", "Manual Curve", "_on_manual_curve_corner_threshold_changed", enabled_when=_MANUAL),
    _workflow_action("manual_curve.placement_option", "Manual Curve Point Placement", "Manual Curve", "_on_manual_curve_placement_changed", enabled_when=_MANUAL),
    _workflow_action("manual_curve.auto_corners_option", "Manual Curve Auto Corners", "Manual Curve", "_on_manual_curve_auto_corners_changed", enabled_when=_MANUAL),
    _workflow_action("manual_curve.keep_on_mesh_option", "Keep Manual Curve on Mesh", "Manual Curve", "_on_manual_curve_keep_on_mesh_changed", enabled_when=(ActionCondition.HAS_MESH,)),

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
    _workflow_action("region.select_boundaries", "Select Boundary Curves", "Regions", "select_boundary_curves_for_active_region", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_REGION, ActionCondition.HAS_REGION_BOUNDARY_CURVES, ActionCondition.NOT_BUSY)),
    _workflow_action("region.convert_boundary", "Convert Boundary to Guide Curve", "Regions", "convert_boundary_to_hybrid_guide_curve", enabled_when=(ActionCondition.SELECTED_REGION_BOUNDARY_CURVE, ActionCondition.MANUAL_CURVE_IDLE, ActionCondition.NOT_BUSY)),
    _workflow_action("region.threshold", "Region Threshold", "Regions", "_on_region_threshold_slider_changed", enabled_when=(ActionCondition.HAS_MESH,), requires_payload=True),
    _workflow_action("region.max_triangles", "Region Maximum Triangles", "Regions", "_on_region_max_triangle_entry_changed", enabled_when=(ActionCondition.HAS_MESH,)),

    # Preview surfaces, BREP records, and editable feature workflows.
    _workflow_action("surface.create_from_curves", "Create Surface From Curves", "Surfaces", "create_surface_from_curves", enabled_when=_CURVES),
    _workflow_action("surface.fill", "Fill Closed Curve", "Surfaces", "fill_closed_curve", enabled_when=(ActionCondition.SINGLE_CLOSED_CURVE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.loft", "Loft Between Two Curves", "Surfaces", "loft_between_two_curves", enabled_when=_TWO_CURVES),
    _workflow_action("surface.conforming_loft", "Mesh-Conforming Loft Preview", "Surfaces", "create_mesh_conforming_loft_preview", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.AT_LEAST_TWO_CURVES, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.boundary_patch", "Create Boundary Patch", "Surfaces", "create_boundary_patch_from_curve", enabled_when=(ActionCondition.SINGLE_CLOSED_CURVE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.four_curve_patch", "Create Four-Curve Patch", "Surfaces", "create_four_curve_patch", enabled_when=(ActionCondition.FOUR_CURVES, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.curve_network", "Create Curve Network Patch", "Surfaces", "create_curve_network_patch", enabled_when=(ActionCondition.AT_LEAST_THREE_CURVES, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.brep_face", "Create BREP Face", "BREP", "create_brep_face_from_closed_curve", enabled_when=(ActionCondition.SINGLE_CLOSED_CURVE, ActionCondition.CAD_AVAILABLE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.region_brep_face", "Create BREP Face From Region", "BREP", "create_brep_face_from_selected_region", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.HAS_REGION, ActionCondition.CAD_AVAILABLE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.brep_loft", "Create BREP Loft", "BREP", "create_brep_loft_from_two_curves", enabled_when=(ActionCondition.TWO_CURVES, ActionCondition.CAD_AVAILABLE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.editable_brep_loft", "Create Editable BREP Loft", "BREP", "create_editable_brep_loft_from_curves", enabled_when=(ActionCondition.AT_LEAST_TWO_CURVES, ActionCondition.CAD_AVAILABLE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.rebuild_brep", "Rebuild Selected BREP", "BREP", "rebuild_selected_brep_surface", enabled_when=(ActionCondition.HAS_BREP_SELECTION, ActionCondition.CAD_AVAILABLE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.delete", "Delete Selected Surface", "Surfaces", "delete_selected_surface", enabled_when=_SURFACE),
    _workflow_action("surface.toggle_visibility", "Toggle Surface Visibility", "Surfaces", "toggle_active_surface_visibility", enabled_when=_SURFACE),
    _workflow_action("surface.opacity", "Surface Opacity", "Surfaces", "_on_surface_opacity_changed", enabled_when=_SURFACE, requires_payload=True),
    _workflow_action("surface.wireframe", "Surface Wireframe Overlay", "Surfaces", "_on_surface_wireframe_changed", enabled_when=_SURFACE),
    _workflow_action("surface.set_visibility", "Set Surface Visibility", "Surfaces", "_on_surface_visibility_changed", enabled_when=_SURFACE),
    _workflow_action("surface.loft_options", "Editable Loft Options", "BREP", "_on_loft_feature_options_changed", enabled_when=(ActionCondition.HAS_LOFT_FEATURE,)),
    _workflow_action("surface.rebuild_loft", "Rebuild Loft", "BREP", "rebuild_selected_loft_feature", enabled_when=(ActionCondition.HAS_LOFT_FEATURE, ActionCondition.CAD_AVAILABLE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.edit_source", "Edit First Source Curve", "BREP", "edit_first_source_curve_for_active_loft", enabled_when=(ActionCondition.HAS_LOFT_FEATURE, ActionCondition.HAS_SOURCE_CURVES)),
    _workflow_action("surface.reverse_source", "Reverse Source Curve", "BREP", "reverse_selected_loft_source_curve_direction", enabled_when=(ActionCondition.HAS_LOFT_FEATURE, ActionCondition.HAS_SOURCE_CURVES)),
    _workflow_action("surface.source_up", "Move Source Curve Up", "BREP", "move_selected_loft_source_curve_up", enabled_when=(ActionCondition.HAS_LOFT_FEATURE, ActionCondition.HAS_SOURCE_CURVES)),
    _workflow_action("surface.source_down", "Move Source Curve Down", "BREP", "move_selected_loft_source_curve_down", enabled_when=(ActionCondition.HAS_LOFT_FEATURE, ActionCondition.HAS_SOURCE_CURVES)),
    _workflow_action("surface.duplicate_loft", "Duplicate Loft Feature", "BREP", "duplicate_selected_loft_feature", enabled_when=(ActionCondition.HAS_LOFT_FEATURE, ActionCondition.CAD_AVAILABLE, ActionCondition.NOT_BUSY)),
    _workflow_action("surface.delete_loft", "Delete Loft Feature", "BREP", "delete_selected_loft_feature", enabled_when=(ActionCondition.HAS_LOFT_FEATURE,)),
    _workflow_action("surface.rebuild_four_boundary", "Rebuild Four-Boundary Patch", "Surfaces", "rebuild_selected_four_boundary_patch_feature", enabled_when=_SURFACE),

    # Read-only analysis actions.
    _workflow_action("analysis.refresh", "Refresh Analysis", "Analysis", "_update_stats", enabled_when=(ActionCondition.HAS_SCENE_OBJECTS,)),
    _workflow_action("analysis.mesh_deviation", "Compute Mesh Deviation", "Analysis", "compute_mesh_deviation", enabled_when=(ActionCondition.HAS_MESH, ActionCondition.NOT_BUSY), requires_payload=True),
)


CORE_ACTIONS: tuple[ActionDefinition, ...] = (*REPRESENTATIVE_ACTIONS, *WORKFLOW_ACTIONS)


def create_core_action_registry() -> ActionRegistry:
    """Return a fresh registry containing all non-file-dialog application actions."""

    return ActionRegistry(CORE_ACTIONS)

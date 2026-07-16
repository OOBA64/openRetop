from __future__ import annotations

import ast
from dataclasses import replace
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import application
from application.actions import (
    ACTION_FRAME_ALL,
    ACTION_FRAME_SELECTED,
    ACTION_REDO,
    ACTION_SHOW_ALL,
    ACTION_TOGGLE_VISIBILITY,
    ACTION_UNDO,
    CORE_ACTIONS,
    REPRESENTATIVE_ACTIONS,
    WORKFLOW_ACTIONS,
    ActionCondition,
    ActionContext,
    ActionDefinition,
    ActionRegistry,
    create_core_action_registry,
)
from application.commands import (
    CommandDispatcher,
    CommandRejected,
    CommandRequest,
)
from application.dependencies import ApplicationDependencies
from application.events import (
    ApplicationEvent,
    CommandEvent,
    CommandPhase,
    EventPublisher,
    StatusEvent,
)
from application.results import (
    CommandResult,
    ViewportRequest,
    ViewportRequestKind,
)
from application.selection import (
    CallbackSelectionProvider,
    SelectionKind,
    SelectionSnapshot,
)


class _UndoStub:
    def __init__(self) -> None:
        self.can_undo = False
        self.can_redo = False

    def undo(self) -> None:
        return None

    def redo(self) -> None:
        return None


def _dependencies(
    *,
    events: EventPublisher | None = None,
    selection: SelectionSnapshot | None = None,
) -> ApplicationDependencies:
    return ApplicationDependencies(
        events=events or EventPublisher(),
        selection=CallbackSelectionProvider(
            lambda: selection or SelectionSnapshot()
        ),
        undo=_UndoStub(),
    )


class ApplicationActionTests(unittest.TestCase):
    def test_representative_registry_has_stable_complete_definitions(self) -> None:
        registry = create_core_action_registry()
        representative_ids = {
            ACTION_FRAME_ALL,
            ACTION_FRAME_SELECTED,
            ACTION_SHOW_ALL,
            ACTION_TOGGLE_VISIBILITY,
            ACTION_UNDO,
            ACTION_REDO,
        }

        self.assertLessEqual(representative_ids, set(registry.ids))
        self.assertEqual(registry.ids, tuple(action.id for action in CORE_ACTIONS))
        self.assertEqual(
            representative_ids,
            {action.id for action in REPRESENTATIVE_ACTIONS},
        )
        self.assertEqual(
            set(registry.ids),
            {action.id for action in (*REPRESENTATIVE_ACTIONS, *WORKFLOW_ACTIONS)},
        )
        for definition in registry.definitions:
            self.assertTrue(definition.id)
            self.assertTrue(definition.label)
            self.assertTrue(definition.description)
            self.assertTrue(definition.category)
            self.assertTrue(definition.command_id)
            self.assertIn(definition.metadata["migration_task"], {75, 76})
            with self.assertRaises(TypeError):
                definition.metadata["changed"] = True
        self.assertTrue(
            all(action.metadata["migration_task"] == 75 for action in REPRESENTATIVE_ACTIONS)
        )
        self.assertTrue(
            all(action.metadata["migration_task"] == 76 for action in WORKFLOW_ACTIONS)
        )

    def test_registry_covers_every_task76_workflow_family(self) -> None:
        registry = create_core_action_registry()
        workflow_ids = {action.id for action in WORKFLOW_ACTIONS}
        required_actions = {
            # Scene, selection, and visibility controllers.
            "scene.select_model",
            "scene.clear_selection",
            "scene.rename_selected",
            "scene.delete_selected",
            "scene.hide_selected",
            "scene.show_selected",
            "scene.isolate_selected",
            # Transform and section controllers.
            "transform.move",
            "transform.rotate",
            "transform.apply_numeric",
            "transform.reset",
            "section.add_plane",
            "section.compute",
            "section.clear_active",
            "section.clear_all",
            "section.delete_plane",
            # Stored/manual curves and regions.
            "curve.join",
            "curve.project",
            "curve.simplify",
            "curve.delete_selected",
            "manual_curve.create",
            "manual_curve.edit",
            "manual_curve.apply",
            "manual_curve.type_option",
            "manual_curve.sample_count_option",
            "manual_curve.corner_threshold_option",
            "manual_curve.placement_option",
            "region.start",
            "region.recompute",
            "region.extract_boundary",
            "region.rename",
            "region.max_triangles",
            "region.delete",
            # Preview surfaces, BREP, and analysis.
            "surface.fill",
            "surface.loft",
            "surface.four_curve_patch",
            "surface.brep_face",
            "surface.editable_brep_loft",
            "surface.rebuild_brep",
            "analysis.refresh",
            "analysis.mesh_deviation",
        }
        self.assertLessEqual(required_actions, workflow_ids)
        self.assertLessEqual(workflow_ids, set(registry.ids))
        self.assertEqual(
            {action.category for action in registry.definitions},
            {
                "Analysis",
                "BREP",
                "Curves",
                "Edit",
                "Manual Curve",
                "Regions",
                "Scene",
                "Sections",
                "Surfaces",
                "Transform",
                "View",
            },
        )
        self.assertEqual(
            {
                action.id.split(".", 1)[0]
                for action in WORKFLOW_ACTIONS
            },
            {
                "analysis",
                "curve",
                "manual_curve",
                "region",
                "scene",
                "section",
                "surface",
                "transform",
                "view",
            },
        )
        for action in WORKFLOW_ACTIONS:
            self.assertTrue(action.metadata["legacy_handler"])

    def test_every_action_condition_has_explicit_context_semantics(self) -> None:
        true_contexts = {
            ActionCondition.ALWAYS: ActionContext(),
            ActionCondition.HAS_SCENE_OBJECTS: ActionContext(has_scene_objects=True),
            ActionCondition.HAS_SCENE_SELECTION: ActionContext(has_scene_selection=True),
            ActionCondition.CAN_UNDO: ActionContext(can_undo=True),
            ActionCondition.CAN_REDO: ActionContext(can_redo=True),
            ActionCondition.HAS_MESH: ActionContext(mesh_loaded=True),
            ActionCondition.NOT_BUSY: ActionContext(busy=False),
            ActionCondition.SINGLE_SELECTION: ActionContext(selection_count=1),
            ActionCondition.MULTI_SELECTION: ActionContext(selection_count=2),
            ActionCondition.HAS_SECTION_PLANE: ActionContext(has_section_plane=True),
            ActionCondition.HAS_SECTION_RESULT: ActionContext(has_section_result=True),
            ActionCondition.HAS_CURVES: ActionContext(has_curves=True),
            ActionCondition.HAS_CURVE_SELECTION: ActionContext(selected_curve_count=1),
            ActionCondition.SINGLE_CURVE: ActionContext(selected_curve_count=1),
            ActionCondition.TWO_CURVES: ActionContext(selected_curve_count=2),
            ActionCondition.AT_LEAST_TWO_CURVES: ActionContext(selected_curve_count=2),
            ActionCondition.AT_LEAST_THREE_CURVES: ActionContext(selected_curve_count=3),
            ActionCondition.FOUR_CURVES: ActionContext(selected_curve_count=4),
            ActionCondition.SINGLE_CLOSED_CURVE: ActionContext(
                selected_curve_count=1,
                selected_curve_closed=True,
            ),
            ActionCondition.SINGLE_OPEN_CURVE: ActionContext(
                selected_curve_count=1,
                selected_curve_open=True,
            ),
            ActionCondition.SINGLE_EDITABLE_CURVE: ActionContext(
                selected_curve_count=1,
                selected_curve_editable=True,
            ),
            ActionCondition.HAS_SURFACE_SELECTION: ActionContext(
                selected_surface_count=1
            ),
            ActionCondition.SINGLE_SURFACE: ActionContext(selected_surface_count=1),
            ActionCondition.HAS_REGION: ActionContext(has_region=True),
            ActionCondition.HAS_BREP_SELECTION: ActionContext(selected_brep_count=1),
            ActionCondition.HAS_LOFT_FEATURE: ActionContext(has_loft_feature=True),
            ActionCondition.HAS_SOURCE_CURVES: ActionContext(has_source_curves=True),
            ActionCondition.CAN_TRANSFORM: ActionContext(can_transform=True),
            ActionCondition.TRANSFORM_ACTIVE: ActionContext(transform_active=True),
            ActionCondition.MANUAL_CURVE_ACTIVE: ActionContext(
                manual_curve_active=True
            ),
            ActionCondition.MANUAL_CURVE_IDLE: ActionContext(
                manual_curve_idle=True
            ),
            ActionCondition.MANUAL_CURVE_CREATING: ActionContext(
                manual_curve_creating=True
            ),
            ActionCondition.MANUAL_CURVE_EDITING: ActionContext(
                manual_curve_editing=True
            ),
            ActionCondition.CAN_ADD_MANUAL_POINT: ActionContext(
                can_add_manual_point=True
            ),
            ActionCondition.HAS_MANUAL_CONTROL_POINT: ActionContext(
                has_manual_control_point=True
            ),
            ActionCondition.REGION_TOOL_ACTIVE: ActionContext(region_tool_active=True),
            ActionCondition.HAS_REGION_BOUNDARY_CURVES: ActionContext(
                has_region_boundary_curves=True
            ),
            ActionCondition.SELECTED_REGION_BOUNDARY_CURVE: ActionContext(
                selected_region_boundary_curve=True
            ),
            ActionCondition.CAD_AVAILABLE: ActionContext(cad_available=True),
            ActionCondition.HAS_RUNTIME_BREP: ActionContext(has_runtime_brep=True),
        }
        self.assertEqual(set(true_contexts), set(ActionCondition))
        for condition, context in true_contexts.items():
            with self.subTest(condition=condition.value):
                self.assertTrue(context.satisfies(condition))

        default_context = ActionContext()
        for condition in ActionCondition:
            if condition in {ActionCondition.ALWAYS, ActionCondition.NOT_BUSY}:
                continue
            with self.subTest(false_condition=condition.value):
                self.assertFalse(default_context.satisfies(condition))
        self.assertFalse(ActionContext(busy=True).satisfies(ActionCondition.NOT_BUSY))

        referenced_conditions = {
            condition
            for action in create_core_action_registry().definitions
            for condition in (
                *action.enabled_when,
                *action.visible_when,
                *(() if action.checked_when is None else (action.checked_when,)),
            )
        }
        self.assertEqual(
            set(ActionCondition) - referenced_conditions,
            {
                ActionCondition.HAS_RUNTIME_BREP,
                ActionCondition.MULTI_SELECTION,
                ActionCondition.SINGLE_SURFACE,
            },
        )

    def test_representative_workflow_enablement_is_controller_neutral(self) -> None:
        registry = create_core_action_registry()
        cases = (
            (
                "scene.rename_selected",
                ActionContext(selection_count=1),
            ),
            (
                "transform.move",
                ActionContext(can_transform=True),
            ),
            (
                "section.compute",
                ActionContext(mesh_loaded=True, has_section_plane=True),
            ),
            (
                "curve.join",
                ActionContext(selected_curve_count=2),
            ),
            (
                "manual_curve.apply",
                ActionContext(manual_curve_editing=True),
            ),
            (
                "region.extract_boundary",
                ActionContext(mesh_loaded=True, has_region=True),
            ),
            (
                "surface.four_curve_patch",
                ActionContext(selected_curve_count=4),
            ),
            (
                "surface.brep_face",
                ActionContext(
                    selected_curve_count=1,
                    selected_curve_closed=True,
                    cad_available=True,
                ),
            ),
            (
                "analysis.mesh_deviation",
                ActionContext(mesh_loaded=True),
            ),
        )
        for action_id, enabled_context in cases:
            with self.subTest(action_id=action_id):
                self.assertFalse(registry.state(action_id, ActionContext()).enabled)
                self.assertTrue(registry.state(action_id, enabled_context).enabled)

        transform_idle = registry.state("transform.confirm", ActionContext())
        transform_active = registry.state(
            "transform.confirm",
            ActionContext(transform_active=True),
        )
        self.assertFalse(transform_idle.enabled)
        self.assertFalse(transform_idle.visible)
        self.assertTrue(transform_active.enabled)
        self.assertTrue(transform_active.visible)

    def test_manual_and_region_action_phases_preserve_adapter_enablement(self) -> None:
        registry = create_core_action_registry()
        idle = ActionContext(mesh_loaded=True, manual_curve_idle=True)
        creating = ActionContext(
            mesh_loaded=True,
            manual_curve_active=True,
            manual_curve_creating=True,
        )
        editing = ActionContext(
            mesh_loaded=True,
            manual_curve_active=True,
            manual_curve_editing=True,
            can_add_manual_point=True,
        )
        editing_point = replace(editing, has_manual_control_point=True)

        self.assertTrue(registry.state("manual_curve.create", idle).enabled)
        self.assertFalse(registry.state("manual_curve.create", creating).enabled)
        self.assertTrue(registry.state("manual_curve.remove_last", creating).enabled)
        self.assertFalse(registry.state("manual_curve.remove_last", editing).enabled)
        self.assertFalse(registry.state("manual_curve.add_point", creating).enabled)
        self.assertTrue(registry.state("manual_curve.add_point", editing).enabled)
        paused_creation = replace(creating, can_add_manual_point=True)
        self.assertTrue(
            registry.state("manual_curve.add_point", paused_creation).enabled
        )
        self.assertFalse(registry.state("manual_curve.delete_point", editing).enabled)
        self.assertTrue(
            registry.state("manual_curve.delete_point", editing_point).enabled
        )
        self.assertTrue(
            registry.state("manual_curve.toggle_point_type", creating).enabled
        )

        region_only = ActionContext(mesh_loaded=True, has_region=True)
        with_boundaries = replace(
            region_only,
            has_region_boundary_curves=True,
        )
        boundary_selected = ActionContext(
            manual_curve_idle=True,
            selected_region_boundary_curve=True,
        )
        self.assertFalse(
            registry.state("region.select_boundaries", region_only).enabled
        )
        self.assertTrue(
            registry.state("region.select_boundaries", with_boundaries).enabled
        )
        self.assertTrue(
            registry.state("region.convert_boundary", boundary_selected).enabled
        )

    def test_application_package_exports_task76_contracts(self) -> None:
        expected_exports = {
            "ActionCondition",
            "AppState",
            "ControllerBase",
            "SceneController",
            "SelectionController",
            "VisibilityController",
            "TransformController",
            "SectionController",
            "CurveController",
            "RegionController",
            "SurfaceController",
            "BrepController",
            "AnalysisController",
            "create_core_action_registry",
        }
        self.assertLessEqual(expected_exports, set(application.__all__))
        for export_name in expected_exports:
            self.assertTrue(hasattr(application, export_name), export_name)

    def test_registry_rejects_duplicate_and_unstable_ids(self) -> None:
        definition = ActionDefinition(
            id="test.valid",
            label="Valid",
            description="A valid action.",
            category="Test",
            shortcut=None,
            command_id="test.execute",
        )
        registry = ActionRegistry((definition,))

        with self.assertRaises(ValueError):
            registry.register(definition)
        with self.assertRaises(ValueError):
            ActionDefinition(
                id="Not Stable",
                label="Invalid",
                description="An invalid action.",
                category="Test",
                shortcut=None,
                command_id="test.execute",
            )

    def test_action_context_resolves_enablement_without_ui_state(self) -> None:
        registry = create_core_action_registry()
        empty = ActionContext()
        populated = ActionContext(
            has_scene_objects=True,
            has_scene_selection=True,
            can_undo=True,
            can_redo=True,
        )

        self.assertFalse(registry.state(ACTION_FRAME_SELECTED, empty).enabled)
        self.assertFalse(registry.state(ACTION_UNDO, empty).enabled)
        self.assertTrue(registry.state(ACTION_FRAME_ALL, empty).enabled)
        self.assertTrue(registry.state(ACTION_FRAME_SELECTED, populated).enabled)
        self.assertTrue(registry.state(ACTION_UNDO, populated).enabled)

    def test_checkable_contract_requires_explicit_checkable_state(self) -> None:
        with self.assertRaises(ValueError):
            ActionDefinition(
                id="test.checked",
                label="Checked",
                description="Invalid checked action.",
                category="Test",
                shortcut=None,
                command_id="test.checked",
                checked_when=ActionCondition.HAS_SCENE_SELECTION,
            )
        definition = ActionDefinition(
            id="test.checked",
            label="Checked",
            description="Valid checked action.",
            category="Test",
            shortcut=None,
            command_id="test.checked",
            checkable=True,
            checked_when=ActionCondition.HAS_SCENE_SELECTION,
        )
        self.assertTrue(
            definition.resolve(
                ActionContext(has_scene_selection=True)
            ).checked
        )


class ApplicationCommandTests(unittest.TestCase):
    def test_dispatcher_routes_and_publishes_typed_lifecycle_events(self) -> None:
        events = EventPublisher()
        received: list[CommandEvent] = []
        events.subscribe(CommandEvent, received.append)
        dependencies = _dependencies(events=events)
        dispatcher = CommandDispatcher(dependencies)
        dispatcher.register(
            "test.execute",
            lambda command, injected: CommandResult.ok(
                status=str(command.payload["status"]),
                changed=injected is dependencies,
            ),
        )

        result = dispatcher.dispatch(
            CommandRequest(
                "test.execute",
                action_id="test.action",
                payload={"status": "done"},
            )
        )

        self.assertTrue(result.success)
        self.assertTrue(result.changed)
        self.assertEqual(result.status, "done")
        self.assertEqual(
            [event.phase for event in received],
            [CommandPhase.STARTED, CommandPhase.COMPLETED],
        )
        self.assertTrue(received[-1].success)
        self.assertEqual(received[-1].action_id, "test.action")

    def test_dispatcher_returns_structured_unknown_and_rejected_failures(self) -> None:
        dispatcher = CommandDispatcher(_dependencies())

        unknown = dispatcher.dispatch(CommandRequest("missing.command"))
        self.assertFalse(unknown.success)
        self.assertIn("No handler", unknown.errors[0])

        def reject(_command: object, _dependencies: object) -> CommandResult:
            raise CommandRejected("Not available")

        dispatcher.register("test.reject", reject)
        rejected = dispatcher.dispatch(CommandRequest("test.reject"))
        self.assertFalse(rejected.success)
        self.assertEqual(rejected.errors, ("Not available",))

    def test_dispatcher_rejects_duplicate_handlers_and_invalid_results(self) -> None:
        dispatcher = CommandDispatcher(_dependencies())
        dispatcher.register(
            "test.execute",
            lambda _command, _dependencies: CommandResult.ok(),
        )
        with self.assertRaises(ValueError):
            dispatcher.register(
                "test.execute",
                lambda _command, _dependencies: CommandResult.ok(),
            )

        invalid_dependencies = _dependencies()
        phases: list[tuple[CommandPhase, bool | None, tuple[str, ...]]] = []
        invalid_dependencies.events.subscribe(
            CommandEvent,
            lambda event: phases.append((event.phase, event.success, event.errors)),
        )
        invalid = CommandDispatcher(invalid_dependencies)
        invalid.register("test.invalid", lambda _command, _dependencies: object())
        with self.assertRaises(TypeError):
            invalid.dispatch(CommandRequest("test.invalid"))
        self.assertEqual(
            phases,
            [
                (CommandPhase.STARTED, None, ()),
                (
                    CommandPhase.COMPLETED,
                    False,
                    ("Command handlers must return CommandResult.",),
                ),
            ],
        )

    def test_structured_result_carries_finite_framing_and_failure_contracts(self) -> None:
        request = ViewportRequest.frame_bounds(
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
            metadata={"target": "selection"},
        )
        result = CommandResult.ok(
            status="Framed",
            viewport_requests=(request,),
        )

        self.assertEqual(result.viewport_requests[0].kind, ViewportRequestKind.FRAME_BOUNDS)
        self.assertEqual(result.viewport_requests[0].minimum_bound, (1.0, 2.0, 3.0))
        self.assertEqual(result.viewport_requests[0].metadata["target"], "selection")
        with self.assertRaises(ValueError):
            ViewportRequest.frame_bounds(
                (float("nan"), 0.0, 0.0),
                (1.0, 1.0, 1.0),
            )
        with self.assertRaises(ValueError):
            CommandResult(success=True, errors=("contradiction",))


class ApplicationEventAndSelectionTests(unittest.TestCase):
    def test_event_subscription_is_typed_ordered_and_cancellable(self) -> None:
        publisher = EventPublisher()
        received: list[str] = []
        publisher.subscribe(ApplicationEvent, lambda event: received.append("base"))
        subscription = publisher.subscribe(
            StatusEvent,
            lambda event: received.append(event.message),
        )
        publisher.subscribe(
            ApplicationEvent,
            lambda event: received.append("late-base"),
        )

        publisher.publish(StatusEvent("first"))
        subscription.cancel()
        subscription.cancel()
        publisher.publish(StatusEvent("second"))

        self.assertEqual(
            received,
            ["base", "first", "late-base", "base", "late-base"],
        )
        self.assertFalse(subscription.active)

    def test_selection_snapshot_is_immutable_deduplicated_and_validated(self) -> None:
        snapshot = SelectionSnapshot.from_ids(
            ("curve:1", "curve:1", "curve:2"),
            kind=SelectionKind.CURVE,
        )

        self.assertEqual(snapshot.ids, ("curve:1", "curve:2"))
        self.assertEqual(snapshot.primary_id, "curve:1")
        self.assertTrue(snapshot.has_selection)
        with self.assertRaises(ValueError):
            SelectionSnapshot(snapshot.items, primary_id="missing")

    def test_dependency_container_has_explicit_ports_not_locator_lookup(self) -> None:
        dependencies = _dependencies()

        self.assertIsInstance(dependencies.events, EventPublisher)
        self.assertFalse(hasattr(dependencies, "get"))
        with self.assertRaises(TypeError):
            ApplicationDependencies(
                events=object(),
                selection=dependencies.selection,
                undo=dependencies.undo,
            )


class V3ActionContractTests(unittest.TestCase):
    def test_every_core_action_has_a_stable_command_identifier(self) -> None:
        command_ids = [definition.command_id for definition in CORE_ACTIONS]

        self.assertEqual(len(command_ids), len(set(command_ids)))
        self.assertTrue(all(command_ids))

    def test_registered_action_labels_are_unique_per_action_id(self) -> None:
        registry = create_core_action_registry()

        self.assertEqual(
            {item.id: item.label for item in registry.definitions},
            {item.id: item.label for item in CORE_ACTIONS},
        )


if __name__ == "__main__":
    unittest.main()

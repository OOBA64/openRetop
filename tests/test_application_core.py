from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from application.actions import (
    ACTION_FRAME_ALL,
    ACTION_FRAME_SELECTED,
    ACTION_REDO,
    ACTION_SHOW_ALL,
    ACTION_TOGGLE_VISIBILITY,
    ACTION_UNDO,
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

        self.assertEqual(
            set(registry.ids),
            {
                ACTION_FRAME_ALL,
                ACTION_FRAME_SELECTED,
                ACTION_SHOW_ALL,
                ACTION_TOGGLE_VISIBILITY,
                ACTION_UNDO,
                ACTION_REDO,
            },
        )
        for definition in registry.definitions:
            self.assertTrue(definition.id)
            self.assertTrue(definition.label)
            self.assertTrue(definition.description)
            self.assertTrue(definition.category)
            self.assertTrue(definition.command_id)
            self.assertEqual(definition.metadata["migration_task"], 75)
            with self.assertRaises(TypeError):
                definition.metadata["changed"] = True

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


class RepresentativeCompatibilityTests(unittest.TestCase):
    def test_legacy_wrappers_dispatch_only_the_registered_representative_actions(
        self,
    ) -> None:
        source_path = Path(__file__).resolve().parents[1] / "src" / "app" / "main_window.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        window = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "OpenRetopWindow"
        )
        expected = {
            "frame_all": "ACTION_FRAME_ALL",
            "frame_selected": "ACTION_FRAME_SELECTED",
            "show_all_scene_objects": "ACTION_SHOW_ALL",
            "toggle_selected_scene_objects": "ACTION_TOGGLE_VISIBILITY",
            "undo": "ACTION_UNDO",
            "redo": "ACTION_REDO",
        }

        for method_name, action_constant in expected.items():
            method = next(
                node
                for node in window.body
                if isinstance(node, ast.FunctionDef) and node.name == method_name
            )
            method_source = ast.get_source_segment(source, method)
            self.assertIn("_dispatch_action", method_source)
            self.assertIn(action_constant, method_source)

    def test_registered_menu_slice_uses_registry_labels(self) -> None:
        menu_source = (
            Path(__file__).resolve().parents[1] / "src" / "app" / "menus.py"
        ).read_text(encoding="utf-8")

        for action_constant in (
            "ACTION_FRAME_ALL",
            "ACTION_FRAME_SELECTED",
            "ACTION_SHOW_ALL",
            "ACTION_TOGGLE_VISIBILITY",
            "ACTION_UNDO",
            "ACTION_REDO",
        ):
            self.assertIn(f"_action_label(app, {action_constant})", menu_source)


if __name__ == "__main__":
    unittest.main()

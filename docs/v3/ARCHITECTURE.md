# openRetop V3 architecture

## Runtime flow

```text
PySide6 presentation
  -> stable ActionDefinition / structured pointer input
  -> WorkflowService / CommandDispatcher
  -> UI-independent controllers + authoritative AppState
  -> CommandResult, events, undo payloads, SceneSnapshot
  -> Qt/VTK presentation adapters
```

`src/main.py` selects the V3 Qt presentation. `bootstrap.create_application`
constructs one explicit, instance-scoped graph: state, events, action/command
registries, controllers, repositories/services, mesh-query cache, CAD adapter,
scene builder, and settings. There is no service locator or legacy shell.

## Layer ownership

| Layer | Owns | Forbidden |
| --- | --- | --- |
| Domain (`geometry`, `curves`, `sections`, `regions`, `surfaces`, core `mesh`, `analysis`) | values, algorithms, topology and feature records | widgets, dialogs, actors, filesystem policy |
| Application (`application`) | state, actions, commands, events, selection, workflow/controller coordination, undo | Tk/Qt, concrete VTK actors, dialogs/file pickers, presentation imports |
| Infrastructure (`infrastructure`, persistence/CAD/query adapters) | JSON/filesystem I/O, model import, proxy/export, CAD capability and accelerated queries | widgets and presentation ownership |
| Presentation (`presentation.qt`, `viewer`, `workbench_ui`) | Qt widgets/dialogs, VTK host/actors/picks/camera, menus/docks/inspector/tree, input/result translation | geometry algorithm or persistent state ownership |
| Bootstrap (`bootstrap`, `main`) | concrete construction and process lifecycle | modeling behavior and serialization logic |

Some historical package names contain mixed technical concerns (`project`,
`settings`, and `mesh`), but architecture tests enforce the critical inward
boundaries: guarded application/domain modules have no concrete UI imports,
and practical package/module cycles are prohibited.

## State and actions

`AppState` and domain collections are authoritative. Widgets display state and
dispatch intent; they do not shadow modeling arrays. `changed` means runtime
state changed, while `dirty` means a persistable project change occurred.
Controllers return structured `CommandResult` values with status,
warnings/errors, viewport/UI requests, metadata, and optional reversible undo
payloads.

Every retained command is declared in `CORE_ACTIONS`, has a unique stable
command ID, is registered in `CommandDispatcher`, and routes through
`WorkflowService`. Labels, menu placement, shortcuts, enablement, and checked
state remain presentation metadata, not handler identity.

## Viewport boundary

`SceneBuilder` creates immutable render records with stable IDs and deterministic
geometry/style/transform revisions. `SceneSynchronizer` creates, updates,
reuses, and removes actors through `VTKActorAdapter` and `ActorCache`.
`PickingService` returns structured mesh, scene-object, control-point, curve,
and handle results. `CameraController` applies named/framing requests only after
actors synchronize; ordinary refresh preserves the current camera.

VTK actor construction/mutation stays under `viewer`. The accelerated mesh
spatial index may use VTK data/locator primitives but does not own render actors.

## Persistence and compatibility

Project/settings DTO parsing and repositories are UI-free. Unknown top-level
project fields round-trip. Existing unversioned/version-1 projects migrate in
memory; optional new region and selection fields preserve old-file defaults.
Runtime CAD objects are deliberately not serialized and reload as
`rebuild_required` records.

## Reusable framework

`packages/workbench_ui` has no openRetop imports. Hosts supply action callbacks,
scene nodes, property fields, and tool state through its public contracts. It
can be built and run independently.

## Enforcement

`scripts/report_architecture_metrics.py --fail-on-new` and
`tests/test_architecture.py` enforce an empty UI-import allowlist, no practical
cycles, centralized scene-ID codecs, no legacy app imports, and release metrics.
`tests/test_task81_legacy_boundary.py` asserts the removed Tk shell/facade stay
absent.

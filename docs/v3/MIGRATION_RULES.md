# openRetop V3 Migration Rules

## Purpose

These rules turn the target architecture in
[ARCHITECTURE.md](ARCHITECTURE.md) into a behavior-preserving migration
protocol. They apply to every V3 extraction. Task-specific instructions take
precedence when they are stricter.

The refactor proceeds by adding an inward contract, adapting existing behavior
to it, and then moving ownership. A file move alone is not an architectural
extraction.

## Non-negotiable invariants

- Preserve modeling results unless the numbered task explicitly changes them.
- Preserve backward compatibility for existing `.openretop` files.
- Preserve Task 74 manual-curve controller/session behavior.
- Reuse the single accelerated `MeshQueryService`; do not add another cache
  or a brute-force projection path.
- Keep domain and application modules free of UI toolkit, actor, dialog, and
  file-picker operations.
- Keep VTK actor construction and mutation in viewport
  infrastructure/presentation adapters.
- Use the existing public VTK and CadQuery/OCP/OCCT stack. Do not add a
  proprietary CAD kernel.
- Preserve public compatibility wrappers until the task that explicitly removes
  them.
- Do not mix an architecture move with an unrelated algorithm rewrite, project
  format change, or new feature.
- Do not weaken tests or enlarge an allowlist merely to make a change pass.

If one of these cannot be preserved, stop and report the blocker.

## Standard extraction sequence

Use this sequence for one bounded workflow at a time:

1. **Characterize current behavior.** Identify entry points, state read/written,
   selection rules, errors/status, undo entry, dirty behavior, dependency
   invalidation, persistence fields, and viewport/UI side effects. Add focused
   characterization tests where coverage is missing.
2. **Identify authoritative state.** Reuse existing domain collections and
   session state. Do not create a shadow copy in a controller or Tk variable.
3. **Define the inward contract.** Add or reuse a stable action/command, typed
   input, result, event, and named dependency port. Keep toolkit and concrete
   adapter types out of the signature.
4. **Move orchestration, not algorithms.** The application handler/controller
   calls existing domain and infrastructure ports. Geometry algorithms keep
   their implementation and tests unless the task says otherwise.
5. **Add an outward adapter.** Bootstrap injects concrete dependencies.
   Presentation resolves widget/screen input, dispatches the command, and
   applies the result.
6. **Retain thin wrappers.** Existing `MainWindow`, menu, keybinding, and test
   entry points forward to the registered action/command without duplicating
   behavior.
7. **Verify equivalence.** Run focused domain/controller/adapter tests, project
   round trips when persisted state is touched, architecture checks, compileall,
   and the full unittest suite required by the task.
8. **Reduce debt.** Remove dead ownership only after all callers use the new
   path. Shrink the dependency baseline when a violation disappears.

Do not migrate adjacent workflows simply because they share a large legacy
method. Extract the seam needed by the numbered task and leave the rest
reviewable.

## Action rules

An action describes presentation-independent user intent.

- IDs are permanent, lower-case dotted identifiers such as
  `scene.toggle_visibility`.
- Labels are presentation text, not identity. Renaming a label must not change
  the ID or command.
- Each action supplies a non-empty label, description, category, command ID,
  optional shortcut, enablement and visibility conditions, checkable contract,
  and read-only metadata.
- Enablement/visibility are evaluated from typed `ActionContext`, not by
  reading Tk variables in the registry.
- Shortcut ownership converges on the registry. During migration, legacy
  keybinding settings may resolve to the same action ID through an adapter.
- Menu, toolbar, scene-browser, context-menu, and shortcut presentations reuse
  the same action definition where they represent the same intent.
- Duplicate labels are reported because they may reveal duplicate intent, but a
  duplicate label is not automatically an error when actions are genuinely
  distinct.
- Action metadata may aid migration/telemetry; it must not carry live services,
  actors, widgets, mutable state, or required control flow.

The Task 75 registry contains only Frame All, Frame Selected, Show All, Toggle
Visibility, Undo, and Redo. Broad registration belongs to the workflow migration
task, not this baseline task.

## Command and controller rules

- A command has a stable command ID, optional originating action ID, and
  immutable payload.
- Register handlers explicitly on an instance-scoped `CommandDispatcher`.
  Duplicate command IDs are errors.
- A handler accepts the command plus typed `ApplicationDependencies` and
  returns `CommandResult`.
- Expected unavailability or invalid user state returns a structured failure or
  raises `CommandRejected`. Unexpected programming/infrastructure exceptions
  are published as failed command completion and re-raised.
- Controllers accept explicit state and ports. They do not import
  `OpenRetopWindow`, Tk/Qt, dialogs, file pickers, VTK actors, or renderer
  objects.
- Controllers do not own a global undo stack. They return an undo payload or use
  the injected undo port for the specific history command.
- Commands must not use the event bus to locate a handler or obtain state.
- Avoid command-to-command dispatch inside a handler. Share a domain/application
  service when two use cases need the same operation.
- Maintain a single authoritative implementation. A compatibility wrapper
  forwards; it does not reimplement the old branch beside the new branch.

Task 75’s representative handlers remain in `OpenRetopWindow` as compatibility
adapters. Their direct UI/state calls are transitional and must not be copied
into new application handlers.

## Result rules

`CommandResult` fields have distinct meanings:

| Field | Meaning |
| --- | --- |
| `success` | The use case completed as an accepted outcome |
| `status` | Concise presentation-neutral status text |
| `warnings` | Non-fatal diagnostics |
| `errors` | Failure diagnostics; successful results cannot contain them |
| `changed` | Runtime model/application state changed |
| `dirty` | Persistable project state should be marked dirty |
| `viewport_requests` | Declarative refresh/render/frame work |
| `ui_requests` | Declarative presentation synchronization work |
| `undo_payload` | One reversible entry to install once |
| `metadata` | Read-only, optional diagnostic/context values |

Rules for applying results:

- Presentation applies requests; application code never calls a concrete
  renderer or widget.
- Installing an undo payload and marking dirty happen once. A migrated handler
  must not also push directly to the legacy stack.
- `changed=True` does not imply `dirty=True`. Camera movement,
  selection, transient tool previews, and status can change without changing
  the saved project.
- A failed result does not silently apply partial viewport/UI work. If a use
  case supports partial success, encode it explicitly with warnings and tested
  state semantics.
- Bounds requests contain finite world-space values. Screen coordinates and VTK
  objects do not cross this boundary.

## Event rules

- Publish the typed event that describes the completed state transition:
  state, selection, scene, dirty, command, active tool, or status.
- Publish immutable IDs/snapshots, not live mutable collections, widgets, or
  actors.
- Delivery is synchronous and registration ordered. A subscriber must finish
  quickly and must not assume asynchronous isolation.
- Events notify; commands request. Do not mutate authoritative state by
  publishing a notification event.
- Subscriptions have an explicit lifecycle and are cancelled when their owning
  adapter is disposed.
- Avoid event feedback loops. If handling an event causes a command, document
  and test the loop-prevention rule.
- Emit dirty/selection/scene events only after the authoritative state is
  coherent.

## Dependency injection rules

- Bootstrap owns construction of concrete services.
- Application defines the required protocol; infrastructure implements it.
- Add dependencies as named, typed fields on an explicit composition contract.
- No global mutable service registry, `get("service")`, module singleton, or
  callback accepting arbitrary `object` is an acceptable substitute.
- Do not pass `MainWindow` as a dependency. Pass the smallest port needed.
- Do not make a port toolkit-specific merely because the first implementation
  uses Tk or VTK.
- Ports should express application meaning (for example selection snapshot or
  undo capability), not mirror every method of a concrete implementation.
- Test controllers with small fakes/stubs implementing those same protocols.

## State and selection rules

- Existing domain collections remain authoritative until a task explicitly
  replaces them.
- Workflow/session state belongs in an application controller when it must
  survive widget refresh or be tested without a UI.
- Tk variables are adapters for presentation state only.
- Stable IDs cross boundaries; list/tree indices, widget IDs, and actor
  identities do not.
- Use `SelectionSnapshot` at the application boundary. Preserve ordering,
  primary selection, group expansion, and category semantics in explicit code.
- Selection changes generally are not project-dirty changes.
- Derived caches carry source identity/revision and are invalidated by the same
  source edits as before.
- A compatibility property may directly forward to controller/session state,
  but it may not maintain an independent shadow value.

## Undo, dirty state, and invalidation

Before migrating a mutating workflow, document:

1. the before snapshot;
2. the after snapshot;
3. the undo/redo operation name and ordering;
4. whether it dirties the project;
5. which dependent sections, curves, regions, surfaces, BREP records, previews,
   runtime CAD objects, and query/display caches are invalidated;
6. which selection and active-object state is restored.

Undo and redo must invoke the same synchronization/invalidation path as the
original mutation. Avoid serializing an entire project merely to create an undo
entry when the existing targeted snapshot is sufficient.

## Geometry, mesh-query, CAD, and viewport boundaries

- Keep geometry algorithms in their existing domain modules while moving
  orchestration.
- Projection and deviation use the injected/shared accelerated
  `MeshQueryService`. Never loop over every triangle as a migration shortcut.
- World/local transform conversion is explicit. Results that request framing use
  world-space finite bounds.
- Domain/application modules may not construct or mutate VTK actors, renderers,
  cameras, widgets, or interactors.
- The mesh spatial index may use VTK CommonCore/CommonDataModel and NumPy bridge
  types as infrastructure. Rendering/Interaction/Views/GUISupport imports are
  prohibited there.
- CAD calls cross a kernel-neutral port/result boundary. CadQuery/OCP/OCCT
  objects remain runtime infrastructure values and are not serialized directly.
- A viewport adapter may turn snapshots/requests into actors and camera calls;
  it must not become the owner of modeling state.

## Project and settings compatibility

- Treat [PROJECT_FORMAT_BASELINE.md](PROJECT_FORMAT_BASELINE.md) as the
  serialization contract.
- Moving classes or functions does not authorize a schema/version change.
- Continue to accept historical optional/missing fields and metadata according
  to the existing loaders.
- Preserve stable IDs, lineage/source references, visibility, transforms,
  editable feature records, and manual-curve metadata through save/load.
- Do not persist widgets, Tk variables, VTK actors/polydata, runtime CAD objects,
  command handlers, events, or dependency containers.
- File dialogs and overwrite/error prompts are presentation adapters. Path-based
  load/save/import/export operations are infrastructure/application contracts.
- Settings DTOs and parsing remain UI-free; color chooser and preference widgets
  remain presentation.
- Any intentional format change requires explicit task scope, compatibility
  fixtures, round-trip tests, version policy, and documentation before code.

## UI and compatibility wrappers

A retained wrapper is acceptable when it:

1. keeps the public name/signature needed by menus, keybindings, or tests;
2. converts presentation input to typed command input;
3. dispatches exactly one application use case;
4. applies the structured result; and
5. contains no duplicate workflow branch.

Dialogs gather/present information. The operation behind them receives a path or
typed decision and is testable without opening a dialog. Scene-browser and
viewport adapters translate stable IDs rather than reaching around a controller
to mutate a collection.

## Module movement and imports

- Prefer a forwarding import or compatibility wrapper when external/internal
  callers still use an old module path.
- Move one ownership boundary at a time and update tests in the same change.
- Do not introduce a dependency cycle to avoid a temporary compatibility
  module. Put the shared contract inward.
- Avoid import-time construction of windows, renderers, dispatchers, services,
  or mutable state.
- Type-checking imports still count as dependencies; protocols belong in the
  inward layer that owns the need.
- Local imports are not an acceptable way to conceal a forbidden dependency or
  cycle.

## Architecture baseline policy

`tests/architecture_dependency_baseline.json` is a ratchet:

- known Task 75 violations are listed explicitly and remain visible;
- the test reports current violations and subtracts the baseline;
- any new forbidden import or practical package cycle fails;
- when a known violation is removed, remove its baseline entry in the same
  change;
- changing a path does not justify transferring the allowance to another file;
- adding an allowance requires explicit architecture justification in the
  numbered task and an update to the dependency audit.

The baseline currently contains six Tk import occurrences in the mixed legacy
`app` package and no cycle allowance. Viewer Tk/VTK imports are presentation
dependencies, not violations. VTK CommonCore/CommonDataModel/NumPy bridge
imports in mesh spatial-query infrastructure are also intentionally allowed.

## Required verification for an extraction

At minimum:

- focused tests for the moved domain/controller contract;
- success, failure, warnings, dirty, undo, event, and missing-dependency cases
  appropriate to the workflow;
- compatibility-wrapper or presentation integration tests;
- project round-trip/backward-compatibility tests when persisted data is touched;
- accelerated-query tests when mesh projection/query behavior is touched;
- architecture dependency and cycle tests;
- `python -m compileall -q src`;
- the complete unittest suite with `PYTHONPATH=src`.

Record exact commands/results, files changed, risks, known issues, and the next
task starting point in `docs/v3/STATUS.md`.

## Review checklist

Before declaring a migration complete, answer yes to all applicable questions:

- Is authoritative state owned in exactly one place?
- Can the workflow run in a test without Tk/Qt or a VTK render window?
- Are dependencies named and typed?
- Does the handler return a complete structured result?
- Are undo, dirty, selection, and dependency invalidation preserved?
- Are dialogs/actors/file pickers outside domain and application?
- Does projection still use the shared accelerated query service?
- Do old public wrappers forward without duplicate logic?
- Do old project files still load and round-trip as documented?
- Did the architecture violation count stay flat or decrease, with no cycle?
- Were only the numbered task’s workflows changed?

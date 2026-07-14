# openRetop V3 Architecture

## Status and scope

This document is the authoritative architecture baseline established by Task 75.
It defines dependency direction and boundary contracts for subsequent V3 work.
The repository is intentionally in a transitional state: the rules below describe
the target architecture, while [DEPENDENCY_AUDIT.md](DEPENDENCY_AUDIT.md)
records the known differences in the current tree.

Task 75 adds the application foundation and a representative action slice. It
does not migrate every workflow, split the complete viewport, remove Tk, change
the project format, or alter modeling algorithms.

## Architectural principles

1. Domain behavior is independent of UI toolkits, file dialogs, render actors,
   persistence mechanisms, and application globals.
2. Application code coordinates use cases through explicit state and typed
   ports. It describes presentation work as requests; it does not perform that
   work.
3. Infrastructure implements technical details such as project/settings I/O,
   accelerated mesh queries, CAD-kernel access, and VTK-backed adapters.
4. Presentation translates user and viewport input into application commands,
   and translates results and events into widgets, actors, status, and camera
   operations.
5. Bootstrap is the only layer that constructs the complete object graph and
   selects concrete implementations.
6. Dependencies point inward. No layer may recover an outward dependency through
   callbacks typed as `object`, a string-key service locator, import-time
   globals, or circular imports.
7. Existing modeling behavior, accelerated projection, undo semantics, and
   `.openretop` compatibility are invariants during the refactor.

## Layers and allowed dependencies

An arrow means “may import or call.” Standard-library and approved numerical
libraries are omitted.

```text
bootstrap -----> presentation -----> application -----> domain
    |                 |                    |
    |                 +-------------------> domain
    +----------> infrastructure ----------> domain
    |                 |
    |                 +-------------------> application ports
    +-------------------------------------> application/domain
```

There are no reverse arrows and no edge between presentation and a concrete
infrastructure implementation. When presentation needs a technical capability,
the application defines a port and bootstrap injects its implementation. A
presentation adapter may use a toolkit-specific viewport facade, but workflow
controllers must not.

| Layer | Owns | May depend on | Must not depend on |
| --- | --- | --- | --- |
| Domain | Modeling values, invariants, geometry algorithms, topology/state transitions, feature dependency rules | Domain modules, standard library, approved numerical libraries | Application, infrastructure, presentation, bootstrap; Tk/Qt; dialogs; VTK rendering/actors; filesystem policy |
| Application | Actions, commands/use cases, controller/session coordination, selection contracts, results, events, ports | Domain and other application modules | Concrete persistence, CAD, VTK, Tk/Qt, dialogs/file pickers, presentation objects, global service lookup |
| Infrastructure | Persistence adapters, settings storage, import/export, accelerated mesh-query implementation, public CadQuery/OCP/OCCT adapters, toolkit-specific viewport services | Domain and application ports/contracts | Presentation or bootstrap; proprietary kernels; workflow/UI ownership |
| Presentation | Tk/Qt widgets, menus, key translation, scene-browser views, status/dialog adapters, viewport host and actor adapters | Application contracts and, where needed, immutable domain values/read models | Domain workflow orchestration, persistence/CAD implementation details, application composition, geometry algorithm ownership |
| Bootstrap | Process entry point and composition root | Every layer for construction and wiring only | Modeling/workflow behavior, serialization logic, widget or actor implementation |

Direct presentation-to-domain reads are permitted for immutable values and view
models during migration. State-changing presentation code must dispatch an
application command. The preferred final path is a purpose-built application
snapshot rather than exposing mutable collections.

## Layer responsibilities

### Domain

The domain contains openRetop’s modeling language and deterministic computation:
triangle mesh values and adjacency, sections, stored and manual curves, regions,
surface/BREP feature records, transforms and geometry math, and analysis values.
Domain APIs accept explicit values and return values or domain-specific errors.

Domain code must not:

- import `tkinter`, a Qt binding, `MainWindow`, dialogs, or file pickers;
- create or mutate VTK actors, renderers, cameras, interactors, or widgets;
- load/save project or settings files;
- select a concrete CAD backend;
- create a second mesh-query cache or replace accelerated projection with a
  brute-force search.

Pure VTK data operations are not automatically domain operations. The current
VTK spatial index and display-proxy implementation are infrastructure even
though they live under `mesh`.

### Application

The application layer owns toolkit-neutral use-case contracts. Task 75 creates:

- `application.actions`: stable action definitions, action conditions, resolved
  state, and the registry;
- `application.commands`: command protocol, immutable request, rejection type,
  and instance-scoped dispatcher;
- `application.results`: structured results, viewport requests, UI requests,
  and the undo-payload protocol;
- `application.events`: typed synchronous events and cancellable
  subscriptions;
- `application.selection`: immutable selection values and the selection-provider
  port;
- `application.dependencies`: explicitly named event, selection, and undo
  ports.

Application services and controllers must receive dependencies in constructors
or command parameters. `ApplicationDependencies` deliberately has fixed,
typed fields and no `get(name)` operation. New dependencies are added as named
ports, not hidden in metadata or a global dictionary.

### Infrastructure

Infrastructure owns details that can be replaced without changing a use case:

- JSON and filesystem project/settings adapters;
- mesh loading and display-proxy generation;
- the cached `MeshQueryService`/`MeshSpatialIndex` implementation;
- CadQuery/OCP/OCCT detection, construction, and STEP export;
- VTK-backed camera, picking, scene synchronization, and actor factories as
  those are split from the legacy viewport.

VTK actor construction and mutation belong only in viewport
infrastructure/presentation adapters. VTK CommonCore/CommonDataModel data
structures used by the accelerated mesh-query implementation are allowed there;
VTK rendering, interaction, view, GUI-support, and actor APIs are not.

### Presentation

Presentation owns toolkit state and translation:

- Tk/Qt widgets and variables;
- menu, keybinding, dialog, and scene-browser views;
- pointer/keyboard interpretation and screen-space picking adapters;
- applying `ViewportRequest` and `UIRequest`;
- showing warnings/errors/status and rendering scene snapshots;
- VTK host/widget and actor adapters.

Presentation may preserve public compatibility methods while migration is in
progress, but those methods must become thin adapters. A widget callback must
not become the authoritative owner of modeling state.

### Bootstrap

Bootstrap creates the root window, state repositories, event publisher, action
registry, dependency ports, command dispatcher, controllers, infrastructure
implementations, and presentation adapters. It performs wiring and lifecycle
management only. `src/main.py` is the current entry point; much of composition
still occurs in `OpenRetopWindow.__init__` and is recorded as migration debt.

## Command and action flow

```text
menu/key/widget
    -> ActionDefinition + ActionContext
    -> CommandRequest
    -> CommandDispatcher
    -> command handler(explicit ApplicationDependencies)
    -> CommandResult + typed events
    -> presentation applies status/dirty/undo/UI/viewport requests
```

An action is discoverable user intent. Its stable action ID is independent of
its label, shortcut, menu placement, and concrete handler. A command ID names
the use case. Multiple presentations may invoke the same command, and a command
may exist without a visible action.

`ActionDefinition` includes:

- stable lower-case dotted `id`;
- label, description, category, and optional shortcut;
- stable command/handler ID;
- typed enablement and visibility conditions;
- checkable/checked-state contract;
- read-only metadata.

`CommandResult` is the complete toolkit-neutral outcome. It carries success,
status, warnings/errors, whether state changed, whether persisted state is
dirty, viewport/UI requests, optional undo payload, and read-only metadata.
Handlers return expected failures as structured results (or
`CommandRejected`); unexpected exceptions remain exceptions after a failed
command event is published.

Task 75 registers exactly this representative slice:

| Action ID | Command ID | Legacy wrapper |
| --- | --- | --- |
| `view.frame_all` | `viewport.frame_all` | `frame_all` |
| `view.frame_selected` | `viewport.frame_selected` | `frame_selected` |
| `scene.show_all` | `scene.show_all` | `show_all_scene_objects` |
| `scene.toggle_visibility` | `scene.toggle_visibility` | `toggle_selected_scene_objects` |
| `edit.undo` | `history.undo` | `undo` |
| `edit.redo` | `history.redo` | `redo` |

The legacy methods and menu callbacks remain callable. Their handlers are still
hosted by `OpenRetopWindow` to preserve behavior; moving the remaining workflow
ownership is outside Task 75.

## Event contract

`EventPublisher` delivers events synchronously in subscription order.
Subscriptions are typed by event class and cancellation is idempotent. The
defined event families are:

- state changed;
- selection changed;
- scene changed;
- dirty changed;
- command started/completed;
- active tool changed;
- status.

Events notify observers after an authoritative change. They are not commands,
mutable shared state, or a substitute for explicit dependencies. Publishers
must provide immutable snapshots/identifiers rather than Tk variables, actors,
or live mutable collections. A subscriber must not assume delivery on a GUI
thread unless a presentation adapter explicitly provides that guarantee.

## State and ownership

- Domain collections and session values are authoritative for modeling data.
- Application controllers own workflow state that is not inherent to a widget.
- Tk variables own presentation state only.
- Selection crosses the application boundary as `SelectionSnapshot` with
  stable IDs and an optional primary ID.
- Undo entries describe reversible domain/application mutations. The application
  result may return an undo payload; the adapter installs it once.
- `changed` means the command changed runtime state. `dirty` means a
  persistable project change occurred. They are intentionally distinct.
- Viewport state is not project/model state unless the project baseline
  explicitly says it is serialized.

Task 74’s `ManualCurveController` and `ManualCurveSessionState` remain the
behavioral baseline for manual-curve work. They must continue to use the shared,
accelerated `MeshQueryService`.

## Physical package map at Task 75

Physical directories do not yet map one-to-one to layers.

| Current package/module | Current logical role | Migration note |
| --- | --- | --- |
| `application` | Application | New clean core; UI imports are forbidden |
| `geometry`, most of `curves`, `sections`, `regions`, `surfaces`, `analysis` | Domain | Keep algorithms stable while boundaries move |
| `mesh.triangle_mesh`, `mesh.adjacency` | Domain | Value/topology operations |
| `mesh.loader`, `mesh.display_proxy`, `mesh.spatial_index`, `mesh.query_service` | Infrastructure | Package is intentionally mixed today |
| `cad_kernel` | Infrastructure | Public CadQuery/OCP/OCCT adapter |
| `project`, `settings` | Infrastructure plus serialization DTOs | Must stay UI-free and format-compatible |
| `app` | Mixed legacy presentation, composition, and application/domain helpers | Primary extraction seam; six Tk imports are baselined |
| `viewer` | Presentation plus VTK viewport infrastructure | Actor/camera/picking split is deferred |
| `main.py` | Bootstrap | Composition currently delegates to the legacy window |

This table classifies existing code; it is not permission to add new mixed
modules.

## Boundary contracts for external technology

- NumPy is an approved value/computation dependency in domain code.
- The public VTK stack remains the rendering and accelerated spatial-query
  technology. Rendering/interaction APIs stay at the viewport boundary.
- CadQuery/OCP/OCCT remain the supported CAD-kernel implementations. Domain and
  application code consume kernel-neutral values/results.
- Tk remains the current presentation toolkit during V3 migration. No task may
  remove it incidentally.
- JSON and filesystem access remain infrastructure concerns.
- Proprietary CAD dependencies are prohibited.

## Compatibility invariants

Every architectural extraction must preserve:

- loading existing `.openretop` files and the documented project format;
- stable stored IDs, metadata, transforms, visibility, feature lineage, and
  manual-curve data;
- Task 74 manual-curve controller/session behavior;
- undo/redo ordering and dirty-state semantics;
- current geometry algorithms unless a task explicitly changes them;
- shared accelerated mesh query/projection;
- existing public wrappers used by menus, keybindings, and tests until their
  scheduled removal.

## Enforcement

`scripts/report_architecture_metrics.py` provides the current structural
snapshot. Architecture tests compare forbidden imports and practical package
cycles with the explicit
`tests/architecture_dependency_baseline.json` allowlist. Existing entries are
visible debt; they do not authorize equivalent imports elsewhere. A new
violation or cycle fails. Removing debt requires shrinking the baseline.

See [MIGRATION_RULES.md](MIGRATION_RULES.md) for the change protocol and
[DEPENDENCY_AUDIT.md](DEPENDENCY_AUDIT.md) for the Task 75 findings.

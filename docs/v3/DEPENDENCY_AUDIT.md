# openRetop V3 Dependency Audit

## Audit baseline

This audit captures the repository at Task 75, after Task 74’s manual-curve
controller/session extraction and after the Task 75 application primitives were
added. It covers all 70 Python files under `src` and all 41 Python test/support
files under `tests`.

The audit used:

- AST/static import inspection of every production module;
- production package and module dependency graphs;
- strongly connected-component checks for practical cycles;
- UI-toolkit policy checks for domain/application and protected infrastructure;
- review of `OpenRetopWindow`, `AppState`, manual-curve controller/session,
  menus, scene browser, keybindings, undo, transforms, mesh/query/projection,
  sections, curves, regions, surfaces/BREP, analysis, project, settings, viewer,
  and their tests;
- the repeatable metrics implementation in
  `scripts/report_architecture_metrics.py`.

Run the current report instead of copying numbers from this document:

```powershell
python scripts/report_architecture_metrics.py
```

## Executive findings

- The production package graph has **no practical multi-package cycle**.
- The production module graph has **no practical multi-module cycle**.
- The new `application` package has **no UI-toolkit or VTK presentation
  imports**.
- Protected `project`, `settings`, `cad_kernel`,
  `mesh/query_service.py`, and `mesh/spatial_index.py` modules have **no
  prohibited UI/rendering imports**.
- Six Tk import statements in the mixed legacy `app` package are the complete
  human-readable Task 75 allowlist.
- VTK CommonCore/CommonDataModel and NumPy bridge imports in mesh spatial/query
  infrastructure are intentional and are not presentation violations.
- `OpenRetopWindow` remains the dominant composition/workflow hotspot.
  `EmbeddedVTKViewport` remains a combined widget, scene, actor, picking, and
  camera hotspot.
- Physical packages do not yet equal the V3 layers. The allowlist is a ratchet,
  not evidence that the current layout is finished.

## Structural snapshot

The source tree contains 37,410 physical Python lines at this
baseline. The largest current modules are:

| Module | Physical lines | Audit significance |
| --- | ---: | --- |
| `app/main_window.py` | 14,703 | Tk bootstrap, state owner, workflow orchestration, commands, dialogs, persistence, viewport coordination |
| `viewer/embedded_viewport.py` | 3,598 | Tk host, VTK actors, picking, scene synchronization, camera/framing |
| `app/manual_curve_controller.py` | 1,671 | UI-agnostic Task 74 controller, still in the legacy package |
| `curves/manual_curve.py` | 1,493 | Manual-curve domain/storage/sampling behavior |
| `surfaces/surface_preview.py` | 1,372 | Surface preview algorithms and query integration |
| `app/scene_browser.py` | 1,331 | Tk tree plus scene-node mapping/presentation |
| `project/project_io.py` | 1,010 | Project schema parsing and compatibility |

`OpenRetopWindow` itself contains 547 methods in this snapshot. These values
are descriptive only; the metrics script is authoritative as the tree changes.

## Current package dependency graph

Edges below mean “imports.” Same-package edges and standard/third-party imports
are omitted.

| Importing package | Imports current production packages |
| --- | --- |
| `analysis` | `mesh` |
| `app` | `application`, `cad_kernel`, `curves`, `geometry`, `mesh`, `project`, `regions`, `sections`, `settings`, `surfaces`, `viewer` |
| `application` | none outside `application` |
| `cad_kernel` | `curves` |
| `curves` | `mesh` |
| `geometry` | none outside `geometry` |
| `mesh` | `geometry` |
| `project` | `curves`, `sections`, `surfaces` |
| `regions` | `mesh` |
| `sections` | `geometry` |
| `settings` | `mesh` |
| `surfaces` | `curves`, `mesh` |
| `viewer` | `curves`, `geometry`, `mesh`, `regions`, `sections`, `surfaces` |
| `main.py` | `app` |

The graph is acyclic today. The longest practical inward chains include
`main -> app -> cad_kernel -> curves -> mesh -> geometry` and
`main -> app -> project -> surfaces -> curves -> mesh -> geometry`.
This is a useful safety property to preserve; it does not mean every edge has
reached its target layer.

## Package and workflow audit

| Area | Current responsibility and tests | Boundary assessment |
| --- | --- | --- |
| `main.py` | Starts `app.main_window.run_app` | Bootstrap entry is small; concrete composition still lives in the window |
| `app/main_window.py` | Owns root Tk window, state/services, workflow handlers, persistence/dialog calls, undo, result application, and viewport coordination; covered by UI/integration and workflow tests | Mixed bootstrap + presentation + application; primary dependency hotspot |
| `app/app_state.py`, object/transform state | Aggregates curve, section, region, surface/BREP, loft/four-boundary and transform state; covered by state/transform tests | Domain/application state physically under legacy presentation package |
| Manual curve | `ManualCurveController` coordinates the shared query service; `ManualCurveSessionState` owns session values; extensive controller/session/V2/manual tests | Task 74 seam is UI-agnostic and behavior-preserving; controller path remains transitional |
| Menus/keybindings/preferences | Tk menu/dialog construction, shortcut parsing and settings; menu labels now consume representative action definitions | Presentation behavior remains in `app`; keybind registry convergence is incomplete |
| Scene browser/selection | Tk tree, stable node-ID helpers, labels, grouping, visibility and selection bridging; label and UI tests exist | Node mapping is entangled with Tk view and mutable collections |
| Undo | Protocol, callback command, stack; focused tests | UI-free implementation, but legacy workflows often push/synchronize directly in MainWindow |
| Transforms | Pure NumPy transform math plus active transform state; focused tests | Good extraction candidate; workflow/tool ownership remains in MainWindow |
| Mesh/query/projection | Mesh values/adjacency plus loader, proxy, cached VTK spatial locator and `MeshQueryService`; spatial, display, loader, adjacency, curve projection tests | Mixed domain/infrastructure package. Computational VTK is allowed; shared accelerated cache is mandatory |
| Sections/curves/regions | Domain collections and algorithms with broad focused coverage | UI-free; some algorithms type against concrete mesh-query infrastructure |
| Surfaces/BREP | Surface records/features, preview algorithms, runtime CAD coordination in MainWindow; surface/BREP/CAD tests | Domain records are UI-free; application orchestration and runtime cache ownership remain legacy |
| CAD kernel | Public CadQuery/OCP/OCCT detection/build/export and kernel-neutral result types; focused backend/wire/face/loft/export tests | Infrastructure, UI-free. Dependency on manual-curve domain topology is inward and allowed |
| Analysis | Point-to-mesh deviation uses query/spatial infrastructure | UI-free, but lacks a dedicated analysis test module and depends on a concrete query implementation |
| Project | DTOs, JSON compatibility parser/writer, conversion to/from domain collections; project I/O/state tests | UI-free infrastructure; compatibility is high-risk and must remain stable |
| Settings | DTOs and JSON parser/writer; settings tests | UI-free, but default proxy quality/normalization are imported from `mesh.display_proxy` |
| Viewer | Tk/VTK host, actor creation, scene updates, picking, framing/camera plus pure overlay geometry; scene/overlay tests | Correct outer-layer technology, but one large module combines several adapter responsibilities |
| `application` | Action registry, commands/dispatcher, typed results/events/selection and explicit dependencies; `test_application_core.py` | Clean Task 75 application foundation with inward-only self-dependencies |
| Architecture tests | Scanner policy, readable baseline, cycle detection, metrics dimensions and duplicate-label characterization | New violations fail while existing debt remains visible |

## UI dependency policy

The scanner treats these as UI toolkit prefixes:

- `tkinter`;
- PyQt5/PyQt6;
- PySide2/PySide6;
- wx;
- kivy;
- pyvista.

It also treats VTK GUI support, interaction, rendering, and views packages as
presentation dependencies. The guarded production areas are:

- domain/application candidates: `analysis`, `app`, `application`,
  `curves`, `geometry`, `mesh`, `regions`, `sections`, `surfaces`;
- protected infrastructure: `project`, `settings`, `cad_kernel`;
- protected query modules: `mesh/query_service.py` and
  `mesh/spatial_index.py`.

`viewer` is deliberately outside that prohibition because it is a
presentation/viewport adapter. This does not permit VTK actors in a controller
or domain module.

## Explicit Task 75 allowlist

`tests/architecture_dependency_baseline.json` contains exactly:

| Path | Module | Count | Reason |
| --- | --- | ---: | --- |
| `app/main_window.py` | `tkinter` | 2 | Legacy Tk presentation and bootstrap shell |
| `app/menus.py` | `tkinter` | 1 | Legacy Tk menu adapter |
| `app/preferences_dialog.py` | `tkinter` | 2 | Legacy Tk settings dialog |
| `app/scene_browser.py` | `tkinter` | 1 | Legacy Tk scene-tree adapter |

Package-cycle and module-cycle allowlists are empty. There is no wildcard path,
package-wide count, or allowance for a second UI toolkit.

The test subtracts this exact multiset from actual findings:

- fewer occurrences pass and should be followed by shrinking the baseline;
- the same occurrences pass and remain reported as known debt;
- any additional path/module/count fails;
- any practical package or module cycle fails.

## Allowed technology edges that are not violations

- `mesh.spatial_index` uses `vtkmodules.util.numpy_support`,
  `vtkCommonCore`, and `vtkCommonDataModel` for accelerated closest-point
  lookup. These are computational infrastructure imports.
- `mesh.display_proxy` uses VTK data/filter modules to build display geometry.
  It does not construct or mutate actors.
- `viewer.embedded_viewport` uses Tk and VTK rendering/interaction modules as
  an outer adapter.
- `cad_kernel` dynamically selects public CadQuery/OCP/OCCT implementations.
- Domain numerical code uses NumPy.

These decisions are narrow. For example, allowing `vtkCommonDataModel` in the
query implementation does not allow `vtkActor`, a renderer, interactor, or
camera there.

## Architectural debt beyond the allowlist

The static UI ratchet catches high-value violations but is not the complete
architecture:

1. **Composition is in presentation.** `OpenRetopWindow.__init__` constructs
   domain state, settings, query service, manual controller, undo stack, event
   publisher, action registry, dependencies, dispatcher, and viewport. Target
   bootstrap must own this graph.
2. **Workflow ownership is concentrated.** MainWindow handlers still mutate
   collections, push undo entries, mark dirty, invalidate dependents, open
   dialogs, and refresh actors/widgets.
3. **The representative commands are transitional.** The six wrappers dispatch
   registered commands, but their handlers remain bound MainWindow methods to
   preserve behavior. New controllers must not copy that pattern.
4. **Raw presentation inputs remain broad.** The viewport and scene browser read
   many domain collections directly. Declarative view/scene snapshots are not
   established yet.
5. **Mesh is a mixed package.** Value/topology code and VTK-backed query/display
   infrastructure share `mesh`, so package name alone does not identify a
   layer.
6. **Domain algorithms name concrete query classes.**
   `curves.projection`, `surfaces.surface_preview`, and
   `analysis.deviation` import mesh query/spatial implementations. A future
   inward query protocol should preserve the existing service and cache.
7. **Settings imports display-proxy policy.** `settings_data` and
   `settings_io` import default/normalization behavior from
   `mesh.display_proxy`. This is UI-free but couples two infrastructure areas.
8. **Viewport responsibilities are combined.** Tk hosting, actor factories,
   caches, scene synchronization, picking, tool previews, overlays, and
   camera/framing share one 3,599-line module.
9. **App is a mixed physical package.** UI-free manual-curve, transform, undo,
   and state code lives beside Tk modules, which is why path-based allowances
   must remain exact.

These are documented migration targets, not permission to address the next
numbered task during Task 75.

## Representative application dependency review

The new package’s internal edges are:

```text
actions       -> standard library only
selection     -> standard library only
results       -> standard library only
events        -> selection
dependencies  -> events, selection
commands      -> dependencies, events, results
__init__      -> public application contracts
```

There is no import from `application` to `app`, viewer, project, settings,
CAD, mesh, Tk, Qt, or VTK. `ApplicationDependencies` has named
`events`, `selection`, and `undo` fields and intentionally exposes no
string-key lookup.

The legacy presentation edge points inward: MainWindow creates the registry,
publisher, dependency adapter, and dispatcher; menus reuse registry labels; the
six legacy wrapper methods dispatch their action IDs; the result adapter applies
undo, dirty, UI, status, and viewport requests.

## Test audit and remaining risk

Current tests directly cover the application core, state collections, Task 74
manual curves, keybindings, scene labels, undo, transforms, mesh loader/query/
spatial/display/adjacency, section/curve/region/surface/BREP algorithms, CAD
backends/export, project/settings serialization, and viewer scene/overlays.

Risk remains highest where behavior spans MainWindow, viewport, persistence, and
runtime caches. In particular:

- UI tests cannot prove every large MainWindow branch is independent;
- framing/project-load camera behavior is a known regression baseline, not fixed
  by Task 75;
- analysis has no dedicated test module;
- optional CAD/VTK behavior depends on environment availability;
- static import analysis cannot detect imports built dynamically from arbitrary
  strings or runtime service lookup.

The architecture scanner includes synthetic characterization tests proving that
new Tk/Qt/PyVista/VTK presentation imports and simple practical cycles are
detected. Code review remains responsible for semantic boundary violations that
an import scanner cannot see.

## Required direction from this baseline

- Keep the cycle count at zero.
- Keep protected project/settings/CAD/query modules free of presentation
  imports.
- Keep `application` free of UI and concrete infrastructure.
- Do not transfer a removed allowlist count to another path.
- Move workflow ownership inward behind typed commands/results/events while
  retaining thin legacy wrappers.
- Move full composition to bootstrap when its numbered task permits it.
- Preserve the shared accelerated query service and project compatibility
  throughout.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the target layer graph and
[MIGRATION_RULES.md](MIGRATION_RULES.md) for the extraction protocol.

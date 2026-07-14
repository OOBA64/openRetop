# V3 Feature Inventory

This document is the Task 75 baseline of behavior that the V3 refactor must
preserve. It describes the repository as audited on 2026-07-13, after Task 74
and before any broad workflow migration. It is an inventory, not a proposal for
new modeling features.

The implementation remains a runnable Tk/VTK desktop application. Most
user-facing orchestration is still in `app.main_window.OpenRetopWindow`; the new
`application` package supplies UI-agnostic contracts and is used by only the
representative Task 75 action slice. "Legacy" below means "not yet migrated to
those contracts", not deprecated or unsupported.

## Product capability baseline

| Area | Behavior that exists now | Primary production owners | Principal test anchors | V3 status at Task 75 |
|---|---|---|---|---|
| Application shell | One Tk main window with menu bar, workbench selector, scrolling context sidebar, status strip, staged progress dialogs, and embedded VTK viewport. Workbenches are Scene, Transform, Sections, Curves, Surfaces, Manual RE, and Analysis. | `main.py`, `app/main_window.py`, `app/menus.py`, `app/preferences_dialog.py` | `test_main_window_ui.py` | Bootstrap and presentation are still combined in `OpenRetopWindow`; no UI redesign is part of Task 75. |
| Aggregate state | `AppState` owns the mesh object, primary selection family, transform session, section planes/results, curves, preview surfaces, BREP records, editable loft/four-boundary features, and the active region. Clearing selection preserves model records; clearing sections removes dependent result/curve/surface records while retaining section planes. | `app/app_state.py`, collection modules under `curves`, `sections`, `regions`, and `surfaces` | `test_app_state.py` and collection-specific tests | Existing mutable aggregate is retained. The new immutable `SelectionSnapshot` is only a command boundary adapter. |
| Project lifecycle | New, open, save, save-as, dirty prompts, title/path tracking, metadata-only projects, mesh reload, and restoration of transform, display, planes, results, curves, surfaces, BREP records, and editable features. | `app/main_window.py`, `project/project_data.py`, `project/project_io.py`, `project/project_state.py` | `test_project_io.py`, `test_project_state.py`, `test_main_window_ui.py` | `.openretop` JSON version 1 and its tolerant legacy fallbacks are compatibility requirements. Runtime CAD objects are rebuilt, not serialized. |
| Settings and preferences | Versioned defaults for display, import proxy quality, window behavior, colors, region opacity, and configurable keybindings. Invalid/missing settings recover to safe defaults. Preferences are edited through a Tk tabbed dialog and saved on exit. | `settings/settings_data.py`, `settings/settings_io.py`, `app/preferences_dialog.py`, `app/keybinds.py` | `test_settings_io.py`, `test_keybinds.py`, `test_main_window_ui.py` | Persistence logic remains outside the new action registry; dialog operations remain presentation code. |
| Mesh import and state | STL, OBJ, and PLY loading through `trimesh`; source mesh, metadata, bounds, normals, triangle counts, and file path are retained. Unsupported/missing files fail cleanly. | `mesh/loader.py`, `mesh/mesh_state.py`, `mesh/triangle_mesh.py`, `mesh/import_mesh.py`, `app/object_state.py` | `test_mesh_loader_state_diagnostics.py`, `test_main_window_ui.py` | Full-resolution source geometry remains authoritative. |
| Display proxy and diagnostics | Optional quality-based decimation produces a VTK-backed display proxy without mutating the source mesh. UI reports source/display counts, reduction, bounds, and proxy status. | `mesh/display_proxy.py`, `mesh/diagnostics.py`, `app/main_window.py` | `test_display_proxy.py`, `test_mesh_loader_state_diagnostics.py`, `test_main_window_ui.py` | Proxy generation is infrastructure; source geometry continues to drive modeling. |
| Accelerated mesh queries | Batched closest-point queries use `vtkStaticCellLocator` through `MeshSpatialIndex`. `MeshQueryService` caches one index by mesh identity or explicit revision and exposes build/query diagnostics. Curve projection, manual-curve projection, conforming lofts, and deviation reuse this service. | `mesh/spatial_index.py`, `mesh/query_service.py`, `curves/projection.py`, `surfaces/surface_preview.py`, `analysis/deviation.py` | `test_mesh_spatial_index.py`, `test_curve_surface_prep.py`, `test_manual_curve_controller.py`, Task 72 tests | The per-window service and transform revision invalidation must be preserved; brute-force projection is not an allowed fallback. |
| Scene browser and selection | Hierarchical nodes cover mesh, section planes/results, grouped curves, preview surfaces, BREP surfaces, and the active region. It supports family/group selection, multi-selection, rename, visibility states (visible/hidden/mixed), source/type tags, and callbacks into application selection. | `app/scene_browser.py`, `app/selection_types.py`, `app/main_window.py` | `test_scene_browser_labels.py`, extensive scene-browser cases in `test_main_window_ui.py` | Tk tree/menu implementation remains presentation. Node-ID parsing is still coupled to legacy application coordination. |
| Visibility and deletion | Toggle, hide, show, isolate, show-all, group visibility, and dependent deletion work across persistent scene families. Deleting planes/results/curves also removes dependent results/surfaces as applicable. Visibility and deletion are undoable where currently supported. | `app/main_window.py`, collection modules | `test_main_window_ui.py`, `test_undo.py` | Show All and Toggle Visibility are in the representative registry; other operations remain legacy wrappers. |
| Viewport and interaction | Embedded VTK scene renders mesh, planes, results, curves, manual controls/previews, region overlays, preview surfaces, and BREP display proxies. It handles selection/picking, camera navigation, named views, render coalescing, actor reuse, interactive transforms, display colors, grid/axes/view cube/axis gizmo, and selection overlays. | `viewer/embedded_viewport.py`, `viewer/overlays.py` | `test_embedded_viewport_scene.py`, `test_viewer_overlays.py`, `test_main_window_ui.py` | VTK actor creation/mutation remains in viewport presentation infrastructure. |
| Camera framing | Frame All and Frame Selected exist for mesh, planes, results, curves, surfaces, BREP source curves, and regions; selected-group IDs expand to child geometry. | `app/main_window.py`, `viewer/embedded_viewport.py` | framing/source-curve cases in `test_main_window_ui.py`; representative contract cases in `test_application_core.py` | Registered in Task 75, but framing is a known regression: restored or mixed scenes are not framed reliably. Expected behavior is characterized separately; the camera fix is reserved for Task 77. |
| Object transforms | Numeric location/rotation/scale/origin editing plus interactive move (`G`) and rotate (`R`) for the mesh. Axis constraints, fine movement, camera-relative movement, bounding-box transforms, reset, set origin to geometry, move origin to world origin, and center geometry on origin are supported. | `app/transforms.py`, `app/transform_state.py`, `app/object_state.py`, `app/main_window.py` | `test_transforms.py`, `test_main_window_ui.py` | Pure transform math is separated; command/session coordination is still in `OpenRetopWindow`. |
| Section-plane transforms | Multiple section planes may be axis-aligned or arbitrary. Interactive move/rotate, plane-normal movement, axis/offset controls, visibility, selection, and orientation preview are supported. | `sections/section_state.py`, `app/transforms.py`, `app/main_window.py`, `viewer/overlays.py` | `test_section_state.py`, `test_sections.py`, `test_main_window_ui.py`, `test_viewer_overlays.py` | Existing behavior and legacy axis/offset compatibility must remain unchanged. |
| Section extraction | Triangle/plane intersection supports X/Y/Z and arbitrary origin/normal planes, welds segments into polylines, and stores independent results per plane. Results can be computed, cleared individually, or cleared together. | `geometry/sections.py`, `sections/section_state.py`, `app/main_window.py` | `test_sections.py`, `test_section_state.py`, `test_main_window_ui.py` | Geometry algorithm is domain code and is not being rewritten during migration. |
| Initial curve fitting | Extracted section polylines are fitted with the existing lightweight Chaikin smoother and retain original/fitted points, mean/max error, and closure state. | `geometry/curves.py` | `test_curves.py`, section integration in `test_main_window_ui.py` | Algorithm is preserved as-is. |
| Stored curve state and repair | Curves retain IDs, source plane/result lineage, visibility/selection, diagnostics, and arbitrary metadata. Join, auto-close, RDP simplify, smooth, tiny-fragment detection, selection, and dependent cleanup are supported. Generated repair operations create new records rather than silently replacing originals. | `curves/curve_state.py` | `test_curve_state.py`, `test_main_window_ui.py` | Domain helpers exist; UI validation, undo, and dependent-feature coordination remain in the window. |
| Projection, rebuild, and readiness | Curves can be projected to the source mesh, rebuilt by arc length, and checked for fill/loft readiness. Results preserve lineage and report failures, distances, point-count mismatch, planarity, closure, and other warnings/errors. | `curves/projection.py`, `curves/rebuild.py`, `curves/validation.py` | `test_curve_surface_prep.py`, `test_mesh_spatial_index.py`, `test_main_window_ui.py` | Projection must continue through `MeshQueryService`. |
| Manual-curve creation/editing | New curves start in draw/add mode; existing curves start in select mode. Open/closed polyline and smooth-guide sampling, explicit add/insert, select/move/delete, closure snapping, point smooth/corner types, automatic corner detection with manual overrides, span smoothing/straightening, snapping to mesh, keep-on-mesh projection, preview caching, finish/apply/cancel, and legacy metadata upgrade are supported. | `curves/manual_curve_session.py`, `app/manual_curve_controller.py`, `curves/manual_curve.py`, thin integration wrappers in `app/main_window.py` | `test_manual_curve_session.py`, `test_manual_curve_controller.py`, `test_manual_curve.py`, `test_manual_curve_v2.py`, Task 72 tests, UI integration cases | Task 74 made session state authoritative and controller behavior UI-agnostic. Compatibility properties/wrappers remain in the window; no smoothing or feature changes are authorized here. |
| Region selection | A mesh pick seeds connected-triangle growth by normal-angle threshold with a maximum-triangle cap. One active region can be recomputed, renamed, framed, shown/hidden, cleared/deleted, and rendered as a selected overlay. Drag is intentionally distinguished from click selection. | `mesh/adjacency.py`, `regions/region_state.py`, `app/main_window.py`, `viewer/embedded_viewport.py` | `test_mesh_adjacency.py`, `test_main_window_ui.py`, `test_embedded_viewport_scene.py` | Region workflow is still window-owned and a likely later extraction target. Paint/add/subtract selection is not implemented. |
| Region boundary and plane fit | Region boundary edges are welded and ordered into one or more polylines, including holes/disconnected/non-manifold cases. Boundaries can become editable curves. Regions can be best-fit to a plane and projected for planar BREP creation with error diagnostics. | `regions/boundary.py`, `regions/primitive_fit.py`, `app/main_window.py` | `test_region_boundary.py`, `test_region_primitive_fit.py`, `test_main_window_ui.py` | Existing boundary-to-curve lineage and diagnostics are project compatibility data. |
| Preview surfaces | Preview records support closed-curve fan fill, two-curve loft, mesh-conforming loft, boundary patch, four-curve Coons-style patch, and curve-network strips. Builders clean/resample/orient curves, align closed seams, suppress degenerate triangles, and store availability/quality diagnostics. | `surfaces/surface_state.py`, `surfaces/surface_preview.py` | `test_surface_state.py`, `test_surface_preview.py`, Task 72 tests, `test_main_window_ui.py` | These are preview meshes, distinct from BREP records and CAD objects. |
| Editable surface features | Editable loft records store ordered source curves, direction/seam/corner/cap/solid/ruled/rebuild options and per-edge overbuild controls. Four-boundary feature records preserve source links and build status. Source curve edits mark dependent features dirty; UI can rebuild, duplicate/delete lofts, edit/reorder/reverse sources, and inspect/select/isolate/show/frame sources. | `surfaces/loft_feature.py`, `surfaces/four_boundary_feature.py`, `app/main_window.py` | `test_surface_features.py`, Task 72 overbuild tests, `test_main_window_ui.py` | Records persist in project version 1; broad workflow migration is deferred. |
| BREP construction | Public CadQuery/OCP/OCCT adapters detect an available backend, convert stored curve semantics to line/spline wires, build planar faces and loft surfaces, validate inputs, and return structured warnings/errors without crashing when the optional kernel is unavailable. BREP records are kept separate from preview surfaces. | `cad_kernel/backend.py`, `cad_kernel/curve_wire.py`, `cad_kernel/occ_backend.py`, `cad_kernel/types.py`, `surfaces/brep_state.py` | `test_cad_kernel_backend.py`, `test_cad_kernel_types.py`, `test_cad_kernel_curve_wire.py`, `test_cad_kernel_planar_face.py`, `test_cad_kernel_loft_surface.py`, `test_brep_state.py` | No proprietary kernel is used or planned. CAD object lifetime is runtime-only. |
| STEP export | A selected runtime BREP object can be written as `.step`/`.stp`; suffix normalization, absent objects, unsupported writers, and empty output are reported cleanly. | `cad_kernel/export_step.py`, `app/main_window.py` | `test_cad_kernel_step_export.py`, `test_main_window_ui.py` | File picker remains presentation code; exporter remains infrastructure. |
| Analysis | Point-to-mesh deviation reports per-sample distances/closest points plus mean, maximum, RMS, failed indices, and timing/backend metadata. Analysis workbench also displays project, mesh, selection, and active-region diagnostics. | `analysis/deviation.py`, `mesh/diagnostics.py`, `app/main_window.py` | deviation cases in `test_mesh_spatial_index.py` and Task 72 contract tests | Computation is UI-independent and uses the accelerated query service; no new analysis tool is introduced. |
| Undo/redo | A LIFO callback-command stack supports named operations, clears redo on push, and is reset for new project/model load. Current integration covers representative scene edits such as rename, visibility, deletion, curve/manual edits, and surface/BREP creation. | `app/undo.py`, `app/main_window.py` | `test_undo.py`, undo/redo cases in `test_main_window_ui.py` | Undo and Redo are registered actions; the stack remains the injected `UndoPort` compatibility implementation. |
| Menus and keybindings | Main menus expose File/Edit/View/Help. Legacy workbench menus remain callable for compatibility. Defaults include undo/redo, rename, visibility/isolate/show-all, frame selected, move/rotate, transform confirm/cancel, and delete; settings may remap them. | `app/menus.py`, `app/keybinds.py`, `settings/settings_data.py`, `app/main_window.py` | `test_keybinds.py`, menu/keybinding cases in `test_main_window_ui.py` | Only six actions use authoritative `ActionDefinition` records. Other labels, shortcuts, and enablement remain presentation-owned. |
| Application core | Stable action definitions, an instance-scoped registry, command protocol/dispatcher, structured results, typed event publisher, immutable selection, and an explicit dependency container are available without Tk/VTK imports. | `application/actions.py`, `application/commands.py`, `application/results.py`, `application/events.py`, `application/selection.py`, `application/dependencies.py` | `test_application_core.py` | Task 75 representative slice only: Frame All, Frame Selected, Show All, Toggle Visibility, Undo, and Redo. |

## Aggregate state ownership

`AppState` is the current non-widget aggregate. Its collections define the
records that project restore and scene refresh must keep coherent.

| State | Current owner | Important relationships |
|---|---|---|
| Mesh object | `MeshObjectState` | Owns source/display mesh, file path, transform, bounds, visibility, and proxy diagnostics. Transform revisions invalidate mesh queries. |
| Section planes/results | `SectionCollection` | Results reference a plane; deleting a plane removes its results and downstream curves/surfaces. |
| Curves | `CurveCollection` | Curves reference plane/result lineage and can be sources for previews, BREP records, loft features, and four-boundary features. |
| Preview surfaces | `SurfaceCollection` | Serializable preview description plus source curve IDs; render geometry is derived. |
| BREP surfaces | `BrepSurfaceCollection` | Serializable record plus source curve IDs; non-serializable CAD object cache is maintained by presentation orchestration. |
| Editable lofts | `LoftFeatureCollection` | Links source curves, preview record, and optional BREP record; source edits mark it dirty. |
| Editable four-boundary patches | `FourBoundaryPatchFeatureCollection` | Links four source curves and generated records; source edits mark it dirty. |
| Region | `RegionCollection` | At most one active selection; it references the source mesh and can produce boundary curves or a planar BREP. |
| Manual-curve session | `ManualCurveController.session` | Transient workflow state is intentionally outside `AppState` but is authoritative; it must never be duplicated in window fields. |
| Global selection bridge | `AppState` collections plus `SceneBrowser` | Legacy selection is multi-family mutable state. `CallbackSelectionProvider` snapshots scene node IDs for registered commands. |

## Production package inventory

| Package | Audited responsibility |
|---|---|
| `analysis` | UI-independent point-to-mesh deviation data and computation. |
| `app` | Legacy application/presentation integration: window, aggregate state, scene browser, menus, keybindings, preferences, transforms, undo, and the Task 74 manual-curve controller. This is intentionally a mixed package during migration. |
| `application` | New UI-agnostic action, command, result, event, selection, and dependency contracts. No global service locator. |
| `cad_kernel` | Public CadQuery/OCP/OCCT detection, curve-to-wire conversion, planar/loft construction, result contracts, and STEP export. |
| `curves` | Stored-curve state, manual-curve/session algorithms, projection, rebuild, diagnostics, repair, and surface-readiness validation. |
| `geometry` | Section-plane intersection and lightweight extracted-curve fitting. |
| `mesh` | Triangle-mesh value type, import/state/diagnostics, display proxy, adjacency/region growing, accelerated spatial index, and cached query service. |
| `project` | Version 1 serializable data, tolerant JSON parsing/writing, and conversion from runtime state. |
| `regions` | Region record, boundary extraction, best-fit plane, and planar boundary projection. |
| `sections` | Section-plane/result collection state and axis/arbitrary orientation compatibility. |
| `settings` | Version 1 application settings defaults and tolerant user-settings persistence. |
| `surfaces` | Preview and BREP record collections, preview mesh builders, editable loft features, and editable four-boundary features. |
| `viewer` | Tk-embedded VTK viewport, actor construction/mutation, picking/navigation, scene synchronization, and pure overlay geometry helpers. |
| `main.py` | Current bootstrap entry point, delegating to `app.main_window.run_app`. |

## Test package inventory

The suite mixes pure unit tests, optional/public CAD backend tests, VTK tests,
and Tk integration tests. `tests/mesh_query_reference.py` is a deliberately
slow reference helper used only to validate accelerated query results.

| Test module(s) | Coverage |
|---|---|
| `test_application_core.py` | Action definition/registry contracts, command dispatch/results, typed events, selection, dependency ports, and compatibility wrappers for the six registered actions. |
| `test_app_state.py`, `test_undo.py`, `test_transforms.py`, `test_keybinds.py` | Aggregate state invariants, history behavior, pure transform math, and key normalization/remapping. |
| `test_main_window_ui.py` | End-to-end Tk application behavior: projects/settings, menus, progress, selection/browser, visibility/deletion, framing, transforms, sections, curves, manual curves, regions, preview/BREP surfaces, feature dependencies, and undo. |
| `test_embedded_viewport_scene.py`, `test_viewer_overlays.py` | VTK scene/actor lifecycle, render coalescing, picking/navigation, camera views, display styling, overlays, manual/region/surface rendering, and transform fast paths. |
| `test_mesh_loader_state_diagnostics.py`, `test_display_proxy.py` | Import validation, mesh metadata/diagnostics, and source-preserving display decimation. |
| `test_mesh_adjacency.py`, `test_mesh_spatial_index.py` | Adjacency/region growth and accelerated closest-point correctness, caching, failures, conforming projection, and deviation metrics. |
| `test_sections.py`, `test_section_state.py`, `test_curves.py` | Axis/arbitrary section extraction, plane/result collections, and initial curve fitting. |
| `test_curve_state.py`, `test_curve_surface_prep.py` | Curve collection/diagnostics/repair plus projection, rebuild, validation, lineage, and scene labels. |
| `test_manual_curve.py`, `test_manual_curve_v2.py`, `test_manual_curve_session.py`, `test_manual_curve_controller.py` | Manual sampling/storage compatibility, typed controls/corners, session invariants, controller workflow/input routing, snapping, projection-cache reuse, and absence of duplicated window state. |
| `test_region_boundary.py`, `test_region_primitive_fit.py` | Boundary topology and region best-fit-plane/projection behavior. |
| `test_surface_state.py`, `test_surface_preview.py`, `test_surface_features.py` | Preview record lifecycle, all current preview builders/diagnostics, editable feature linkage/dirty state, and project persistence. |
| `test_brep_state.py`, `test_cad_kernel_backend.py`, `test_cad_kernel_types.py`, `test_cad_kernel_curve_wire.py`, `test_cad_kernel_planar_face.py`, `test_cad_kernel_loft_surface.py`, `test_cad_kernel_step_export.py` | BREP records, backend detection, CAD input cleanup, mixed line/spline wires, face/loft validation and construction, optional-backend failures, and STEP writing. |
| `test_project_io.py`, `test_project_state.py`, `test_settings_io.py` | Versioned serialization, tolerant legacy/default handling, metadata preservation, runtime-to-project conversion, and settings recovery. |
| `test_scene_browser_labels.py` | Stable human-readable curve/surface/BREP/region labels. |
| `test_task72_rewrite.py`, `test_task72_third_revision.py` | Regression contracts for smooth guides, corner sources, conforming loft metrics, overbuild metadata/handles, and deviation records. |

## Explicitly absent or placeholder behavior

- `Recent Files` is a disabled menu placeholder.
- `Help > Hotkeys` reports "Not implemented yet"; editable keybindings exist in
  Preferences, but there is no separate hotkey reference dialog.
- Region paint/add/subtract brushes, curvature grow, automatic face detection,
  primitives, trimming, intersections, tangent-handle/NURBS editing, and other
  roadmap modeling features are not part of this baseline.
- Task 75 does not replace Tk, rewrite the viewport, migrate every command, or
  change any geometry algorithm.
- The known camera framing failure is retained and documented for Task 77; it
  must not be hidden by changing expected behavior in this task.

## Preservation checklist for later extractions

Every later workflow migration must keep the following observable contracts:

1. Project version 1 and legacy `.openretop` inputs continue to load without
   discarding optional metadata or source lineage.
2. Full-resolution source mesh geometry remains the modeling source even when a
   display proxy is active.
3. Closest-point work goes through the shared accelerated `MeshQueryService`.
4. Preview surfaces, BREP records, runtime CAD objects, and editable feature
   records remain distinct concepts with explicit links.
5. Selection, visibility, deletion, undo/redo, dirty state, scene refresh, and
   dependent-feature invalidation stay coherent after each command.
6. Manual-curve transient state remains owned by `ManualCurveSessionState`, and
   Task 74 input-routing behavior remains unchanged.
7. Tk dialogs/widgets and VTK actors stay outside domain and application
   contracts.

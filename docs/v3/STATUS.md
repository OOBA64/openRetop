# openRetop V3 migration status

## Current task

Task 80 — Implement openRetop V3 UI on the reusable framework

Implementation status: complete for the V3 shell, central action wiring,
snapshot viewport, persistence dialogs, and tested core workflow adapters.
Tasks 77–79 are committed. Task 81 remains for final parity closure and legacy
shell removal.

## Completed task history

- Task 77: scene snapshots, incremental VTK, structured picking, camera and
  framing rework. Focused suite: 11 passed. Commit `4de640b`.
- Task 78: persistence/settings/import-export/CAD boundaries and composition
  root. Focused suite: 7 passed. Commit `53ee0cd`.
- Task 79: independent `packages/workbench_ui` PySide6 framework, VTK host,
  shell, panels, tools, inspector, tree, palette, themes, settings, demo, and
  offscreen tests. Focused suite: 5 passed. Commit `0edbe1f`.

## Task 80 completed work

- Added `OpenRetopV3Window` and made `src/main.py` launch it as the supported
  entry point. The framework path is composed only when running from source;
  installed packages continue to resolve normally.
- Added the default V3 layout: File/Edit/View/Create/Modify/Inspect/Help
  menus, optional toolbar actions, Scene and Properties docks, Task 77 VTK
  snapshot viewport, command palette, diagnostics panel, and instruction/status
  bar.
- Converted the central application action registry into framework actions;
  Frame All/Selected, visibility, undo/redo, named views, and file actions
  dispatch through one path rather than widget-specific handlers.
- Added stable scene-tree coverage for mesh, section planes/results, curves,
  preview/BREP surfaces, and regions with selection and visibility controller
  adapters.
- Added V3 model/project open/save dialogs that call Task 78 services, create
  controller-owned mesh state, preserve relative project paths, and frame
  restored model geometry through Task 77 snapshots.
- Added `docs/v3/V3_PARITY_MATRIX.md` and a concise V3 user guide.

## Task 80 verification

- `tests.test_task80_v3_ui` — 3 passed with `QT_QPA_PLATFORM=offscreen`.
- `tests.test_task79_workbench_ui` — 5 passed with `QT_QPA_PLATFORM=offscreen`.
- Task 77 and Task 78 focused suites remain green individually.
- `python -m compileall -q src packages/workbench_ui/workbench_ui` — passed.
- Standalone framework wheel build — passed after installing the declared
  `wheel` build dependency.
- `git diff --check` — passed.

## Known limitations before Task 81

- The V3 shell exposes the full central action registry, but several advanced
  actions still report controller availability rather than presenting every
  legacy-specific inspector editor; the parity matrix identifies the owning
  controller and existing behavior tests.
- The legacy Tk `OpenRetopWindow` and its compatibility viewport facade remain
  in the tree for the migration test baseline. Task 81 must remove them only
  after replacing the remaining widget-internal tests with V3 behavior tests.
- A Windows offscreen VTK run can log OpenGL warnings when multiple Qt/VTK
  windows are created in one interpreter; isolated V3 smoke runs are green.

## Exact next-task starting point

Task 81 starts by walking `docs/v3/V3_PARITY_MATRIX.md`, moving each retained
legacy behavior to a tested V3 action/controller path, then removing the
superseded Tk shell, `EmbeddedVTKViewport.set_scene(...)` compatibility path,
Tk menus/dialogs/panels, and stale allowlist entries. Do not claim final
release-candidate status until the complete V3 behavior suite is green.

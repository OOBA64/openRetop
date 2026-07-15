# openRetop V3 migration status

## Current task

Task 79 — Reusable Standalone Workbench UI Framework

Implementation status: complete. Task 77 and Task 78 are committed. The
standalone PySide6 framework, offscreen Qt tests, VTK host proof, and demo all
pass. Task 80 presentation work is present in the working tree but is not part
of this Task 79 commit.

## Completed task history

### Task 77

Added immutable scene snapshots/render items, a UI-independent scene builder,
stable revisions and IDs, incremental actor synchronization, structured
picking, isolated VTK adapters, camera/framing math, and post-load framing.
Focused result: `tests.test_task77_viewport` — 11 passed. Commit `4de640b`.

### Task 78

Added typed JSON/in-memory project and settings repositories, schema migration
and unknown metadata preservation, mesh/proxy/STEP/project services with typed
progress, public CAD capabilities, and `bootstrap.create_application`.
Focused result: `tests.test_task78_boundaries` — 7 passed. Commit `53ee0cd`.

## Task 79 completed work

- Added `packages/workbench_ui` with package metadata, public API, extension
  documentation, and a standalone demo. The Python package imports no
  openRetop modules.
- Added reusable action registry/state propagation, declarative menu and
  toolbar schemas, panel registry, dock-layout persistence/recovery,
  selection context, tool lifecycle manager, property inspector model,
  scene-tree model, command palette, theme manager, and framework settings.
- Added `ApplicationShell` with dockable panels, menu/toolbar construction,
  status messaging, layout save/restore, and central action dispatch.
- Added generic scene-tree, property-inspector, tool-instruction, command
  palette, and optional public-VTK Qt host widgets.
- Added `requirements.txt` PySide6 dependency and Qt offscreen/headless tests.

## Task 79 verification

- `tests.test_task79_workbench_ui` — 5 passed with `QT_QPA_PLATFORM=offscreen`.
- PySide6/VTK proof: `VTKViewportWidget.available == True` in the V3
  environment.
- `python -m compileall -q src packages/workbench_ui/workbench_ui` — passed.
- Architecture metrics with `--fail-on-new` — passed; no cycles or new
  protected-layer UI imports.
- `git diff --check` — passed.

## Files added for Task 79

- `packages/workbench_ui/pyproject.toml`
- `packages/workbench_ui/README.md`
- `packages/workbench_ui/workbench_ui/{__init__,contracts,shell,widgets,viewport,demo}.py`
- `tests/test_task79_workbench_ui.py`
- `requirements.txt` (PySide6 dependency)

## Known risks and next task

The legacy Tk shell remains in `src/app/main_window.py` while Task 80 wires
V3 workflows and Task 81 removes the superseded shell. The pre-existing full
suite baseline remains 617 passed, 31 failed, and 1 error in legacy Tk
compatibility cases; the new framework suites are green.

Task 80 starts at `src/presentation/qt/`: use the workbench shell, Task 77
scene snapshots, Task 78 services, and application controllers to build the
openRetop V3 window and parity matrix without duplicating actor or workflow
state.

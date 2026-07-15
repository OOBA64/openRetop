# openRetop V3 migration status

## Current task

Task 78 — Persistence, Settings, Import/Export, CAD Adapters, and Bootstrap

Implementation status: complete for the repository/application boundary slice.
Task 77 is committed. Task 78 focused checks pass; the existing legacy
MainWindow compatibility suite still has the baseline failures recorded below.

## Task 77 summary

Task 77 introduced immutable toolkit-neutral scene snapshots and render-item
contracts, a UI-independent scene builder, stable object/revision identities,
incremental VTK actor synchronization, structured picking, isolated style and
actor factories, camera/framing math, and post-load framing. The real viewport
submits snapshots; `EmbeddedVTKViewport.set_scene(...)` remains only for the
temporary compatibility path through Task 81.

Focused result: `tests.test_task77_viewport` — 11 passed. Architecture,
compile, and diff checks passed. Commit: `4de640b`.

## Task 78 completed work

- Added `ProjectRepository`, deterministic `JsonProjectRepository`, and an
  in-memory fake with structured load/save results, schema-version handling,
  relative mesh-path resolution, missing-mesh warnings, and unknown top-level
  metadata preservation.
- Extended `ProjectData` with a non-destructive metadata map while preserving
  the existing `.openretop` fields and serializers.
- Added `SettingsRepository`, deterministic `JsonSettingsRepository`, and an
  in-memory fake with normalized defaults and structured corruption results.
- Added `MeshImportService`, `DisplayProxyService`, `StepExportService`, and
  `ProjectFileService`; progress is emitted as typed events and file-dialog
  policy remains outside the services.
- Added `PublicCadAdapter` and accurate capability flags. It exposes wire,
  planar-face, loft, tessellation, and STEP operations only; trim/intersection
  are explicitly unavailable.
- Added `bootstrap.create_application` as an explicit composition root wiring
  state, events, actions, commands, undo, query service, repositories,
  import/export services, CAD, controllers, and scene building without a
  singleton or toolkit import.

## Task 78 verification

- `tests.test_task78_boundaries` — 7 passed.
- `python -m compileall -q src` — passed.
- Task 77 focused and architecture suites remain passing.
- `git diff --check` — passed.

The complete pre-existing suite currently reports 617 passed, 31 failed, and 1
error under the V3 interpreter. The non-passing cases are in the legacy Tk
MainWindow compatibility tests and concern old status wording, direct private
restore helpers, and Task 74–76 compatibility expectations; they do not fail
the new persistence, scene, camera, or controller contracts.

## Files added or modified for Task 78

- `src/infrastructure/__init__.py`
- `src/infrastructure/persistence.py`
- `src/infrastructure/settings_repository.py`
- `src/infrastructure/io_services.py`
- `src/infrastructure/cad_adapter.py`
- `src/bootstrap/__init__.py`
- `src/bootstrap/composition_root.py`
- `src/application/bootstrap.py`
- `src/project/project_data.py`
- `src/project/project_io.py`
- `tests/test_task78_boundaries.py`

## Compatibility and known risks

- Existing project/settings convenience functions remain available for legacy
  callers; the new repositories are the V3 boundary.
- CAD availability depends on the optional CadQuery/OCP installation. The
  adapter reports unavailable capabilities rather than claiming unsupported
  trim/intersection behavior.
- No representative real-world project fixture is checked in yet.
- The current Tk shell remains a compatibility implementation while the Qt V3
  workbench is brought to parity in Tasks 79–81.

## Exact next-task starting point

Task 79 starts at `packages/workbench_ui/`: prove PySide6/VTK embedding,
implement the reusable host-independent workbench framework and standalone
demo, and add Qt offscreen contract tests. Do not remove the openRetop shell
until Task 80 parity is wired and Task 81 explicitly removes it.

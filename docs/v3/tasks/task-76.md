# Task 76 — Extract Remaining Workflow Controllers

# Common execution rules

This task is part of the openRetop V3 architecture refactor.

The repository starting point already includes Task 74: manual-curve controller/session extraction and behavior-preserving stabilization.

Mandatory rules:

- Complete only the numbered task in this file.
- Do not begin the next numbered task.
- Do not commit, push, merge, rebase, reset, tag, or switch branches. The external runner handles Git.
- Preserve current modeling behavior unless this task explicitly changes presentation behavior.
- Preserve backward compatibility for existing `.openretop` project files.
- Do not rewrite geometry algorithms merely because code is being moved.
- Do not delete, weaken, skip, or rewrite tests solely to obtain a passing result.
- Keep UI toolkit imports out of domain and application modules.
- Keep concrete Tk, Qt, VTK actor, dialog, and file-picker operations outside domain controllers.
- Keep VTK actor construction and mutation inside viewport infrastructure/presentation adapters.
- Use the existing public VTK and CadQuery/OCP/OCCT stack.
- Do not add proprietary CAD-kernel dependencies.
- Do not add new modeling features during the refactor.
- Reuse the existing accelerated MeshQueryService; do not reintroduce brute-force projection.
- Keep the application runnable after this task.
- Run focused tests during development.
- Before finishing, run `python -m compileall -q src` and the complete unittest suite with `PYTHONPATH=src`.
- Update `docs/v3/STATUS.md` with completed work, files changed, tests/results, risks, known issues, and the exact next-task starting point.
- Stop and report a blocker rather than bypassing a critical compatibility, test, or architecture requirement.

At completion, report implemented changes, files created/moved/removed, tests/results, compatibility risks, known remaining issues, and whether every acceptance criterion was satisfied.


## Purpose
Move non-presentation behavior out of MainWindow into testable application controllers. Task 74 handled manual curves; Task 75 supplied contracts. Preserve the Tk UI as an adapter.

## Required controllers
- SceneController
- SelectionController
- VisibilityController
- TransformController
- SectionController
- CurveController for non-manual curve processing
- RegionController
- SurfaceController
- BrepController
- AnalysisController

Project/settings/import/export remain primarily Task 78.

## Rules
Controllers operate on explicit state, return Task 75 results, publish typed events, avoid Tk/Qt/dialog/MainWindow/VTK actors, avoid direct file dialogs and message boxes, do not own the global undo stack, do not duplicate geometry or project serialization, and do not create another mesh-query cache.

Move authoritative workflow/session state out of MainWindow where appropriate. Tk variables are presentation state only; no independent shadow copies. Compatibility properties may directly forward to controller state.

Refactor MainWindow methods into thin adapters: gather presentation input, resolve screen-space input, call controller/command, apply status/undo/dirty/refresh/selection requests, update widgets. Preserve public method names used by menus/tests until Task 81.

Preserve undo/redo and dependency invalidation for transforms, visibility, create/delete/rename, sections, curve processing, regions, surfaces/BREP, editable lofts, source-curve edits, mesh replacement, and source deletion.

Register all current non-file-dialog actions in the central action registry and centralize enablement/visibility rules.

## Tests
Add controller tests without Tk for success/failure, undo payloads, dirty state, events, selection, missing dependencies, and dependent-feature invalidation. Keep MainWindow integration tests. Assert controllers do not import UI/MainWindow.

## Acceptance
All listed workflows have UI-agnostic controllers or documented exceptions. MainWindow is materially smaller and mostly an adapter. Task 74 manual curves and Task 73 projection remain intact. Undo/persistence semantics remain. Full tests pass.

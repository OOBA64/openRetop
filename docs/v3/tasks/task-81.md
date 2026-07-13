# Task 81 — Reach Parity, Remove Legacy Shell, and Eliminate Compatibility Scaffolding

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
Complete V3 parity, make V3 the supported entry point, remove legacy Tk presentation and temporary migration layers, and enforce architecture. Do not remove legacy behavior until V3 equivalents are tested.

## Required work
1. Review the Task 80 parity matrix. Every legacy feature must be implemented/tested, intentionally removed as redundant with rationale/migration note, or explicitly documented as previously nonfunctional with a replacement plan.
2. Finish missing V3 actions, tree operations, inspector fields, tools, shortcuts, preferences, dialogs, progress/error reporting, undo/redo, recent files, project dirty/title, BREP/STEP, and diagnostics.
3. Make V3 the normal entry point. Remove temporary legacy launch only after parity is proven.
4. Remove legacy Tk MainWindow, Tk panels/menus/dialogs/preferences, old scene browser/viewport host if replaced, redundant UI state, duplicated action enablement, compatibility wrappers, and dead imports/tests.
5. Remove migration re-exports only after all callers use final V3 paths. Update imports to documented layout.
6. Shrink architecture allowlists toward:
   - domain: zero UI imports
   - application: zero concrete UI imports
   - infrastructure: no presentation imports
   - presentation: application contracts only
   - bootstrap: composition root
7. Remove Tk-only dependencies when no longer needed; update package metadata for PySide6/VTK.
8. Replace brittle legacy widget-internal tests with behavior-focused V3 tests without reducing command/selection/visibility/framing/tool/project/undo/geometry coverage.
9. Add a test ensuring production code no longer references removed legacy MainWindow/Tk presentation.
10. Update startup, UI, architecture, extension, migration, and limitation docs.

## Acceptance
V3 is the only supported shell, every retained feature has parity evidence, legacy Tk/dead UI is removed, shims are gone or narrowly justified, architecture allowlists are substantially reduced, project compatibility remains, and full tests pass.

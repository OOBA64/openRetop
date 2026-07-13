# Task 75 — V3 Architecture Baseline and Application Core

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
Establish the authoritative V3 architecture, dependency rules, command/action contracts, event contracts, and migration baseline before extracting remaining workflows. Add foundations and compatibility adapters, but do not migrate the whole UI or remove Tk.

## Required work
1. Audit all production/test packages, especially MainWindow, AppState, manual-curve controller/session, scene browser, menus, keybindings, undo, transforms, mesh/query/projection, sections, curves, regions, surfaces, BREP, analysis, project, settings, and viewer.
2. Create/complete:
   - `docs/v3/ARCHITECTURE.md`
   - `docs/v3/MIGRATION_RULES.md`
   - `docs/v3/FEATURE_INVENTORY.md`
   - `docs/v3/COMMAND_INVENTORY.md`
   - `docs/v3/PROJECT_FORMAT_BASELINE.md`
   - `docs/v3/DEPENDENCY_AUDIT.md`
   - `docs/v3/KNOWN_REGRESSIONS.md`
   - `docs/v3/STATUS.md`
3. Define layers: domain, application, infrastructure, presentation, bootstrap. Document allowed dependency direction.
4. Create `scripts/report_architecture_metrics.py` reporting file/line counts, largest modules, classes/functions, MainWindow method count, major-package imports, current dependency violations, and duplicate action labels where detectable.
5. Add architecture tests with an explicit human-readable baseline/allowlist so current known violations are reported and only new violations fail. Detect UI imports in domain/application, UI imports from project/settings/CAD/mesh-query modules, and practical package cycles.
6. Create UI-agnostic application primitives, preferably:
   - `src/application/actions.py`
   - `commands.py`
   - `events.py`
   - `results.py`
   - `selection.py`
   - `dependencies.py`
7. Implement:
   - ActionDefinition with stable ID, label, description, category, shortcut, command/handler ID, enablement/visibility contract, checkable state, metadata.
   - command protocol/dispatcher and structured result with warnings/errors, changed/dirty, viewport/UI requests, optional undo payload.
   - typed event publisher for state, selection, scene, dirty, command, active tool, and status events.
   - explicit dependency container/composition contracts without an untyped global service locator.
8. Migrate only a representative slice into the new registry while preserving current wrappers: Frame All, Frame Selected, Show All, Toggle Visibility, Undo, Redo.
9. Characterize the known framing regression and define future expected behavior. Add tests where practical; reserve the full camera fix for Task 77.

## Acceptance
Architecture docs, inventories, project baseline, metrics, dependency tests/baseline, and application primitives exist. The representative actions use them without broad UI migration. Existing projects and Task 74 behavior remain intact. Full tests pass.

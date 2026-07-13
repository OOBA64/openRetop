# Task 80 — Implement openRetop UI V3 on the Reusable Framework

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
Build a parallel PySide6 V3 presentation layer using workbench_ui and Tasks 75–78 controllers. Keep legacy Tk available for parity comparison during this task.

## Required work
1. Add a clear V3 entry point/bootstrap without deleting legacy.
2. Default layout:
   - menu and compact optional toolbar
   - left Scene tree
   - center VTK viewport
   - right contextual Properties/Tool inspector
   - optional bottom diagnostics/task output
   - status/tool instruction bar
   - command palette
3. Use centralized actions. Recommended menus: File, Edit, View, Create, Modify, Inspect, Help. No duplicate menu/toolbar/context handlers.
4. Scene tree covers mesh, section planes/results, curve groups/curves, regions, preview/BREP surfaces, and editable features, with selection/visibility/rename/delete/context/isolate/show-all/frame.
5. Context inspector covers no selection, mesh, section, curve, manual curve tool, region, preview/BREP surface, editable loft/four-boundary feature, settings. Use collapsible Advanced groups.
6. Integrate transforms, manual curves, region selection, section editing, and overbuild handles through ToolModeManager. Preserve camera navigation and consistent Finish/Apply/Cancel/Esc.
7. Use Task 77 scene snapshots/viewport adapter; no duplicated VTK actor logic.
8. Add V3 dialogs/adapters for project/model open/save, STEP export, preferences, confirmation/errors, and progress through Task 78 services.
9. Build a parity matrix mapping every legacy feature/action to V3 location, action ID, controller, and test.
10. Add shell, menu/action parity, tree, inspector, tool lifecycle, shortcuts, dialogs, VTK smoke, workflow adapter, optional-CAD startup, project open/save, and architecture tests.

## Acceptance
V3 launches, existing features are reachable through actions, tree/viewport/inspector/status/palette work, manual curve/region navigation remains correct, project/model/settings/export connect, legacy remains available, parity matrix exists, full tests pass.

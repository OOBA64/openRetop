# Task 79 — Reusable Standalone Workbench UI Framework

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
Build a reusable desktop UI/UX framework with zero openRetop dependencies for future technical/CAD-style programs. Create the framework and a standalone demo; do not replace openRetop UI yet.

## Technology decision
Use PySide6/Qt if a proof of concept succeeds. First prove on supported Windows:
- PySide6/QMainWindow launches
- dockable panels, actions, shortcuts, saved/restored layout work
- VTK render window embeds/renders
- headless tests cover non-rendering components

If Qt/VTK has a fundamental blocker, document it and stop rather than silently building another large Tk framework.

## Package
Create `packages/workbench_ui/` with a clean public API and package metadata. It must not import openRetop.

## Systems
- ApplicationShell: central workspace, docks, status, menu/toolbar, layout persistence, panel/focus management.
- ActionRegistry: one action definition drives menus, toolbars, context menus, shortcuts, command palette, and help; stable ID, label, category, icon key, shortcut, enabled/visible/check state, dispatch.
- Declarative MenuSchema/ToolbarSchema.
- PanelRegistry and DockLayoutManager with safe layout recovery.
- ToolModeManager with one primary tool and consistent enter/exit/cancel/apply/finish/instructions.
- SelectionContext.
- Reusable PropertyInspector editors: text, number, slider, checkbox, combo, color, vector, read-only, grouped/advanced, validation, live/apply/cancel modes.
- SceneTree model/view interfaces with stable IDs, hierarchy, selection, visibility, rename, context actions, optional reorder.
- CommandPalette search.
- ThemeManager with semantic colors, spacing, typography, icon keys, dark/light.
- Framework settings/layout schema independent of openRetop.

## Demo and docs
Create a standalone demo showing docks, tree, inspector, registry-driven menu/toolbar/context actions, palette, tool mode, color/vector editors, layout persistence, and embedded VTK test geometry. Document public API and extension workflows.

## Tests
Test action propagation, schemas, conflicts, panels/layout, inspector validation, tool lifecycle, tree model, palette, themes, and zero openRetop imports. Use Qt offscreen testing where reliable.

## Acceptance
Qt/VTK proof works, workbench_ui is independent/reusable, central actions drive UI surfaces, shell/docking/inspector/tree/tools/themes/settings/palette exist, demo runs, docs/tests exist, openRetop UI is not replaced, full repository tests pass.

# workbench_ui

`workbench_ui` is a standalone PySide6 workbench framework for technical
desktop applications. It provides reusable action, menu, toolbar, panel,
docking, tool-mode, selection, property-inspector, scene-tree, command-palette,
theme, settings, and VTK-host primitives.

The package has no dependency on the host application's domain or application
layers. A host supplies action callbacks, scene nodes, property definitions,
and tool lifecycle hooks through the public contracts.

The public API includes state-aware actions with shortcut-conflict detection,
nested menus and toolbars, dock layout save/recovery, hierarchical scene trees
with rename/visibility/context/reorder operations, live or apply/cancel property
inspectors (text, numeric, slider, check, choice, color, vector, and read-only
editors), modal tool lifecycle state, command-palette search, built-in themes,
and an optional QVTK workspace host.

The VTK host has an explicit native lifecycle. Add it to a shown Qt window,
connect to its one-shot `ready` signal if scene work must wait for native VTK,
then call idempotent `start()`. Rendering before readiness is a safe no-op, and
native initialization/rendering are suppressed under `QT_QPA_PLATFORM=offscreen`.

Run the framework demo from the repository root after installing PySide6:

```powershell
$env:PYTHONPATH = "packages/workbench_ui"
python -m workbench_ui.demo
```

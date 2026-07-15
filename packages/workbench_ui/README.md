# workbench_ui

`workbench_ui` is a standalone PySide6 workbench framework for technical
desktop applications. It provides reusable action, menu, toolbar, panel,
docking, tool-mode, selection, property-inspector, scene-tree, command-palette,
theme, settings, and VTK-host primitives.

The package has no dependency on the host application's domain or application
layers. A host supplies action callbacks, scene nodes, property definitions,
and tool lifecycle hooks through the public contracts.

Run the framework demo from the repository root after installing PySide6:

```powershell
$env:PYTHONPATH = "packages/workbench_ui"
python -m workbench_ui.demo
```

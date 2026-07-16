"""Standalone workbench_ui demonstration."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from workbench_ui import (
    ActionDefinition,
    ActionRegistry,
    ApplicationShell,
    CommandPaletteWidget,
    FieldDefinition,
    MenuItem,
    MenuSchema,
    PanelDescriptor,
    PropertyInspectorModel,
    PropertyInspectorWidget,
    SceneNode,
    SceneTreeModel,
    SceneTreeWidget,
    ToolInstructionBar,
    ToolbarItem,
    ToolbarSchema,
    VTKViewportWidget,
)


def build_demo() -> ApplicationShell:
    registry = ActionRegistry()
    registry.register(
        ActionDefinition(
            "demo.reset",
            "Reset Demo",
            category="Demo",
            shortcut="Ctrl+R",
            dispatch=lambda _payload: shell.set_status_message("Demo reset"),
        )
    )
    registry.register(ActionDefinition("demo.about", "About Workbench", category="Help"))
    menu = MenuSchema("Demo", (MenuItem(action_id="demo.reset"), MenuItem(action_id="demo.about")))
    toolbar = ToolbarSchema("Demo", (ToolbarItem("demo.reset"),))
    shell = ApplicationShell(action_registry=registry, menu_schemas=(menu,), toolbar_schemas=(toolbar,))

    tree = SceneTreeWidget(
        SceneTreeModel(
            [
                SceneNode("root", "Model", kind="group", renameable=False),
                SceneNode("mesh", "Scan Mesh", parent_id="root", kind="mesh"),
                SceneNode("curve", "Section Curve", parent_id="root", kind="curve"),
            ]
        )
    )
    inspector = PropertyInspectorWidget(
        PropertyInspectorModel(
            [
                FieldDefinition("name", "Name", "Scan Mesh"),
                FieldDefinition("visible", "Visible", True, "checkbox"),
                FieldDefinition("quality", "Quality", "Medium", "combo", options=("Low", "Medium", "High")),
                FieldDefinition("location", "Location", (0.0, 0.0, 0.0), "vector", group="Transform"),
                FieldDefinition("color", "Color", "#00d1ff", "color", group="Display"),
            ]
        )
    )
    viewport = VTKViewportWidget()
    if viewport.available:
        viewport.add_test_geometry()
    palette = CommandPaletteWidget(registry)
    tool_bar = ToolInstructionBar(shell.tool_modes)
    shell.add_panel(PanelDescriptor("scene", "Scene", area="left"), tree)
    shell.add_panel(PanelDescriptor("properties", "Properties", area="right"), inspector)
    shell.add_panel(PanelDescriptor("palette", "Command Palette", area="bottom"), palette)
    shell.set_workspace(viewport)
    shell.set_status_message("Standalone workbench_ui demo")
    shell.statusBar().addPermanentWidget(tool_bar)
    shell.resize(1200, 760)
    return shell


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_demo()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

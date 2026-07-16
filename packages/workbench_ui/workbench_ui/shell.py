"""PySide6 application shell built entirely from reusable contracts."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QMenu,
    QToolBar,
    QWidget,
)

from workbench_ui.contracts import (
    ActionDefinition,
    ActionRegistry,
    CommandPalette,
    DockLayoutManager,
    FrameworkSettings,
    MenuSchema,
    PanelDescriptor,
    PanelRegistry,
    ThemeManager,
    ToolbarSchema,
    ToolModeManager,
)


class ApplicationShell(QMainWindow):
    """Host window for panels, actions, workspace content, and status."""

    def __init__(
        self,
        *,
        action_registry: ActionRegistry | None = None,
        menu_schemas: Iterable[MenuSchema] = (),
        toolbar_schemas: Iterable[ToolbarSchema] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WorkbenchApplicationShell")
        self.action_registry = action_registry or ActionRegistry()
        self.panel_registry = PanelRegistry()
        self.layout_manager = DockLayoutManager()
        self.theme_manager = ThemeManager()
        self.tool_modes = ToolModeManager()
        self.command_palette = CommandPalette(self.action_registry)
        self._qt_actions: dict[str, QAction] = {}
        self._docks: dict[str, QDockWidget] = {}
        self._status_label = QLabel("Ready", self)
        self.statusBar().addPermanentWidget(self._status_label)
        self.action_registry.subscribe(self._sync_qt_action)
        self._build_menus(tuple(menu_schemas))
        self._build_toolbars(tuple(toolbar_schemas))
        self.apply_theme(self.theme_manager.theme.name)

    def _qt_action(self, definition: ActionDefinition) -> QAction:
        action = self._qt_actions.get(definition.id)
        if action is None:
            action = QAction(definition.label, self)
            action.setObjectName(f"action_{definition.id.replace('.', '_')}")
            action.triggered.connect(lambda _checked=False, action_id=definition.id: self.action_registry.invoke(action_id))
            self._qt_actions[definition.id] = action
        self._sync_qt_action(definition)
        return action

    def _sync_qt_action(self, definition: ActionDefinition) -> None:
        action = self._qt_actions.get(definition.id)
        if action is None:
            return
        action.setText(definition.label)
        action.setEnabled(definition.enabled)
        action.setVisible(definition.visible)
        action.setCheckable(definition.checkable)
        action.setChecked(definition.checked)
        if definition.shortcut:
            action.setShortcut(QKeySequence(definition.shortcut))

    def _build_menus(self, schemas: tuple[MenuSchema, ...]) -> None:
        for schema in schemas:
            menu = self.menuBar().addMenu(schema.title)
            self._populate_menu(menu, schema.items)

    def _populate_menu(self, menu: QMenu, items: tuple) -> None:
        for item in items:
            if item.separator:
                menu.addSeparator()
            elif item.children:
                child = menu.addMenu(item.title or "")
                self._populate_menu(child, item.children)
            elif item.action_id:
                menu.addAction(self._qt_action(self.action_registry.require(item.action_id)))

    def _build_toolbars(self, schemas: tuple[ToolbarSchema, ...]) -> None:
        for schema in schemas:
            toolbar = QToolBar(schema.title, self)
            toolbar.setObjectName(f"toolbar_{schema.title.replace(' ', '_')}")
            for item in schema.items:
                toolbar.addAction(self._qt_action(self.action_registry.require(item.action_id)))
            self.addToolBar(toolbar)

    def add_panel(self, descriptor: PanelDescriptor, widget: QWidget) -> QDockWidget:
        self.panel_registry.register(descriptor)
        dock = QDockWidget(descriptor.title, self)
        dock.setObjectName(descriptor.id)
        dock.setWidget(widget)
        features = QDockWidget.DockWidgetMovable
        if descriptor.closable:
            features |= QDockWidget.DockWidgetClosable
        if descriptor.floatable:
            features |= QDockWidget.DockWidgetFloatable
        dock.setFeatures(features)
        area = {
            "left": Qt.LeftDockWidgetArea,
            "right": Qt.RightDockWidgetArea,
            "bottom": Qt.BottomDockWidgetArea,
            "top": Qt.TopDockWidgetArea,
        }.get(descriptor.area, Qt.RightDockWidgetArea)
        self.addDockWidget(area, dock)
        dock.setVisible(descriptor.visible)
        self._docks[descriptor.id] = dock
        return dock

    def show_panel(self, panel_id: str, visible: bool = True) -> QDockWidget:
        self.panel_registry.require(panel_id)
        dock = self._docks[panel_id]
        dock.setVisible(bool(visible))
        return dock

    def focus_panel(self, panel_id: str) -> QDockWidget:
        dock = self.show_panel(panel_id, True)
        dock.raise_()
        widget = dock.widget()
        if widget is not None:
            widget.setFocus(Qt.OtherFocusReason)
        return dock

    def set_workspace(self, widget: QWidget) -> None:
        self.setCentralWidget(widget)

    def set_status_message(self, message: str) -> None:
        self._status_label.setText(str(message))
        self.statusBar().showMessage(str(message))

    def save_framework_settings(self) -> FrameworkSettings:
        state = bytes(self.saveState(self.layout_manager.schema_version))
        self.layout_manager.save(state)
        return FrameworkSettings(layout_state=state, theme=self.theme_manager.theme.name)

    def restore_framework_settings(self, settings: FrameworkSettings) -> bool:
        if not self.layout_manager.restore(settings.layout_state):
            return False
        try:
            restored = bool(
                self.restoreState(
                    settings.layout_state,
                    self.layout_manager.schema_version,
                )
            )
        except (RuntimeError, TypeError, ValueError):
            restored = False
        if not restored:
            self.layout_manager.reset()
        try:
            self.apply_theme(settings.theme)
        except ValueError:
            self.apply_theme("dark")
        return restored

    def reset_layout(self) -> None:
        self.layout_manager.reset()
        for descriptor in self.panel_registry.descriptors:
            dock = self._docks[descriptor.id]
            dock.setFloating(False)
            dock.setVisible(descriptor.visible)

    def apply_theme(self, name: str) -> None:
        theme = self.theme_manager.built_in(name)
        self.theme_manager.set_theme(theme)
        self.setStyleSheet(self.theme_manager.stylesheet())

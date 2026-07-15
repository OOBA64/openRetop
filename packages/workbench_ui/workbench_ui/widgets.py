"""Generic Qt widgets backed by the host-independent workbench models."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from workbench_ui.contracts import (
    ActionRegistry,
    CommandPalette,
    PropertyInspectorModel,
    SceneTreeModel,
    ToolModeManager,
)


class SceneTreeWidget(QWidget):
    selection_changed = Signal(object)
    visibility_changed = Signal(str, bool)

    def __init__(self, model: SceneTreeModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Scene"])
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._item_changed)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tree)
        self.refresh()

    def refresh(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        items: dict[str, QTreeWidgetItem] = {}
        for node in self.model.nodes.values():
            item = QTreeWidgetItem([node.label])
            item.setData(0, Qt.UserRole, node.id)
            item.setCheckState(0, Qt.Checked if node.visible else Qt.Unchecked)
            items[node.id] = item
            if node.parent_id and node.parent_id in items:
                items[node.parent_id].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _selection_changed(self) -> None:
        ids = [item.data(0, Qt.UserRole) for item in self.tree.selectedItems()]
        self.selection_changed.emit(self.model.select(ids))

    def _item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        node_id = str(item.data(0, Qt.UserRole))
        if node_id not in self.model.nodes:
            return
        visible = item.checkState(0) == Qt.Checked
        self.model.set_visible(node_id, visible)
        self.visibility_changed.emit(node_id, visible)


class PropertyInspectorWidget(QWidget):
    value_changed = Signal(str, object)

    def __init__(self, model: PropertyInspectorModel | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model or PropertyInspectorModel()
        self.form = QFormLayout(self)
        self._editors: dict[str, QLineEdit] = {}
        self.refresh()

    def refresh(self) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._editors.clear()
        for field in self.model.fields:
            editor = QLineEdit(str(field.value) if field.value is not None else "", self)
            editor.setObjectName(f"property_{field.id}")
            editor.editingFinished.connect(lambda field_id=field.id, widget=editor: self._apply(field_id, widget))
            self.form.addRow(field.label, editor)
            self._editors[field.id] = editor

    def _apply(self, field_id: str, editor: QLineEdit) -> None:
        value = editor.text()
        self.model.set_value(field_id, value)
        self.value_changed.emit(field_id, value)


class ToolInstructionBar(QWidget):
    def __init__(self, tool_modes: ToolModeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QLabel("Ready", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self.label)
        tool_modes.subscribe(self._update)

    def _update(self, state: object) -> None:
        instructions = getattr(state, "instructions", "")
        self.label.setText(instructions or "Ready")


class CommandPaletteWidget(QWidget):
    action_triggered = Signal(str)

    def __init__(self, registry: ActionRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = CommandPalette(registry)
        self.search = QLineEdit(self)
        self.results = QListWidget(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.results)
        self.search.textChanged.connect(self.refresh)
        self.results.itemDoubleClicked.connect(self._trigger)
        self.refresh("")

    def refresh(self, query: str) -> None:
        self.results.clear()
        for definition in self.palette.search(query):
            item = QListWidgetItem(f"{definition.label}  ·  {definition.id}")
            item.setData(Qt.UserRole, definition.id)
            self.results.addItem(item)

    def _trigger(self, item: QListWidgetItem) -> None:
        self.action_triggered.emit(str(item.data(Qt.UserRole)))

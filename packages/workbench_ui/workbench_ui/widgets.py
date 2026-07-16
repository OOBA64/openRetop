"""Generic Qt widgets backed by the host-independent workbench models."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from workbench_ui.contracts import (
    ActionRegistry,
    CommandPalette,
    FieldDefinition,
    PropertyInspectorModel,
    SceneTreeModel,
    ToolModeManager,
)


class SceneTreeWidget(QWidget):
    """Reusable hierarchy with selection, visibility, rename, and context actions."""

    selection_changed = Signal(object)
    visibility_changed = Signal(str, bool)
    renamed = Signal(str, str)
    context_action_requested = Signal(str, object)

    def __init__(self, model: SceneTreeModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Scene"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tree)
        self.refresh()

    def refresh(self) -> None:
        selected_ids = set(self.model.selected_ids)
        self.tree.blockSignals(True)
        self.tree.clear()
        items: dict[str, QTreeWidgetItem] = {}
        for node in self.model.nodes.values():
            item = QTreeWidgetItem([node.label])
            item.setData(0, Qt.UserRole, node.id)
            item.setData(0, Qt.UserRole + 1, node.label)
            item.setCheckState(0, Qt.Checked if node.visible else Qt.Unchecked)
            flags = item.flags() | Qt.ItemIsUserCheckable
            if node.renameable:
                flags |= Qt.ItemIsEditable
            if not node.selectable:
                flags &= ~Qt.ItemIsSelectable
            if node.reorderable:
                flags |= Qt.ItemIsDragEnabled
            item.setFlags(flags)
            items[node.id] = item
        for node in self.model.nodes.values():
            item = items[node.id]
            if node.parent_id and node.parent_id in items:
                items[node.parent_id].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            item.setSelected(node.id in selected_ids)
        self.tree.setDragDropMode(
            QAbstractItemView.InternalMove
            if any(node.reorderable for node in self.model.nodes.values())
            else QAbstractItemView.NoDragDrop
        )
        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _selection_changed(self) -> None:
        ids = [str(item.data(0, Qt.UserRole)) for item in self.tree.selectedItems()]
        self.selection_changed.emit(self.model.select(ids))

    def _item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        node_id = str(item.data(0, Qt.UserRole))
        node = self.model.nodes.get(node_id)
        if node is None:
            return
        previous_label = str(item.data(0, Qt.UserRole + 1) or node.label)
        next_label = item.text(0).strip()
        if next_label != previous_label:
            try:
                self.model.rename(node_id, next_label)
            except ValueError:
                item.setText(0, previous_label)
            else:
                item.setData(0, Qt.UserRole + 1, next_label)
                self.renamed.emit(node_id, next_label)
        visible = item.checkState(0) == Qt.Checked
        if visible != node.visible:
            self.model.set_visible(node_id, visible)
            self.visibility_changed.emit(node_id, visible)

    def _context_menu(self, position: object) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            return
        node_id = str(item.data(0, Qt.UserRole))
        node = self.model.nodes.get(node_id)
        if node is None:
            return
        action_ids = tuple(node.metadata.get("context_actions", ()))
        if not action_ids:
            return
        menu = QMenu(self)
        for action_id in action_ids:
            action = menu.addAction(
                str(action_id).replace("_", " ").replace(".", " · ").title()
            )
            action.setData(str(action_id))
        selected = menu.exec(self.tree.viewport().mapToGlobal(position))
        if selected is not None:
            context = self.model.select([node_id])
            self.context_action_requested.emit(str(selected.data()), context)


class PropertyInspectorWidget(QWidget):
    """Editor factory for live and apply/cancel property models."""

    value_changed = Signal(str, object)
    validation_failed = Signal(str, str)
    applied = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        model: PropertyInspectorModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model or PropertyInspectorModel()
        self.layout = QVBoxLayout(self)
        self._editors: dict[str, QWidget] = {}
        self._groups: dict[str, QGroupBox] = {}
        self.refresh()

    def set_model(self, model: PropertyInspectorModel) -> None:
        self.model = model
        self.refresh()

    def refresh(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._editors.clear()
        self._groups.clear()
        group_forms: dict[tuple[str, bool], QFormLayout] = {}
        for field in self.model.fields:
            group_key = (field.group, field.advanced)
            form = group_forms.get(group_key)
            if form is None:
                title = f"{field.group} · Advanced" if field.advanced else field.group
                group = QGroupBox(title, self)
                group.setObjectName(
                    f"property_group_{title.casefold().replace(' ', '_').replace('·', 'advanced')}"
                )
                if field.advanced:
                    group.setCheckable(True)
                    group.setChecked(False)
                form = QFormLayout(group)
                group_forms[group_key] = form
                self._groups[title] = group
                self.layout.addWidget(group)
            editor = self._make_editor(field)
            form.addRow(field.label, editor)
            self._editors[field.id] = editor
        if self.model.mode == "apply":
            buttons = QWidget(self)
            row = QHBoxLayout(buttons)
            apply_button = QPushButton("Apply", buttons)
            cancel_button = QPushButton("Cancel", buttons)
            apply_button.clicked.connect(self._apply_pending)
            cancel_button.clicked.connect(self._cancel_pending)
            row.addWidget(apply_button)
            row.addWidget(cancel_button)
            self.layout.addWidget(buttons)
        self.layout.addStretch(1)

    def _make_editor(self, field: FieldDefinition) -> QWidget:
        field_id = field.id
        value = self.model.value(field_id)
        if field.editor == "readonly" or field.read_only:
            editor: QWidget = QLabel("" if value is None else str(value), self)
        elif field.editor == "checkbox":
            checkbox = QCheckBox(self)
            checkbox.setChecked(bool(value))
            checkbox.toggled.connect(
                lambda checked, current=field_id: self._commit(current, checked)
            )
            editor = checkbox
        elif field.editor == "combo":
            combo = QComboBox(self)
            for option in field.options:
                combo.addItem(str(option), option)
            index = combo.findText(str(value))
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(
                lambda _index, current=field_id, widget=combo: self._commit(
                    current, widget.currentData()
                )
            )
            editor = combo
        elif field.editor == "slider":
            slider = QSlider(Qt.Horizontal, self)
            slider.setMinimum(int(field.minimum if field.minimum is not None else 0))
            slider.setMaximum(int(field.maximum if field.maximum is not None else 100))
            slider.setValue(int(value or 0))
            slider.valueChanged.connect(
                lambda next_value, current=field_id: self._commit(current, next_value)
            )
            editor = slider
        elif field.editor == "number":
            number = QDoubleSpinBox(self)
            number.setDecimals(field.decimals)
            number.setRange(
                float(field.minimum if field.minimum is not None else -1.0e12),
                float(field.maximum if field.maximum is not None else 1.0e12),
            )
            number.setSingleStep(float(field.step or 0.1))
            number.setValue(float(value or 0.0))
            number.editingFinished.connect(
                lambda current=field_id, widget=number: self._commit(
                    current, widget.value()
                )
            )
            editor = number
        else:
            line = QLineEdit(self)
            if field.editor == "vector" and isinstance(value, (tuple, list)):
                line.setText(", ".join(str(component) for component in value))
            else:
                line.setText("" if value is None else str(value))
            line.editingFinished.connect(
                lambda current=field_id, widget=line, kind=field.editor: self._commit(
                    current, self._line_value(widget.text(), kind)
                )
            )
            editor = line
        editor.setObjectName(f"property_{field_id}")
        return editor

    @staticmethod
    def _line_value(value: str, editor_type: str) -> object:
        if editor_type == "vector":
            components = [item.strip() for item in value.split(",")]
            if len(components) != 3:
                raise ValueError("Vectors require three comma-separated values.")
            return tuple(float(item) for item in components)
        return value

    def _commit(self, field_id: str, value: object) -> None:
        try:
            self.model.set_value(field_id, value)
        except (KeyError, TypeError, ValueError) as exc:
            self.validation_failed.emit(field_id, str(exc))
            return
        self.value_changed.emit(field_id, value)

    def _apply_pending(self) -> None:
        values = self.model.apply()
        self.applied.emit(values)

    def _cancel_pending(self) -> None:
        self.model.cancel()
        self.refresh()
        self.cancelled.emit()


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
        self.search.setPlaceholderText("Search commands")
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

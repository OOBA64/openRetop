"""Generic Qt widgets backed by the host-independent workbench models."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
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
    QStyle,
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
        self.tree.viewport().installEventFilter(self)
        self._checkbox_interaction = False
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
            flags = item.flags()
            if node.checkable:
                item.setCheckState(0, Qt.Checked if node.visible else Qt.Unchecked)
                flags |= Qt.ItemIsUserCheckable
            else:
                flags &= ~Qt.ItemIsUserCheckable
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
        # Clicking a visibility indicator must not implicitly replace the
        # application selection.  The subsequent model refresh restores the
        # prior visual selection from ``selected_ids``.
        if self._checkbox_interaction:
            return
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
        if node.checkable and visible != node.visible:
            self.model.set_visible(node_id, visible)
            self.visibility_changed.emit(node_id, visible)

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802 - Qt API
        if watched is self.tree.viewport() and isinstance(event, QMouseEvent):
            if event.type() == QEvent.MouseButtonPress:
                self._checkbox_interaction = self._is_checkbox_press(event)
            elif event.type() == QEvent.MouseButtonRelease:
                self._checkbox_interaction = False
        return super().eventFilter(watched, event)

    def _is_checkbox_press(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        item = self.tree.itemAt(event.position().toPoint())
        if item is None:
            return False
        node = self.model.nodes.get(str(item.data(0, Qt.UserRole)))
        if node is None or not node.checkable:
            return False
        row = self.tree.visualItemRect(item)
        indicator_width = self.tree.style().pixelMetric(
            QStyle.PixelMetric.PM_IndicatorWidth,
            None,
            self.tree,
        )
        # visualItemRect starts at the item's indented content area on Qt's
        # native tree implementation.  Include a small style-independent pad.
        return row.left() <= int(event.position().x()) <= row.left() + indicator_width + 8

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


AXIS_LABEL_COLORS = ("#e5484d", "#46a758", "#3e8ef7")  # X, Y, Z: the viewport's axis colours


class VectorEditor(QWidget):
    """Three labelled number boxes (X, Y, Z), stacked like Blender's transform panel."""

    committed = Signal(object)

    def __init__(self, value: object, decimals: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.boxes: list[QDoubleSpinBox] = []
        for name, color in zip(("X", "Y", "Z"), AXIS_LABEL_COLORS):
            row = QHBoxLayout()
            row.setSpacing(6)
            label = QLabel(name, self)
            label.setObjectName(f"vector_axis_{name.lower()}")
            label.setStyleSheet(f"color: {color}; font-weight: 600;")
            label.setFixedWidth(12)
            box = QDoubleSpinBox(self)
            box.setObjectName(f"vector_{name.lower()}")
            box.setDecimals(decimals)
            box.setRange(-1.0e12, 1.0e12)
            box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            box.setKeyboardTracking(False)
            box.editingFinished.connect(self._emit)
            row.addWidget(label)
            row.addWidget(box, 1)
            layout.addLayout(row)
            self.boxes.append(box)
        self.set_value(value)

    def value(self) -> tuple[float, float, float]:
        return (self.boxes[0].value(), self.boxes[1].value(), self.boxes[2].value())

    def set_value(self, value: object) -> None:
        try:
            components = [float(item) for item in value]  # type: ignore[union-attr]
        except (TypeError, ValueError):
            return
        if len(components) != 3:
            return
        for box, component in zip(self.boxes, components):
            if box.hasFocus():
                continue  # never overwrite what the user is typing
            box.blockSignals(True)
            box.setValue(component)
            box.blockSignals(False)

    def _emit(self) -> None:
        self.committed.emit(self.value())


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

    def show_values(self, values: dict[str, object]) -> None:
        """Update shown values in place (no rebuild, no signals), e.g. live during a drag.

        Fields that are not shown are ignored; a box the user is typing in is left alone.
        """

        for field_id, value in values.items():
            editor = self._editors.get(field_id)
            if isinstance(editor, VectorEditor):
                editor.set_value(value)
            elif isinstance(editor, QDoubleSpinBox) and not editor.hasFocus():
                try:
                    number = float(value)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                editor.blockSignals(True)
                editor.setValue(number)
                editor.blockSignals(False)
            elif isinstance(editor, QLabel):
                editor.setText("" if value is None else str(value))

    def refresh(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Detach immediately: deleteLater alone leaves the old group boxes painted
                # (overlapping the new ones) until the event loop runs.
                widget.hide()
                widget.setParent(None)
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
        elif field.editor == "vector":
            vector = VectorEditor(value, field.decimals, self)
            vector.committed.connect(lambda next_value, current=field_id: self._commit(current, next_value))
            editor = vector
        else:
            line = QLineEdit(self)
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
    """Shows what the mouse and keys do in the active tool; hidden when no tool is active."""

    def __init__(self, tool_modes: ToolModeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tool_instruction_bar")
        self.label = QLabel("", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self.label)
        self.setVisible(False)
        tool_modes.subscribe(self._update)

    def _update(self, state: object) -> None:
        instructions = str(getattr(state, "instructions", "") or "")
        active = getattr(state, "phase", "inactive") not in {"inactive", "finished"}
        self.label.setText(instructions)
        self.setVisible(bool(instructions) and active)


class CommandPaletteWidget(QWidget):
    """Searchable command list. Unavailable commands stay visible, greyed, with the reason."""

    action_triggered = Signal(str)

    def __init__(self, registry: ActionRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = CommandPalette(registry)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Type a command, e.g. section, loft, export...")
        self.search.setClearButtonEnabled(True)
        self.results = QListWidget(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.results)
        self.search.textChanged.connect(self.refresh)
        self.search.installEventFilter(self)
        self.results.itemDoubleClicked.connect(self._trigger)
        self.results.itemActivated.connect(self._trigger)
        self.refresh("")

    def refresh(self, query: str = "") -> None:
        self.results.clear()
        for definition in self.palette.search(query, include_disabled=True):
            parts = [definition.label]
            if definition.shortcut:
                parts.append(f"[{definition.shortcut}]")
            text = "  ".join(parts)
            detail = definition.description
            if not definition.enabled and definition.disabled_reason:
                detail = f"needs {definition.disabled_reason}"
            item = QListWidgetItem(f"{text}\n    {detail}" if detail else text)
            item.setData(Qt.UserRole, definition.id)
            item.setToolTip(f"{definition.category}: {definition.description}")
            if not definition.enabled:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)
                item.setForeground(QColor("#7d838c"))
            self.results.addItem(item)
        self._select_first_enabled()

    def _select_first_enabled(self) -> None:
        for row in range(self.results.count()):
            if self.results.item(row).flags() & Qt.ItemIsEnabled:
                self.results.setCurrentRow(row)
                return

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if watched is self.search and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                item = self.results.currentItem()
                if item is not None:
                    self._trigger(item)
                return True
            if key in (Qt.Key_Down, Qt.Key_Up):
                self._move(1 if key == Qt.Key_Down else -1)
                return True
        return super().eventFilter(watched, event)

    def _move(self, step: int) -> None:
        row = self.results.currentRow()
        while 0 <= row + step < self.results.count():
            row += step
            if self.results.item(row).flags() & Qt.ItemIsEnabled:
                self.results.setCurrentRow(row)
                return

    def _trigger(self, item: QListWidgetItem) -> None:
        if item.flags() & Qt.ItemIsEnabled:
            self.action_triggered.emit(str(item.data(Qt.UserRole)))


class CommandPaletteDialog(QDialog):
    """Ctrl+K style popup around CommandPaletteWidget; closes after a command is chosen."""

    action_triggered = Signal(str)

    def __init__(self, registry: ActionRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("command_palette_dialog")
        self.widget = CommandPaletteWidget(registry, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.widget)
        self.resize(560, 420)
        self.widget.action_triggered.connect(self._on_triggered)

    def open_palette(self) -> None:
        self.widget.search.clear()
        self.widget.refresh("")
        parent = self.parentWidget()
        if parent is not None:
            centre = parent.geometry().center()
            self.move(centre.x() - self.width() // 2, parent.geometry().top() + 80)
        self.show()
        self.widget.search.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _on_triggered(self, action_id: str) -> None:
        self.close()
        self.action_triggered.emit(action_id)

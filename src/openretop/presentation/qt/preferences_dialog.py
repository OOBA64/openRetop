"""PySide6 settings editor for the V3 workbench: General, Colours and Keyboard pages.

The Keyboard page lists every command with its shortcut: click a row, press the new keys
(or Clear / Reset), and conflicts are flagged before anything is saved. It replaced a long
single page whose keybinding section ended up below the bottom of the screen, greyed out
behind an "advanced" checkbox, and covered only twelve commands.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from openretop.application.keybindings import shortcut_conflicts, shortcut_overrides, store_shortcut_choices
from openretop.settings.settings_data import DISPLAY_COLOR_FIELDS, AppSettings
from openretop.settings.settings_io import settings_from_dict, settings_to_dict
from workbench_ui import FieldDefinition, PropertyInspectorModel, PropertyInspectorWidget


@dataclass(frozen=True)
class CommandShortcut:
    """One row of the Keyboard page."""

    action_id: str
    label: str
    category: str
    default: str = ""


class PreferencesDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        commands: tuple[CommandShortcut, ...] = (),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("openRetop Preferences")
        self._settings = copy.deepcopy(settings)
        self._commands = tuple(sorted(commands, key=lambda item: (item.category, item.label)))
        self._defaults = {item.action_id: item.default for item in self._commands}
        chosen = shortcut_overrides(self._settings.keybinds, self._settings.future)
        self._choices = {item.action_id: chosen.get(item.action_id, item.default) for item in self._commands}

        self.tabs = QTabWidget(self)
        # live editors: each change lands in the pending settings at once; the dialog's own
        # OK / Cancel decide whether they are kept (no second Apply row inside the page)
        self.model = PropertyInspectorModel(self._general_fields())
        self.inspector = PropertyInspectorWidget(self.model, self)
        self.inspector.value_changed.connect(lambda field_id, value: self._apply_values({field_id: value}))
        self.colors_model = PropertyInspectorModel(self._color_fields())
        self.colors = PropertyInspectorWidget(self.colors_model, self)
        self.colors.value_changed.connect(lambda field_id, value: self._apply_values({field_id: value}))
        self.tabs.addTab(_scrolling(self.inspector), "General")
        self.tabs.addTab(_scrolling(self.colors), "Colours")
        self.tabs.addTab(self._keyboard_page(), "Keyboard")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)
        self.resize(640, 620)  # fits a 768-pixel-high screen; every page scrolls

    # -- results -------------------------------------------------------------------------------

    @property
    def settings(self) -> AppSettings:
        result = copy.deepcopy(self._settings)
        store_shortcut_choices(result.keybinds, result.future, self._choices, self._defaults)
        return result

    @property
    def shortcut_choices(self) -> dict[str, str]:
        return dict(self._choices)

    def conflicts(self) -> dict[str, tuple[str, ...]]:
        return shortcut_conflicts(self._choices)

    # -- general and colours -------------------------------------------------------------------

    def _general_fields(self) -> tuple[FieldDefinition, ...]:
        display = self._settings.display
        return (
            FieldDefinition("default_units", "Default import units", self._settings.import_settings.default_units, "combo", group="Import", options=("mm", "cm", "m", "in")),
            FieldDefinition("proxy_quality", "Default proxy quality", self._settings.import_settings.default_proxy_quality, "combo", group="Import", options=("Low", "Medium", "High", "Full")),
            FieldDefinition("show_grid", "Show grid", display.show_grid, "checkbox", group="Display"),
            FieldDefinition("show_axes", "Show axes", display.show_axes, "checkbox", group="Display"),
            FieldDefinition("show_normals", "Show normals", display.show_normals, "checkbox", group="Display"),
            FieldDefinition("show_axis_gizmo", "Show XYZ axes", display.show_axis_gizmo, "checkbox", group="Display"),
            FieldDefinition("show_viewcube", "Show view cube", display.show_viewcube, "checkbox", group="Display"),
            FieldDefinition("window_width", "Window width", self._settings.ui.window_width, "number", group="Window", minimum=800, maximum=7680, decimals=0),
            FieldDefinition("window_height", "Window height", self._settings.ui.window_height, "number", group="Window", minimum=600, maximum=4320, decimals=0),
        )

    def _color_fields(self) -> tuple[FieldDefinition, ...]:
        display = self._settings.display
        return tuple(
            FieldDefinition(
                f"color.{name}",
                name.replace("_", " ").title(),
                getattr(display, name),
                "color",
                group="Colours",
                validator=_validate_color,
            )
            for name in DISPLAY_COLOR_FIELDS
        )

    def _accept(self) -> None:
        if self.conflicts():
            self.tabs.setCurrentIndex(2)
            self._show_conflicts()
            return
        self.accept()

    def _apply_values(self, values: object) -> None:
        if not isinstance(values, dict):
            return
        data = settings_to_dict(self._settings)
        for field_id, value in values.items():
            if field_id == "proxy_quality":
                data["import"]["default_proxy_quality"] = value
            elif field_id == "default_units":
                data["import"]["default_units"] = value
            elif field_id.startswith("color."):
                data["display"][field_id.split(".", 1)[1]] = value
            elif field_id in {"window_width", "window_height"}:
                data["ui"][field_id] = int(float(value))
            elif field_id in data["display"]:
                data["display"][field_id] = value
        self._settings = settings_from_dict(data)

    # -- keyboard ------------------------------------------------------------------------------

    def _keyboard_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self.filter = QLineEdit(page)
        self.filter.setPlaceholderText("Search commands or keys...")
        self.filter.textChanged.connect(self._filter_rows)
        layout.addWidget(self.filter)
        self.table = QTableWidget(len(self._commands), 3, page)
        self.table.setHorizontalHeaderLabels(("Command", "Group", "Shortcut"))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for row, command in enumerate(self._commands):
            self.table.setItem(row, 0, QTableWidgetItem(command.label))
            self.table.setItem(row, 1, QTableWidgetItem(command.category))
            self.table.setItem(row, 2, QTableWidgetItem(self._choices[command.action_id]))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, command.action_id)
        self.table.currentCellChanged.connect(lambda row, *_: self._select_row(row))
        layout.addWidget(self.table, 1)
        editor_row = QHBoxLayout()
        editor_row.addWidget(QLabel("New shortcut:", page))
        self.key_editor = QKeySequenceEdit(page)
        self.key_editor.setMaximumSequenceLength(1)
        self.key_editor.editingFinished.connect(self._take_key)
        editor_row.addWidget(self.key_editor, 1)
        clear = QPushButton("Clear", page)
        clear.setToolTip("Remove the shortcut from this command.")
        clear.clicked.connect(lambda: self._set_choice(""))
        reset = QPushButton("Default", page)
        reset.setToolTip("Give this command its original shortcut back.")
        reset.clicked.connect(self._reset_choice)
        reset_all = QPushButton("Reset All", page)
        reset_all.clicked.connect(self._reset_all)
        for button in (clear, reset, reset_all):
            editor_row.addWidget(button)
        layout.addLayout(editor_row)
        self.conflict_label = QLabel("", page)
        self.conflict_label.setWordWrap(True)
        self.conflict_label.setObjectName("panel_hint")
        layout.addWidget(self.conflict_label)
        self._show_conflicts()
        return page

    def _current_action(self) -> str | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def _select_row(self, row: int) -> None:
        action = self._current_action()
        self.key_editor.setKeySequence(QKeySequence(self._choices.get(action or "", "")))

    def _take_key(self) -> None:
        sequence = self.key_editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if sequence:
            self._set_choice(sequence)

    def set_shortcut(self, action_id: str, shortcut: str) -> None:
        """Programmatic edit (and what the editor row does for the selected command)."""

        self._choices[action_id] = str(shortcut).strip()
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == action_id:
                self.table.item(row, 2).setText(self._choices[action_id])
        self._show_conflicts()

    def _set_choice(self, shortcut: str) -> None:
        action = self._current_action()
        if action is not None:
            self.set_shortcut(action, shortcut)
            self.key_editor.setKeySequence(QKeySequence(shortcut))

    def _reset_choice(self) -> None:
        action = self._current_action()
        if action is not None:
            self._set_choice(self._defaults.get(action, ""))

    def _reset_all(self) -> None:
        for action_id, default in self._defaults.items():
            self.set_shortcut(action_id, default)

    def _filter_rows(self, text: str) -> None:
        needle = text.strip().casefold()
        for row in range(self.table.rowCount()):
            cells = " ".join(self.table.item(row, column).text() for column in range(3)).casefold()
            self.table.setRowHidden(row, bool(needle) and needle not in cells)

    def _show_conflicts(self) -> None:
        conflicts = self.conflicts()
        labels = {item.action_id: item.label for item in self._commands}
        if conflicts:
            text = "; ".join(f"{key.upper()} is used by {' and '.join(labels.get(i, i) for i in ids)}" for key, ids in conflicts.items())
            self.conflict_label.setText(f"Conflicts (a shared key fires neither command): {text}")
        else:
            self.conflict_label.setText("Click a command, then press the new keys. Changes apply when you press OK.")


def _scrolling(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(widget)
    return area


def _validate_color(value: object) -> str | None:
    text = str(value).strip()
    if len(text) != 7 or not text.startswith("#"):
        return "Colors must use #RRGGBB format."
    try:
        int(text[1:], 16)
    except ValueError:
        return "Colors must use #RRGGBB format."
    return None


__all__ = ("CommandShortcut", "PreferencesDialog")

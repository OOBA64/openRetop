"""PySide6 settings editor for the V3 workbench."""

from __future__ import annotations

import copy

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from settings.settings_data import AppSettings, DISPLAY_COLOR_FIELDS
from settings.settings_io import settings_from_dict, settings_to_dict
from workbench_ui import FieldDefinition, PropertyInspectorModel, PropertyInspectorWidget


class PreferencesDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("openRetop Preferences")
        self._settings = copy.deepcopy(settings)
        self.model = PropertyInspectorModel(self._fields(), mode="apply")
        self.inspector = PropertyInspectorWidget(self.model, self)
        self.inspector.applied.connect(self._apply_values)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply,
            self,
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        apply_button = buttons.button(QDialogButtonBox.Apply)
        if apply_button is not None:
            apply_button.clicked.connect(self._apply_model)
        layout = QVBoxLayout(self)
        layout.addWidget(self.inspector)
        layout.addWidget(buttons)
        self.resize(560, 720)

    @property
    def settings(self) -> AppSettings:
        return copy.deepcopy(self._settings)

    def _fields(self) -> tuple[FieldDefinition, ...]:
        display = self._settings.display
        keybinds = self._settings.keybinds
        fields: list[FieldDefinition] = [
            FieldDefinition("proxy_quality", "Default proxy quality", self._settings.import_settings.default_proxy_quality, "combo", group="Import", options=("Low", "Medium", "High", "Full")),
            FieldDefinition("show_grid", "Show grid", display.show_grid, "checkbox", group="Display"),
            FieldDefinition("show_axes", "Show axes", display.show_axes, "checkbox", group="Display"),
            FieldDefinition("show_normals", "Show normals", display.show_normals, "checkbox", group="Display"),
            FieldDefinition("show_axis_gizmo", "Show axis gizmo", display.show_axis_gizmo, "checkbox", group="Display"),
            FieldDefinition("show_viewcube", "Show view controls", display.show_viewcube, "checkbox", group="Display"),
            FieldDefinition("window_width", "Window width", self._settings.ui.window_width, "number", group="Window", minimum=800, maximum=7680, decimals=0),
            FieldDefinition("window_height", "Window height", self._settings.ui.window_height, "number", group="Window", minimum=600, maximum=4320, decimals=0),
        ]
        fields.extend(
            FieldDefinition(
                f"color.{name}",
                name.replace("_", " ").title(),
                getattr(display, name),
                "color",
                group="Colors",
                advanced=True,
                validator=_validate_color,
            )
            for name in DISPLAY_COLOR_FIELDS
        )
        fields.extend(
            FieldDefinition(
                f"keybind.{name}",
                name.replace("_", " ").title(),
                getattr(keybinds, name),
                "text",
                group="Keybindings",
                advanced=True,
                validator=_validate_nonempty,
            )
            for name in keybinds.__dataclass_fields__
        )
        return tuple(fields)

    def _apply_model(self) -> None:
        self._apply_values(self.model.apply())

    def _accept(self) -> None:
        self._apply_model()
        self.accept()

    def _apply_values(self, values: object) -> None:
        if not isinstance(values, dict):
            return
        data = settings_to_dict(self._settings)
        for field_id, value in values.items():
            if field_id == "proxy_quality":
                data["import"]["default_proxy_quality"] = value
            elif field_id.startswith("color."):
                data["display"][field_id.split(".", 1)[1]] = value
            elif field_id.startswith("keybind."):
                data["keybinds"][field_id.split(".", 1)[1]] = value
            elif field_id in {"window_width", "window_height"}:
                data["ui"][field_id] = int(float(value))
            elif field_id in data["display"]:
                data["display"][field_id] = value
        self._settings = settings_from_dict(data)


def _validate_color(value: object) -> str | None:
    text = str(value).strip()
    if len(text) != 7 or not text.startswith("#"):
        return "Colors must use #RRGGBB format."
    try:
        int(text[1:], 16)
    except ValueError:
        return "Colors must use #RRGGBB format."
    return None


def _validate_nonempty(value: object) -> str | None:
    return None if str(value).strip() else "Keybindings cannot be empty."


__all__ = ("PreferencesDialog",)

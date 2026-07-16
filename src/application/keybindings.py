"""Map persisted keybinding fields to stable V3 action identifiers."""

from __future__ import annotations

from dataclasses import fields

from settings.settings_data import AppKeybindSettings


KEYBIND_ACTION_BY_FIELD = {
    "undo": "edit.undo",
    "redo": "edit.redo",
    "rename_selected": "scene.rename_selected",
    "toggle_visibility": "scene.toggle_visibility",
    "isolate_selected": "scene.isolate_selected",
    "show_all": "scene.show_all",
    "frame_selected": "view.frame_selected",
    "move": "transform.move",
    "rotate": "transform.rotate",
    "confirm_transform": "transform.confirm",
    "cancel_transform": "transform.cancel",
    "delete_selected": "scene.delete_selected",
}


def shortcut_overrides(keybinds: AppKeybindSettings) -> dict[str, str]:
    return {
        action_id: str(getattr(keybinds, field_name)).strip()
        for field_name, action_id in KEYBIND_ACTION_BY_FIELD.items()
        if str(getattr(keybinds, field_name)).strip()
    }


def action_for_shortcut(
    keybinds: AppKeybindSettings, shortcut: str
) -> str | None:
    normalized = str(shortcut).strip().lower()
    for item in fields(keybinds):
        value = str(getattr(keybinds, item.name)).strip().lower()
        if value == normalized:
            return KEYBIND_ACTION_BY_FIELD.get(item.name)
    if normalized == "ctrl+shift+z":
        return "edit.redo"
    return None


__all__ = ("KEYBIND_ACTION_BY_FIELD", "action_for_shortcut", "shortcut_overrides")

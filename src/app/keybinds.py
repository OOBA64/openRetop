"""Keybind labels and Tk event normalization for openRetop."""

from __future__ import annotations

from dataclasses import fields

from settings.settings_data import AppKeybindSettings


KEYBIND_DISPLAY_ORDER: tuple[tuple[str, str], ...] = (
    ("undo", "Undo"),
    ("redo", "Redo"),
    ("rename_selected", "Rename Selected"),
    ("toggle_visibility", "Toggle Visibility"),
    ("isolate_selected", "Isolate Selected"),
    ("show_all", "Show All"),
    ("frame_selected", "Frame Selected"),
    ("move", "Move"),
    ("rotate", "Rotate"),
    ("confirm_transform", "Confirm Transform"),
    ("cancel_transform", "Cancel Transform"),
    ("delete_selected", "Delete Selected"),
)

KEYBIND_ACTION_BY_FIELD = {
    field_name: field_name for field_name, _label in KEYBIND_DISPLAY_ORDER
}


def keybind_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(AppKeybindSettings))


def shortcut_from_tk_event(event: object) -> str | None:
    key = str(getattr(event, "keysym", "") or "")
    if not key:
        return None

    state = int(getattr(event, "state", 0) or 0)
    modifiers: list[str] = []
    if state & 0x0004:
        modifiers.append("Ctrl")
    if state & 0x0001:
        modifiers.append("Shift")
    if state & 0x0008:
        modifiers.append("Alt")

    key_label = _key_label(key)
    if key_label is None:
        return None
    if modifiers:
        return f"{'+'.join(modifiers)}+{key_label}"
    return key_label


def action_for_shortcut(
    keybinds: AppKeybindSettings,
    shortcut: str,
) -> str | None:
    normalized = shortcut.strip()
    for field_name in keybind_field_names():
        if str(getattr(keybinds, field_name)).strip() == normalized:
            return KEYBIND_ACTION_BY_FIELD[field_name]
    if normalized == "Ctrl+Shift+Z":
        return "redo"
    return None


def _key_label(key: str) -> str | None:
    aliases = {
        "Return": "Enter",
        "Escape": "Esc",
        "BackSpace": "Backspace",
        "Delete": "Delete",
        "F2": "F2",
    }
    if key in aliases:
        return aliases[key]
    if len(key) == 1 and key.isalpha():
        return key.upper()
    return None

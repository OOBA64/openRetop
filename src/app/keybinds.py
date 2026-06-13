"""Keybind labels and Tk event normalization for openRetop."""

from __future__ import annotations

from dataclasses import fields

from settings.settings_data import AppKeybindSettings


KEYBIND_DISPLAY_ORDER: tuple[tuple[str, str], ...] = (
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
    prefix = ""
    if state & 0x0008:
        prefix = "Alt+"
    elif state & 0x0001:
        prefix = "Shift+"

    key_label = _key_label(key)
    if key_label is None:
        return None
    return f"{prefix}{key_label}"


def action_for_shortcut(
    keybinds: AppKeybindSettings,
    shortcut: str,
) -> str | None:
    normalized = shortcut.strip()
    for field_name in keybind_field_names():
        if str(getattr(keybinds, field_name)).strip() == normalized:
            return KEYBIND_ACTION_BY_FIELD[field_name]
    return None


def _key_label(key: str) -> str | None:
    aliases = {
        "Return": "Enter",
        "Escape": "Esc",
        "Delete": "Delete",
        "F2": "F2",
    }
    if key in aliases:
        return aliases[key]
    if len(key) == 1 and key.isalpha():
        return key.upper()
    return None

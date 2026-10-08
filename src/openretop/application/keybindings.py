"""Map persisted keybinding fields to stable V3 action identifiers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields

from openretop.settings.settings_data import AppKeybindSettings

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


# settings.future key holding every other command's chosen shortcut: {action id: key or ""}
SHORTCUTS_SETTING = "shortcuts"


def shortcut_overrides(keybinds: AppKeybindSettings, future: Mapping[str, object] | None = None) -> dict[str, str]:
    """Shortcuts the user chose, by action id ("" removes an action's default key).

    The twelve classic bindings live in ``keybinds``; any other command's choice lives in
    ``future["shortcuts"]`` (the Keyboard page of Preferences can set every command).
    """

    result = {
        action_id: str(getattr(keybinds, field_name)).strip()
        for field_name, action_id in KEYBIND_ACTION_BY_FIELD.items()
        if str(getattr(keybinds, field_name)).strip()
    }
    extra = (future or {}).get(SHORTCUTS_SETTING)
    if isinstance(extra, Mapping):
        for action_id, value in extra.items():
            result[str(action_id)] = str(value or "").strip()
    return result


def store_shortcut_choices(
    keybinds: AppKeybindSettings,
    future: dict[str, object],
    choices: Mapping[str, str],
    defaults: Mapping[str, str | None],
) -> None:
    """Write the Keyboard page's choices back into the settings (in place)."""

    field_by_action = {action_id: name for name, action_id in KEYBIND_ACTION_BY_FIELD.items()}
    extra: dict[str, str] = {}
    for action_id, value in choices.items():
        value = str(value or "").strip()
        field_name = field_by_action.get(action_id)
        if field_name is not None and value:
            setattr(keybinds, field_name, value)
            continue
        if value != str(defaults.get(action_id) or "").strip():
            extra[action_id] = value  # includes "" for a removed key
    if extra:
        future[SHORTCUTS_SETTING] = extra
    else:
        future.pop(SHORTCUTS_SETTING, None)


def shortcut_conflicts(shortcuts: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    """Keys given to more than one command (Qt then fires neither)."""

    owners: dict[str, list[str]] = {}
    for action_id, value in shortcuts.items():
        key = str(value or "").strip().casefold()
        if key:
            owners.setdefault(key, []).append(action_id)
    return {key: tuple(ids) for key, ids in owners.items() if len(ids) > 1}


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


__all__ = (
    "KEYBIND_ACTION_BY_FIELD",
    "SHORTCUTS_SETTING",
    "action_for_shortcut",
    "shortcut_conflicts",
    "shortcut_overrides",
    "store_shortcut_choices",
)

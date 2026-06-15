"""Preferences dialog construction for openRetop."""

from __future__ import annotations

from dataclasses import dataclass
from tkinter import BooleanVar, StringVar, Toplevel
from tkinter import ttk
from typing import Callable, Sequence

from app.keybinds import KEYBIND_DISPLAY_ORDER
from settings.settings_data import AppSettings


@dataclass
class PreferencesDialogHandle:
    dialog: Toplevel
    notebook: ttk.Notebook
    variables: dict[str, BooleanVar | StringVar]


def build_preferences_dialog(
    parent: object,
    *,
    settings: AppSettings,
    proxy_quality_labels: Sequence[str],
    apply_callback: Callable[[], None],
    ok_callback: Callable[[], None],
    close_callback: Callable[[], None],
    placeholder_callback: Callable[[str], None],
) -> PreferencesDialogHandle:
    dialog = Toplevel(parent)
    dialog.title("Preferences")
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.protocol("WM_DELETE_WINDOW", close_callback)
    dialog.columnconfigure(0, weight=1)

    variables: dict[str, BooleanVar | StringVar] = {
        "window_mode": StringVar(master=dialog, value=settings.ui.window_mode),
        "remember_window_size": BooleanVar(
            master=dialog,
            value=settings.ui.remember_window_size,
        ),
        "show_grid": BooleanVar(master=dialog, value=settings.display.show_grid),
        "show_axes": BooleanVar(master=dialog, value=settings.display.show_axes),
        "show_axis_gizmo": BooleanVar(
            master=dialog,
            value=settings.display.show_axis_gizmo,
        ),
        "show_viewcube": BooleanVar(
            master=dialog,
            value=settings.display.show_viewcube,
        ),
        "default_proxy_quality": StringVar(
            master=dialog,
            value=settings.import_settings.default_proxy_quality,
        ),
    }
    for field_name, _label in KEYBIND_DISPLAY_ORDER:
        variables[f"keybind.{field_name}"] = StringVar(
            master=dialog,
            value=str(getattr(settings.keybinds, field_name)),
        )

    content = ttk.Frame(dialog, padding=12)
    content.grid(row=0, column=0, sticky="nsew")
    content.columnconfigure(0, weight=1)

    notebook = ttk.Notebook(content)
    notebook.grid(row=0, column=0, sticky="nsew")
    content.rowconfigure(0, weight=1)

    _build_general_tab(notebook, variables, proxy_quality_labels)
    _build_viewport_tab(notebook, variables)
    _build_keybinds_tab(notebook, variables)
    _build_advanced_tab(notebook, placeholder_callback)

    buttons = ttk.Frame(content)
    buttons.grid(row=1, column=0, sticky="e", pady=(12, 0))
    ttk.Button(buttons, text="OK", command=ok_callback).grid(row=0, column=0)
    ttk.Button(buttons, text="Cancel", command=close_callback).grid(
        row=0,
        column=1,
        padx=(6, 0),
    )
    ttk.Button(buttons, text="Apply", command=apply_callback).grid(
        row=0,
        column=2,
        padx=(6, 0),
    )

    return PreferencesDialogHandle(
        dialog=dialog,
        notebook=notebook,
        variables=variables,
    )


def _build_general_tab(
    notebook: ttk.Notebook,
    variables: dict[str, BooleanVar | StringVar],
    proxy_quality_labels: Sequence[str],
) -> None:
    tab = ttk.Frame(notebook, padding=10)
    tab.columnconfigure(1, weight=1)
    notebook.add(tab, text="General")

    ttk.Label(tab, text="Startup window mode").grid(row=0, column=0, sticky="w", pady=2)
    ttk.Combobox(
        tab,
        textvariable=variables["window_mode"],
        values=("maximized", "remembered_size"),
        width=18,
        state="readonly",
    ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
    ttk.Checkbutton(
        tab,
        text="Remember last window size",
        variable=variables["remember_window_size"],
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 2))
    ttk.Label(tab, text="Default Proxy Quality").grid(row=2, column=0, sticky="w", pady=2)
    ttk.Combobox(
        tab,
        textvariable=variables["default_proxy_quality"],
        values=tuple(proxy_quality_labels),
        width=12,
        state="readonly",
    ).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=2)


def _build_viewport_tab(
    notebook: ttk.Notebook,
    variables: dict[str, BooleanVar | StringVar],
) -> None:
    tab = ttk.Frame(notebook, padding=10)
    tab.columnconfigure(1, weight=1)
    notebook.add(tab, text="Viewport")

    ttk.Checkbutton(
        tab,
        text="Default Show Grid",
        variable=variables["show_grid"],
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(
        tab,
        text="Default Show Axes",
        variable=variables["show_axes"],
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
    ttk.Checkbutton(
        tab,
        text="Default Show Axis Gizmo",
        variable=variables["show_axis_gizmo"],
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
    ttk.Checkbutton(
        tab,
        text="Default Show View Controls",
        variable=variables["show_viewcube"],
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))


def _build_keybinds_tab(
    notebook: ttk.Notebook,
    variables: dict[str, BooleanVar | StringVar],
) -> None:
    tab = ttk.Frame(notebook, padding=10)
    tab.columnconfigure(1, weight=1)
    notebook.add(tab, text="Keybinds")

    for row, (field_name, label) in enumerate(KEYBIND_DISPLAY_ORDER):
        ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(
            tab,
            textvariable=variables[f"keybind.{field_name}"],
            width=16,
        ).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)

    start_row = len(KEYBIND_DISPLAY_ORDER) + 1
    ttk.Separator(tab).grid(row=start_row, column=0, columnspan=2, sticky="ew", pady=(8, 6))
    ttk.Label(tab, text="Manual Curve").grid(row=start_row + 1, column=0, sticky="w", pady=2)
    for offset, (label, shortcut) in enumerate(
        (
            ("Finish Curve", "Enter"),
            ("Cancel", "Esc"),
            ("Remove Last Point", "Backspace"),
            ("Toggle Closed", "C"),
        ),
        start=2,
    ):
        row = start_row + offset
        ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Label(tab, text=shortcut).grid(row=row, column=1, sticky="w", padx=(8, 0), pady=2)


def _build_advanced_tab(
    notebook: ttk.Notebook,
    placeholder_callback: Callable[[str], None],
) -> None:
    tab = ttk.Frame(notebook, padding=10)
    tab.columnconfigure(0, weight=1)
    notebook.add(tab, text="Advanced")

    for row, label in enumerate(("Reset Preferences", "Diagnostics")):
        ttk.Button(
            tab,
            text=label,
            command=lambda item=label: placeholder_callback(item),
        ).grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else 6, 0))

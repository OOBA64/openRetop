"""Design tokens and the application stylesheet.

One place decides how the workbench looks: surfaces in three elevations, two text levels, a
single accent, the X/Y/Z axis colours shared with the viewport, a spacing and radius scale.
``build_stylesheet`` turns a token set into a Qt stylesheet that covers every widget the
workbench uses, so nothing falls back to the stock platform look.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"

DARK: Mapping[str, str] = {
    # surfaces, darkest to lightest
    "window": "#15171b",  # behind everything: the dock gutters and the status bar
    "panel": "#1c1f24",  # docks, toolbars, menus
    "raised": "#252930",  # inputs, buttons
    "hover": "#2d323a",
    "pressed": "#353b45",
    "border": "#2a2e35",
    "border_strong": "#3a404a",
    # text
    "text": "#e4e7eb",
    "text_muted": "#959ca7",
    "text_faint": "#646b76",
    # accent and states
    "accent": "#4c8dff",
    "accent_hover": "#6aa1ff",
    "accent_text": "#ffffff",
    "accent_soft": "rgba(76, 141, 255, 0.20)",
    "warning": "#f0a43a",
    "danger": "#e5484d",
    "success": "#46a758",
    # the viewport's axis colours, for X/Y/Z labels in the panels
    "axis_x": "#e5484d",
    "axis_y": "#46a758",
    "axis_z": "#3e8ef7",
    # the 3D view behind the scene (a vertical gradient)
    "viewport_top": "#2b3038",
    "viewport_bottom": "#121418",
}

LIGHT: Mapping[str, str] = {
    "window": "#e9ebee",
    "panel": "#f6f7f9",
    "raised": "#ffffff",
    "hover": "#eceef2",
    "pressed": "#dfe3e8",
    "border": "#d9dde3",
    "border_strong": "#c3c9d1",
    "text": "#17191c",
    "text_muted": "#5b6470",
    "text_faint": "#8a929d",
    "accent": "#2f6fdb",
    "accent_hover": "#4a84e6",
    "accent_text": "#ffffff",
    "accent_soft": "rgba(47, 111, 219, 0.16)",
    "warning": "#b86e00",
    "danger": "#c8323a",
    "success": "#2f8a43",
    "axis_x": "#c8323a",
    "axis_y": "#2f8a43",
    "axis_z": "#2f6fdb",
    "viewport_top": "#c9cfd8",
    "viewport_bottom": "#eef0f3",
}

FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", sans-serif'
FONT_SIZE = "9pt"
RADIUS = 6  # px: inputs, buttons, menus
SMALL_RADIUS = 4


def tokens(colors: Mapping[str, str]) -> dict[str, str]:
    """A complete token set: the dark defaults overridden by ``colors``."""

    merged = dict(DARK)
    merged.update(colors)
    return merged


def _asset(name: str) -> str:
    return (ASSETS / name).as_posix()


def build_stylesheet(colors: Mapping[str, str]) -> str:
    t = tokens(colors)
    check = _asset("check.svg")
    chevron_down = _asset("chevron-down.svg")
    chevron_right = _asset("chevron-right.svg")
    return f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE};
}}
QMainWindow, QDialog {{
    background-color: {t["window"]};
    color: {t["text"]};
}}
QWidget {{
    background-color: transparent;
    color: {t["text"]};
    selection-background-color: {t["accent"]};
    selection-color: {t["accent_text"]};
}}
QMainWindow::separator {{
    background-color: {t["window"]};
    width: 4px;
    height: 4px;
}}
QMainWindow::separator:hover {{
    background-color: {t["accent"]};
}}

/* ---- docks: a quiet uppercase title above a flat panel ---- */
QDockWidget {{
    color: {t["text_muted"]};
}}
QDockWidget::title {{
    background-color: {t["panel"]};
    padding: 7px 10px 5px 10px;
    text-align: left;
    border-bottom: 1px solid {t["border"]};
}}
QDockWidget > QWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: {t["panel"]};
}}
QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: none;
    padding: 2px;
    border-radius: {SMALL_RADIUS}px;
}}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background-color: {t["hover"]};
}}

/* ---- menus ---- */
QMenuBar {{
    background-color: {t["window"]};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    border-radius: {SMALL_RADIUS}px;
}}
QMenuBar::item:selected {{
    background-color: {t["hover"]};
}}
QMenu {{
    background-color: {t["panel"]};
    border: 1px solid {t["border_strong"]};
    border-radius: {RADIUS}px;
    padding: 5px;
}}
QMenu::item {{
    padding: 6px 28px 6px 12px;
    border-radius: {SMALL_RADIUS}px;
}}
QMenu::item:selected {{
    background-color: {t["accent_soft"]};
}}
QMenu::item:disabled {{
    color: {t["text_faint"]};
}}
QMenu::separator {{
    height: 1px;
    background-color: {t["border"]};
    margin: 5px 6px;
}}
QMenu::indicator {{
    width: 14px;
    height: 14px;
    margin-left: 6px;
}}
QMenu::indicator:checked {{
    image: url({check});
}}

/* ---- toolbar ---- */
QToolBar {{
    background-color: {t["window"]};
    border: none;
    border-bottom: 1px solid {t["border"]};
    padding: 3px 6px;
    spacing: 2px;
}}
QToolBar::separator {{
    background-color: {t["border_strong"]};
    width: 1px;
    margin: 5px 6px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {RADIUS}px;
    padding: 4px 8px;
    color: {t["text"]};
}}
QToolButton:hover {{
    background-color: {t["hover"]};
}}
QToolButton:pressed {{
    background-color: {t["pressed"]};
}}
QToolButton:checked {{
    background-color: {t["accent_soft"]};
    border-color: {t["accent"]};
}}
QToolButton:disabled {{
    color: {t["text_faint"]};
}}

/* ---- buttons ---- */
QPushButton {{
    background-color: {t["raised"]};
    border: 1px solid {t["border_strong"]};
    border-radius: {RADIUS}px;
    padding: 6px 12px;
    color: {t["text"]};
    text-align: center;
}}
QPushButton:hover {{
    background-color: {t["hover"]};
}}
QPushButton:pressed {{
    background-color: {t["pressed"]};
}}
QPushButton:disabled {{
    color: {t["text_faint"]};
    border-color: {t["border"]};
}}
QPushButton:flat {{
    background: transparent;
    border: none;
    text-align: left;
    color: {t["accent"]};
}}
QPushButton:flat:hover {{
    background-color: {t["hover"]};
}}
QPushButton[primary="true"] {{
    background-color: {t["accent"]};
    border-color: {t["accent"]};
    color: {t["accent_text"]};
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{
    background-color: {t["accent_hover"]};
}}
QPushButton[primary="true"]:disabled {{
    background-color: {t["raised"]};
    border-color: {t["border"]};
    color: {t["text_faint"]};
}}

/* ---- inputs ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background-color: {t["raised"]};
    border: 1px solid {t["border"]};
    border-radius: {SMALL_RADIUS}px;
    padding: 4px 6px;
    color: {t["text"]};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: {t["border_strong"]};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {t["accent"]};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {t["text_faint"]};
}}
QLineEdit[readOnly="true"] {{
    color: {t["text_muted"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: url({chevron_down});
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {t["panel"]};
    border: 1px solid {t["border_strong"]};
    selection-background-color: {t["accent_soft"]};
    selection-color: {t["text"]};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    border: none;
}}
QCheckBox {{
    spacing: 6px;
}}
QCheckBox::indicator, QTreeView::indicator, QListView::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t["border_strong"]};
    border-radius: 3px;
    background-color: {t["raised"]};
}}
QCheckBox::indicator:hover, QTreeView::indicator:hover {{
    border-color: {t["accent"]};
}}
QCheckBox::indicator:checked, QTreeView::indicator:checked, QListView::indicator:checked {{
    background-color: {t["accent"]};
    border-color: {t["accent"]};
    image: url({check});
}}
QSlider::groove:horizontal {{
    height: 4px;
    background-color: {t["raised"]};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background-color: {t["accent"]};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background-color: {t["text"]};
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}

/* ---- property sections: a heading and a hairline, not a boxed frame ---- */
QGroupBox {{
    border: none;
    border-top: 1px solid {t["border"]};
    margin-top: 16px;
    padding: 12px 2px 2px 2px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 0px;
    top: 2px;
    padding: 0 6px 0 0;
    color: {t["text_muted"]};
}}
QGroupBox::indicator {{
    width: 12px;
    height: 12px;
}}
QFormLayout QLabel, QGroupBox QLabel {{
    color: {t["text_muted"]};
}}

/* ---- trees and lists ---- */
QTreeView, QTreeWidget, QListView, QListWidget {{
    background-color: {t["panel"]};
    border: none;
    outline: none;
    show-decoration-selected: 0;
    selection-background-color: {t["accent_soft"]};
    selection-color: {t["text"]};
}}
QTableView, QTableWidget {{
    background-color: {t["panel"]};
    color: {t["text"]};
    gridline-color: {t["border"]};
    border: 1px solid {t["border"]};
    border-radius: {SMALL_RADIUS}px;
    outline: none;
    selection-background-color: {t["accent_soft"]};
    selection-color: {t["text"]};
}}
QTableView::item {{
    padding: 3px 6px;
    color: {t["text"]};
}}
QTableView::item:hover {{
    background-color: {t["hover"]};
}}
QTableView::item:selected {{
    background-color: {t["accent_soft"]};
    color: {t["text"]};
}}
QTableCornerButton::section {{
    background-color: {t["panel"]};
    border: none;
}}
QTreeView::item {{
    padding: 4px 4px;
}}
QListView::item {{
    padding: 4px 4px;
    border-radius: {SMALL_RADIUS}px;
}}
QTreeView::item:hover, QListView::item:hover {{
    background-color: {t["hover"]};
}}
QTreeView::item:selected, QListView::item:selected {{
    background-color: {t["accent_soft"]};
    color: {t["text"]};
}}
QTreeView::branch {{
    background: transparent;
}}
/* only the row itself is highlighted (a rounded pill), never the indentation gutter */
QTreeView::branch:selected {{
    background: transparent;
}}
QTreeView::branch:has-children:closed {{
    image: url({chevron_right});
}}
QTreeView::branch:has-children:open {{
    image: url({chevron_down});
}}
QHeaderView::section {{
    background-color: {t["panel"]};
    color: {t["text_muted"]};
    border: none;
    border-bottom: 1px solid {t["border"]};
    padding: 4px 6px;
}}

/* ---- scroll bars: thin, no arrows ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle {{
    background-color: {t["border_strong"]};
    border-radius: 3px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::handle:hover {{
    background-color: {t["text_faint"]};
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
    border: none;
    width: 0px;
    height: 0px;
}}

/* ---- status bar, tooltips, tabs, progress ---- */
QStatusBar {{
    background-color: {t["window"]};
    color: {t["text_muted"]};
    border-top: 1px solid {t["border"]};
}}
QStatusBar::item {{
    border: none;
}}
QStatusBar QLabel {{
    color: {t["text_muted"]};
    padding: 0 6px;
}}
QToolTip {{
    background-color: {t["panel"]};
    color: {t["text"]};
    border: 1px solid {t["border_strong"]};
    border-radius: {SMALL_RADIUS}px;
    padding: 6px 8px;
}}
QTabBar::tab {{
    background-color: {t["window"]};
    color: {t["text_muted"]};
    padding: 6px 12px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {t["text"]};
    border-bottom-color: {t["accent"]};
}}
QProgressBar {{
    background-color: {t["raised"]};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {t["accent"]};
    border-radius: 3px;
}}

/* ---- workbench pieces (by object name) ---- */
#tool_instruction_bar {{
    background-color: {t["accent_soft"]};
    border-radius: {SMALL_RADIUS}px;
}}
#next_steps_title {{
    font-size: 12pt;
    font-weight: 600;
    color: {t["text"]};
}}
#next_steps_explanation, #next_step_hint, #next_steps_summary {{
    color: {t["text_muted"]};
}}
#next_steps_section {{
    color: {t["text_faint"]};
    font-weight: 600;
    margin-top: 10px;
}}
#next_steps_cad_note {{
    color: {t["warning"]};
}}
"""


__all__ = ("ASSETS", "DARK", "LIGHT", "build_stylesheet", "tokens")

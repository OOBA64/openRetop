"""The surfacing tool panel (milestone S): one page per tool, ExModel-style.

The panel owns no state. ``show_session`` paints it from the modelling controller's session
and a few facts from the main window; every control emits ``action_requested(action, payload)``
for the main window to dispatch as an ordinary action (so undo, status and busy handling are
the same as for menu commands).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

SURFACE_TYPES = (
    ("auto", "Auto"),
    ("freeform", "Freeform"),
    ("plane", "Plane"),
    ("cylinder", "Cylinder"),
    ("cone", "Cone"),
    ("sphere", "Sphere"),
    ("torus", "Torus"),
)
SELECTION_MODES = (("smart", "Smart"), ("brush", "Brush"), ("erase", "Erase"))
PAGES = ("fit_surface", "loft", "fill", "extend", "trim", "compare")


@dataclass
class PanelFacts:
    """What the panel shows besides the tool session."""

    title: str = ""
    units: str = "mm"
    selected_triangles: int = 0
    preview_text: str = ""
    selected_curves: int = 0
    selected_surfaces: tuple[str, ...] = ()
    fill_sides: tuple[str, ...] = ()
    trim_text: str = ""
    has_pieces: bool = False
    deviation_text: str = ""
    has_deviation: bool = False
    busy: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("panel_section")
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _hint(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("panel_hint")
    return label


def _button(text: str, *, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setObjectName("primary_button")
        button.setDefault(True)
    return button


class SurfacingPanel(QWidget):
    action_requested = Signal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("surfacing_panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.title = QLabel("Surfacing")
        font = self.title.font()
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setBold(True)
        self.title.setFont(font)
        header.addWidget(self.title, 1)
        self.done_button = QPushButton("Done")
        self.done_button.setToolTip("Close the tool (Esc)")
        self.done_button.clicked.connect(lambda: self._emit("model.finish"))
        header.addWidget(self.done_button)
        layout.addLayout(header)
        self.pages = QStackedWidget(self)
        layout.addWidget(self.pages)
        self.status = _hint()
        layout.addWidget(self.status)
        layout.addStretch(1)
        self._page_index: dict[str, int] = {}
        for name, builder in (
            ("fit_surface", self._build_fit),
            ("loft", self._build_loft),
            ("fill", self._build_fill),
            ("extend", self._build_extend),
            ("trim", self._build_trim),
            ("compare", self._build_compare),
        ):
            page = QWidget(self)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(6)
            builder(page_layout)
            page_layout.addStretch(1)  # pack each page to the top (the stack is as tall as the tallest)
            self._page_index[name] = self.pages.addWidget(page)

    # -- painting ------------------------------------------------------------------------------

    def show_session(self, session: Any, facts: PanelFacts) -> None:
        if session is None:
            return
        self.title.setText(facts.title)
        self.pages.setCurrentIndex(self._page_index.get(session.tool, 0))
        blockers = [QSignalBlocker(widget) for widget in self._inputs()]
        try:
            self._show_fit(session, facts)
            self.loft_info.setText(
                f"{facts.selected_curves} curve(s) selected." if facts.selected_curves else "No curves selected."
            )
            self.loft_button.setEnabled(facts.selected_curves >= 2 and not facts.busy)
            self.fill_list.clear()
            self.fill_list.addItems([f"{index + 1}. {label}" for index, label in enumerate(facts.fill_sides)])
            self.fill_on_scan.setChecked(bool(session.fill_on_scan))
            self.fill_button.setEnabled(len(facts.fill_sides) >= 2 and not facts.busy)
            self.extend_distance.setSuffix(f" {facts.units}")
            self.extend_distance.setValue(float(session.extend_distance))
            self.extend_info.setText(
                "Selected: " + ", ".join(facts.selected_surfaces) if facts.selected_surfaces else "Select a surface in the tree or the scene."
            )
            self.extend_button.setEnabled(bool(facts.selected_surfaces) and not facts.busy)
            self.trim_tolerance.setSuffix(f" {facts.units}")
            self.trim_tolerance.setValue(float(session.trim_tolerance))
            self.trim_overlap.setValue(int(round(100 * float(session.trim_overlap))))
            self.trim_overlap_label.setText(f"{int(round(100 * float(session.trim_overlap)))}%")
            self.trim_info.setText(facts.trim_text)
            self.trim_apply.setEnabled(facts.has_pieces and not facts.busy)
            self.trim_compute.setEnabled(not facts.busy)
            self.compare_tolerance.setSuffix(f" {facts.units}")
            self.compare_tolerance.setValue(float(session.fit.tolerance))
            self.compare_info.setText(facts.deviation_text)
            self.compare_clear.setEnabled(facts.has_deviation)
            self.legend.setVisible(facts.has_deviation)
            self.legend_low.setText(f"-{4 * session.fit.tolerance:g}")
            self.legend_high.setText(f"+{4 * session.fit.tolerance:g}")
        finally:
            del blockers
        self.status.setText("Working..." if facts.busy else "")

    def _show_fit(self, session: Any, facts: PanelFacts) -> None:
        for mode, button in self.mode_buttons.items():
            button.setChecked(session.selection_mode == mode)
        brushing = session.selection_mode in ("brush", "erase")
        self.angle.setValue(float(session.smart_angle))
        self.angle.setEnabled(not brushing)
        self.connected.setChecked(bool(session.connected))
        self.connected.setEnabled(not brushing)
        self.brush.setSuffix(f" {facts.units}")
        self.brush.setValue(float(session.brush_radius))
        self.brush.setEnabled(brushing)
        self.selection_info.setText(
            f"{facts.selected_triangles:,} triangles selected" if facts.selected_triangles else "Nothing selected yet"
        )
        for kind, button in self.type_buttons.items():
            button.setChecked(session.fit.kind == kind)
        freeform = session.fit.kind in ("auto", "freeform")
        for widget in (self.control_u, self.control_v, self.smoothness):
            widget.setEnabled(freeform)
        self.control_u.setValue(int(session.fit.control_u))
        self.control_v.setValue(int(session.fit.control_v))
        self.smoothness.setValue(int(round(100 * float(session.fit.smoothness))))
        self.expand.setValue(float(100 * session.fit.expand))
        self.tolerance.setSuffix(f" {facts.units}")
        self.tolerance.setValue(float(session.fit.tolerance))
        self.fit_result.setText(facts.preview_text)
        has_selection = facts.selected_triangles > 0
        self.fit_button.setEnabled(has_selection and not facts.busy)
        self.create_button.setEnabled(has_selection and not facts.busy)

    def _inputs(self) -> list[QWidget]:
        return [
            self.angle,
            self.connected,
            self.brush,
            self.control_u,
            self.control_v,
            self.smoothness,
            self.expand,
            self.tolerance,
            self.fill_on_scan,
            self.extend_distance,
            self.trim_tolerance,
            self.trim_overlap,
            self.compare_tolerance,
            self.ruled,
            self.sew,
        ]

    # -- pages ---------------------------------------------------------------------------------

    def _build_fit(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_section("1. Select the area"))
        modes = QHBoxLayout()
        self.mode_buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for mode, text in SELECTION_MODES:
            button = QToolButton()
            button.setText(text)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setSizePolicy(button.sizePolicy().horizontalPolicy(), button.sizePolicy().verticalPolicy())
            button.clicked.connect(lambda _checked=False, value=mode: self._emit("model.configure", {"selection_mode": value}))
            group.addButton(button)
            modes.addWidget(button)
            self.mode_buttons[mode] = button
        self.mode_buttons["smart"].setToolTip("Click a smooth area: it grows until the surface turns more than the angle.")
        self.mode_buttons["brush"].setToolTip("Drag over the scan to paint the area (Alt+drag rotates the view).")
        self.mode_buttons["erase"].setToolTip("Drag to remove triangles from the area (Alt+drag rotates the view).")
        layout.addLayout(modes)
        form = QFormLayout()
        self.angle = QDoubleSpinBox()
        self.angle.setRange(0.1, 45.0)
        self.angle.setDecimals(1)
        self.angle.setSuffix(" deg")
        self.angle.setToolTip("Smart select stops where neighbouring triangles turn more than this.")
        self.angle.valueChanged.connect(lambda value: self._emit("model.configure", {"smart_angle": value}))
        form.addRow("Angle", self.angle)
        self.brush = QDoubleSpinBox()
        self.brush.setRange(0.01, 1e5)
        self.brush.setDecimals(2)
        self.brush.valueChanged.connect(lambda value: self._emit("model.configure", {"brush_radius": value}))
        form.addRow("Brush size", self.brush)
        layout.addLayout(form)
        self.connected = QCheckBox("Select the whole connected piece")
        self.connected.toggled.connect(lambda value: self._emit("model.configure", {"connected": bool(value)}))
        layout.addWidget(self.connected)
        row = QHBoxLayout()
        clear = _button("Clear")
        clear.clicked.connect(lambda: self._emit("model.select_clear"))
        invert = _button("Invert")
        invert.clicked.connect(lambda: self._emit("model.select_invert"))
        row.addWidget(clear)
        row.addWidget(invert)
        layout.addLayout(row)
        self.selection_info = _hint()
        layout.addWidget(self.selection_info)

        layout.addWidget(_section("2. Surface type"))
        grid = QGridLayout()
        self.type_buttons: dict[str, QToolButton] = {}
        types = QButtonGroup(self)
        types.setExclusive(True)
        for index, (kind, text) in enumerate(SURFACE_TYPES):
            button = QToolButton()
            button.setText(text)
            button.setCheckable(True)
            button.setMinimumWidth(72)
            button.clicked.connect(lambda _checked=False, value=kind: self._emit("model.configure", {"fit_kind": value}))
            types.addButton(button)
            grid.addWidget(button, index // 3, index % 3)
            self.type_buttons[kind] = button
        self.type_buttons["auto"].setToolTip("The simplest exact shape that fits within the tolerance, else freeform.")
        layout.addLayout(grid)

        layout.addWidget(_section("3. Options"))
        form = QFormLayout()
        net = QHBoxLayout()
        self.control_u = QSpinBox()
        self.control_v = QSpinBox()
        for spin, key in ((self.control_u, "fit_control_u"), (self.control_v, "fit_control_v")):
            spin.setRange(0, 48)
            spin.setSpecialValueText("Auto")
            spin.setToolTip("Control points across the patch: more follows finer detail (and noise).")
            spin.valueChanged.connect(lambda value, name=key: self._emit("model.configure", {name: value}))
            net.addWidget(spin)
        net_widget = QWidget()
        net_widget.setLayout(net)
        net.setContentsMargins(0, 0, 0, 0)
        form.addRow("U x V", net_widget)
        self.smoothness = QSlider(Qt.Orientation.Horizontal)
        self.smoothness.setRange(0, 100)
        self.smoothness.setToolTip("Smoother surfaces ignore more noise but follow small detail less.")
        self.smoothness.valueChanged.connect(lambda value: self._emit("model.configure", {"fit_smoothness": value / 100.0}))
        form.addRow("Smoothness", self.smoothness)
        self.expand = QDoubleSpinBox()
        self.expand.setRange(0.0, 100.0)
        self.expand.setDecimals(0)
        self.expand.setSuffix(" %")
        self.expand.setToolTip("Make the surface larger than the selection, to trim it against its neighbours.")
        self.expand.valueChanged.connect(lambda value: self._emit("model.configure", {"fit_expand": value / 100.0}))
        form.addRow("Expand by", self.expand)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0.001, 10.0)
        self.tolerance.setDecimals(3)
        self.tolerance.setSingleStep(0.01)
        self.tolerance.setToolTip("Auto type and auto net aim for this deviation; Compare colours it green.")
        self.tolerance.valueChanged.connect(lambda value: self._emit("model.configure", {"fit_tolerance": value}))
        form.addRow("Tolerance", self.tolerance)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.fit_button = _button("Fit")
        self.fit_button.setToolTip("Preview the fitted surface and its deviation.")
        self.fit_button.clicked.connect(lambda: self._emit("model.fit_preview"))
        self.create_button = _button("Create", primary=True)
        self.create_button.setToolTip("Keep the surface (fits first if needed).")
        self.create_button.clicked.connect(lambda: self._emit("model.fit_create"))
        row.addWidget(self.fit_button)
        row.addWidget(self.create_button)
        layout.addLayout(row)
        self.fit_result = _hint()
        layout.addWidget(self.fit_result)

    def _build_loft(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_hint("Select two or more curves (Ctrl+click in the tree or the scene), in order. Draw curves on the scan with Draw Curve."))
        self.loft_info = _hint()
        layout.addWidget(self.loft_info)
        self.ruled = QCheckBox("Ruled (straight between curves)")
        layout.addWidget(self.ruled)
        self.loft_button = _button("Loft", primary=True)
        self.loft_button.clicked.connect(lambda: self._emit("model.loft_apply", {"ruled": self.ruled.isChecked()}))
        layout.addWidget(self.loft_button)

    def _build_fill(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_hint("Click the surface edges and curves around the gap, in order around it. Edges join smoothly (tangent), curves by contact."))
        self.fill_list = QListWidget()
        self.fill_list.setMaximumHeight(140)
        layout.addWidget(self.fill_list)
        row = QHBoxLayout()
        for text, continuity in (("Contact", "contact"), ("Smooth", "smooth")):
            button = _button(text)
            button.setToolTip(f"Make the selected side {text.lower()}.")
            button.clicked.connect(lambda _checked=False, value=continuity: self._fill_continuity(value))
            row.addWidget(button)
        clear = _button("Clear")
        clear.clicked.connect(lambda: self._emit("model.fill_clear"))
        row.addWidget(clear)
        layout.addLayout(row)
        self.fill_on_scan = QCheckBox("Follow the scan inside the boundary")
        self.fill_on_scan.toggled.connect(lambda value: self._emit("model.configure", {"fill_on_scan": bool(value)}))
        layout.addWidget(self.fill_on_scan)
        self.fill_button = _button("Fill", primary=True)
        self.fill_button.clicked.connect(lambda: self._emit("model.fill_apply"))
        layout.addWidget(self.fill_button)

    def _fill_continuity(self, continuity: str) -> None:
        row = self.fill_list.currentRow()
        if row >= 0:
            self._emit("model.fill_continuity", {"index": row, "continuity": continuity})

    def _build_extend(self, layout: QVBoxLayout) -> None:
        self.extend_info = _hint()
        layout.addWidget(self.extend_info)
        form = QFormLayout()
        self.extend_distance = QDoubleSpinBox()
        self.extend_distance.setRange(0.01, 1e5)
        self.extend_distance.setDecimals(2)
        self.extend_distance.valueChanged.connect(lambda value: self._emit("model.configure", {"extend_distance": value}))
        form.addRow("Distance", self.extend_distance)
        layout.addLayout(form)
        self.extend_button = _button("Extend", primary=True)
        self.extend_button.clicked.connect(lambda: self._emit("model.extend_apply"))
        layout.addWidget(self.extend_button)

    def _build_trim(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_hint("Splits all visible surfaces by each other and keeps the pieces lying on the scan. Click a piece to keep or drop it."))
        form = QFormLayout()
        self.trim_tolerance = QDoubleSpinBox()
        self.trim_tolerance.setRange(0.001, 50.0)
        self.trim_tolerance.setDecimals(3)
        self.trim_tolerance.setSingleStep(0.05)
        self.trim_tolerance.setToolTip("A piece point counts as on the scan within this distance.")
        self.trim_tolerance.valueChanged.connect(lambda value: self._emit("model.configure", {"trim_tolerance": value}))
        form.addRow("Tolerance", self.trim_tolerance)
        overlap_row = QHBoxLayout()
        self.trim_overlap = QSlider(Qt.Orientation.Horizontal)
        self.trim_overlap.setRange(5, 95)
        self.trim_overlap.setToolTip("Share of a piece that must lie on the scan for it to be kept.")
        self.trim_overlap.valueChanged.connect(lambda value: self._emit("model.configure", {"trim_overlap": value / 100.0}))
        self.trim_overlap_label = QLabel()
        overlap_row.addWidget(self.trim_overlap, 1)
        overlap_row.addWidget(self.trim_overlap_label)
        overlap = QWidget()
        overlap.setLayout(overlap_row)
        overlap_row.setContentsMargins(0, 0, 0, 0)
        form.addRow("On the scan", overlap)
        layout.addLayout(form)
        self.trim_compute = _button("Automatic Trim")
        self.trim_compute.clicked.connect(lambda: self._emit("model.trim_compute"))
        layout.addWidget(self.trim_compute)
        self.trim_info = _hint()
        layout.addWidget(self.trim_info)
        self.sew = QCheckBox("Sew into one body (a solid when it closes)")
        self.sew.setChecked(True)
        layout.addWidget(self.sew)
        self.trim_apply = _button("Apply", primary=True)
        self.trim_apply.clicked.connect(lambda: self._emit("model.trim_apply", {"sew": self.sew.isChecked()}))
        layout.addWidget(self.trim_apply)

    def _build_compare(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_hint("Colours the scan by its distance to the visible model surfaces."))
        form = QFormLayout()
        self.compare_tolerance = QDoubleSpinBox()
        self.compare_tolerance.setRange(0.001, 10.0)
        self.compare_tolerance.setDecimals(3)
        self.compare_tolerance.setSingleStep(0.01)
        self.compare_tolerance.valueChanged.connect(lambda value: self._emit("model.configure", {"fit_tolerance": value}))
        form.addRow("Tolerance", self.compare_tolerance)
        layout.addLayout(form)
        row = QHBoxLayout()
        compute = _button("Compute", primary=True)
        compute.clicked.connect(lambda: self._emit("model.compare_apply"))
        self.compare_clear = _button("Clear map")
        self.compare_clear.clicked.connect(lambda: self._emit("model.compare_clear"))
        row.addWidget(compute)
        row.addWidget(self.compare_clear)
        layout.addLayout(row)
        self.legend = QFrame()
        legend_layout = QVBoxLayout(self.legend)
        legend_layout.setContentsMargins(0, 4, 0, 0)
        bar = QLabel()
        bar.setFixedHeight(14)
        bar.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #334ceb, stop:0.33 #4dcbf2, "
            "stop:0.40 #4dc766, stop:0.60 #4dc766, stop:0.67 #f5e040, stop:1 #ed4033); border-radius: 3px;"
        )
        legend_layout.addWidget(bar)
        labels = QHBoxLayout()
        self.legend_low = QLabel()
        middle = QLabel("in tolerance")
        middle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.legend_high = QLabel()
        self.legend_high.setAlignment(Qt.AlignmentFlag.AlignRight)
        labels.addWidget(self.legend_low)
        labels.addWidget(middle, 1)
        labels.addWidget(self.legend_high)
        legend_layout.addLayout(labels)
        layout.addWidget(self.legend)
        self.compare_info = _hint()
        layout.addWidget(self.compare_info)

    def _emit(self, action: str, payload: dict[str, Any] | None = None) -> None:
        self.action_requested.emit(action, dict(payload or {}))


__all__ = ("PAGES", "PanelFacts", "SurfacingPanel")

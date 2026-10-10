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
PAGES = ("sketch", "plane_sketch", "section", "extrude", "fit_surface", "loft", "fill", "extend", "trim", "compare")
EXTRUDE_MODES = (("new", "New body"), ("add", "Add"), ("cut", "Cut"))
SECTION_PLANES = (("XY", "XY (top)"), ("XZ", "XZ (front)"), ("YZ", "YZ (side)"))
SKETCH2D_TOOLS = (
    ("select", "Select", "Pick points and curves to constrain; drag a point to move it (S)."),
    ("line", "Line", "Click points; click the first one to close the shape; Enter ends (L)."),
    ("rectangle", "Rectangle", "Click two opposite corners (R)."),
    ("circle", "Circle", "Click the centre, then a point on the circle (C)."),
    ("arc", "Arc", "Click the centre, the start, then the end, counter-clockwise (A)."),
)
SKETCH2D_CONSTRAINTS = (
    ("coincident", "Coincident", "A point on another point, a line or a circle."),
    ("horizontal", "Horizontal", "A line, or two points, level."),
    ("vertical", "Vertical", "A line, or two points, upright."),
    ("parallel", "Parallel", "Two lines parallel."),
    ("perpendicular", "Perpendicular", "Two lines at right angles."),
    ("tangent", "Tangent", "A line and a circle or arc, or two of them, touching smoothly."),
    ("equal", "Equal", "Two lines the same length, or two circles / arcs the same radius."),
    ("concentric", "Concentric", "Two circles or arcs on one centre."),
    ("midpoint", "Midpoint", "A point at a line's middle."),
    ("symmetric", "Symmetric", "Two points mirrored about a line."),
    ("collinear", "Collinear", "Two lines on one line."),
    ("fix", "Fix", "A point held where it is."),
)


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
    editing_done = Signal()  # Enter in a number field: give the keyboard back to the 3D view

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
            ("sketch", self._build_sketch),
            ("plane_sketch", self._build_plane_sketch),
            ("section", self._build_section),
            ("extrude", self._build_extrude),
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
        self._keep_hotkeys_working()

    def _keep_hotkeys_working(self) -> None:
        """Buttons, boxes and sliders never take the keyboard, so Ctrl+Z, Delete, H, M ...
        still reach the window after clicking them; number fields hand it back on Enter."""

        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QPushButton, QToolButton, QCheckBox, QSlider, QListWidget)):
                widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            elif isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.lineEdit().returnPressed.connect(self.editing_done.emit)

    # -- painting ------------------------------------------------------------------------------

    def show_session(self, session: Any, facts: PanelFacts) -> None:
        if session is None:
            return
        self.title.setText(facts.title)
        self.pages.setCurrentIndex(self._page_index.get(session.tool, 0))
        blockers = [QSignalBlocker(widget) for widget in self._inputs()]
        try:
            self._show_fit(session, facts)
            self._show_sketch(facts.extra, facts.busy)
            self._show_plane_sketch(session, facts)
            self._show_section(session, facts)
            self._show_extrude(session, facts)
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
            for manual, mode_button in self.trim_mode_buttons.items():
                mode_button.setChecked(bool(session.trim_manual) == manual)
            drawing = bool(session.trim_drawing)
            self.trim_cut.setText("Enter to Cut" if drawing else "Cut Line")
            self.trim_cut.setEnabled(not drawing and not facts.busy)
            self.trim_cut_clear.setEnabled(bool(session.trim_cuts) and not facts.busy)
            self.trim_tolerance.setEnabled(not session.trim_manual)
            self.trim_overlap.setEnabled(not session.trim_manual)
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

    def _show_sketch(self, extra: dict[str, Any], busy: bool) -> None:
        if not extra:
            return
        drawing = int(extra.get("drawing", 0))
        selected = int(extra.get("selected_curves", 0))
        lines = []
        if drawing:
            lines.append(f"Drawing: {drawing} point(s). Enter finishes, C closes, Backspace removes the last point.")
        lines.append(f"{extra.get('curves', 0)} curve(s) in the sketch.")
        if selected:
            lines.append(f"Selected: {extra.get('selected_names', '')}")
        self.sketch_info.setText("\n".join(lines))
        self.sketch_finish.setEnabled(drawing >= 2)
        self.sketch_close.setEnabled(drawing >= 3)
        self.sketch_undo.setEnabled(drawing >= 1)
        self.sketch_delete.setEnabled(selected > 0 and not busy)
        self.sketch_loft.setEnabled(selected >= 2 and not busy)
        self.sketch_face.setEnabled(bool(extra.get("loop")) and not busy)
        self.sketch_fit.setChecked(bool(extra.get("fit_to_scan", True)))
        point = bool(extra.get("selected_node"))
        self.sketch_delete_point.setEnabled(point and not busy)
        self.sketch_split.setEnabled(point and not busy)
        editable = (selected > 0 or point) and not busy
        self.sketch_toggle_closed.setEnabled(editable)
        self.sketch_reverse.setEnabled(editable)
        self.sketch_feature.setChecked(bool(extra.get("feature", False)))
        if not self.sketch_smoothness.isSliderDown():
            self.sketch_smoothness.setValue(int(round(100 * float(extra.get("smoothness", 0.6)))))
        self.sketch_creases.setChecked(bool(extra.get("show_creases", False)))
        self.sketch_options_hint.setText(
            "These apply to the selected curve(s) and to new ones." if selected else "These apply to the curves you draw next."
        )

    def _show_section(self, session: Any, facts: PanelFacts) -> None:
        if session.tool != "section":
            return
        extra = facts.extra
        for plane, button in self.plane_buttons.items():
            button.setChecked(session.section_plane == plane)
        self.section_offset.setSuffix(f" {facts.units}")
        self.section_offset.setValue(float(session.section_offset))
        self.section_tolerance.setSuffix(f" {facts.units}")
        self.section_tolerance.setValue(float(session.section_tolerance))
        self.section_sharp.setSuffix(f" {facts.units}")
        self.section_sharp.setValue(float(session.section_sharp))
        self.section_info.setText(str(extra.get("section_text", "")))
        loops = int(extra.get("loops", 0))
        self.section_fit.setEnabled(loops > 0 and not facts.busy)
        self.section_create.setEnabled(loops > 0 and not facts.busy)
        picked = extra.get("picked") or {}
        self.section_selection.setText(
            str(picked.get("text") or "Click a corner (drag to move it) or a segment of the violet profile.")
        )
        if picked.get("radius"):
            self.section_radius.setValue(float(picked["radius"]))
        allowed = set(picked.get("allowed", ()))
        if extra.get("open_profile"):
            allowed.add("close")
        for operation, edit_button in self.section_edit_buttons.items():
            edit_button.setEnabled(operation in allowed and not facts.busy)

    def _show_extrude(self, session: Any, facts: PanelFacts) -> None:
        if session.tool != "extrude":
            return
        extra = facts.extra
        for mode, button in self.extrude_mode_buttons.items():
            button.setChecked(session.extrude_mode == mode)
            button.setEnabled(mode == "new" or bool(extra.get("has_target")))
        for box in (self.extrude_front, self.extrude_back):
            box.setSuffix(f" {facts.units}")
        self.extrude_front.setValue(float(session.extrude_front))
        self.extrude_back.setValue(float(session.extrude_back))
        self.extrude_draft.setValue(float(session.extrude_draft))
        self.extrude_auto.setChecked(bool(session.extrude_auto))
        self.extrude_info.setText(str(extra.get("extrude_text", "")))
        self.extrude_create.setEnabled(not facts.busy)
        self.extrude_measure.setEnabled(not facts.busy)

    def _show_plane_sketch(self, session: Any, facts: PanelFacts) -> None:
        if session.tool != "plane_sketch":
            return
        extra = facts.extra
        for plane, button in self.sketch2d_plane_buttons.items():
            button.setChecked(extra.get("plane") == plane)
        self.sketch2d_offset.setSuffix(f" {facts.units}")
        self.sketch2d_offset.setValue(float(extra.get("offset", 0.0)))
        for tool, button in self.sketch2d_tool_buttons.items():
            button.setChecked(extra.get("tool") == tool)
        available = set(extra.get("available", ()))
        for kind, constraint_button in self.sketch2d_constraint_buttons.items():
            constraint_button.setEnabled(kind in available and not facts.busy)
        self.sketch2d_dimension.setEnabled("dimension" in available and not facts.busy)
        two_points = bool(extra.get("two_points"))
        self.sketch2d_horizontal_dimension.setEnabled(two_points and not facts.busy)
        self.sketch2d_vertical_dimension.setEnabled(two_points and not facts.busy)
        selected = int(extra.get("selected", 0))
        self.sketch2d_delete.setEnabled(selected > 0 and not facts.busy)
        self.sketch2d_construction.setEnabled(selected > 0 and not facts.busy)
        rows = list(extra.get("constraints", ()))
        current = self._sketch2d_constraint_id()
        self.sketch2d_constraints.clear()
        self._sketch2d_rows = rows
        for row_id, text, _value, _dimension in rows:
            self.sketch2d_constraints.addItem(text)
            if row_id == current:
                self.sketch2d_constraints.setCurrentRow(self.sketch2d_constraints.count() - 1)
        self._sketch2d_show_value()
        editing = str(extra.get("editing", ""))
        self.sketch2d_status.setText((f"Editing {editing}. " if editing else "") + str(extra.get("dof_text", "")))
        self.sketch2d_finish.setEnabled(not facts.busy)

    def _sketch2d_constraint_id(self) -> str | None:
        row = self.sketch2d_constraints.currentRow()
        rows = getattr(self, "_sketch2d_rows", [])
        return rows[row][0] if 0 <= row < len(rows) else None

    def _sketch2d_show_value(self) -> None:
        row = self.sketch2d_constraints.currentRow()
        rows = getattr(self, "_sketch2d_rows", [])
        dimension = 0 <= row < len(rows) and rows[row][3]
        blocker = QSignalBlocker(self.sketch2d_value)
        if dimension:
            self.sketch2d_value.setValue(float(rows[row][2]))
        del blocker
        self.sketch2d_value.setEnabled(bool(dimension))
        self.sketch2d_remove.setEnabled(0 <= row < len(rows))

    def _sketch2d_apply_value(self) -> None:
        constraint = self._sketch2d_constraint_id()
        if constraint is not None and self.sketch2d_value.isEnabled():
            self._emit("model.sketch2d_set_dimension", {"constraint": constraint, "value": self.sketch2d_value.value()})

    def _sketch2d_remove(self) -> None:
        constraint = self._sketch2d_constraint_id()
        if constraint is not None:
            self._emit("model.sketch2d_delete_constraint", {"constraint": constraint})

    def _inputs(self) -> list[QWidget]:
        return [
            self.sketch2d_offset,
            self.sketch2d_value,
            self.section_radius,
            self.sketch_feature,
            self.sketch_smoothness,
            self.sketch_creases,
            self.extrude_front,
            self.extrude_back,
            self.extrude_draft,
            self.extrude_auto,
            self.section_offset,
            self.section_tolerance,
            self.section_sharp,
            self.sketch_fit,
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

    def _build_sketch(self, layout: QVBoxLayout) -> None:
        layout.addWidget(
            _hint(
                "Click points on the scan: the curve runs along the surface through them. While drawing, click a "
                "point to connect (that finishes), or the first point to close. Ctrl+click a point to start a "
                "curve from it. Click a point to select it, drag to move it; double-click a curve to add a point; "
                "right-click for more."
            )
        )
        form = QFormLayout()
        self.sketch_feature = QCheckBox("Follow body lines (creases)")
        self.sketch_feature.setToolTip(
            "Between its points the curve rides along the scan's creases: two clicks at the ends of a body line trace it."
        )
        self.sketch_feature.toggled.connect(lambda value: self._emit("model.sketch_options", {"feature": bool(value)}))
        form.addRow(self.sketch_feature)
        smooth_row = QHBoxLayout()
        self.sketch_smoothness = QSlider(Qt.Orientation.Horizontal)
        self.sketch_smoothness.setRange(0, 100)
        self.sketch_smoothness.setToolTip("Low: hugs the scan's surface detail. High: a fair, even curve.")
        self.sketch_smoothness.sliderReleased.connect(
            lambda: self._emit("model.sketch_options", {"smoothness": self.sketch_smoothness.value() / 100.0})
        )
        self.sketch_smoothness_label = QLabel()
        self.sketch_smoothness.valueChanged.connect(lambda value: self.sketch_smoothness_label.setText(f"{value}%"))
        smooth_row.addWidget(self.sketch_smoothness, 1)
        smooth_row.addWidget(self.sketch_smoothness_label)
        smooth = QWidget()
        smooth.setLayout(smooth_row)
        smooth_row.setContentsMargins(0, 0, 0, 0)
        form.addRow("Smoothness", smooth)
        self.sketch_creases = QCheckBox("Show body lines on the scan")
        self.sketch_creases.setToolTip("Colour the scan red along its creases, to see the lines to trace.")
        self.sketch_creases.toggled.connect(lambda value: self._emit("model.configure", {"show_creases": bool(value)}))
        form.addRow(self.sketch_creases)
        layout.addLayout(form)
        self.sketch_options_hint = _hint()
        layout.addWidget(self.sketch_options_hint)
        row = QHBoxLayout()
        self.sketch_finish = _button("Finish")
        self.sketch_finish.setToolTip("Finish the curve being drawn as an open curve (Enter).")
        self.sketch_finish.clicked.connect(lambda: self._emit("model.sketch_finish"))
        self.sketch_close = _button("Close")
        self.sketch_close.setToolTip("Close the curve being drawn into a loop (C).")
        self.sketch_close.clicked.connect(lambda: self._emit("model.sketch_close"))
        self.sketch_undo = _button("Undo Point")
        self.sketch_undo.setToolTip("Remove the last point placed (Backspace).")
        self.sketch_undo.clicked.connect(lambda: self._emit("model.sketch_undo_point"))
        for button in (self.sketch_finish, self.sketch_close, self.sketch_undo):
            row.addWidget(button)
        layout.addLayout(row)
        self.sketch_info = _hint()
        layout.addWidget(self.sketch_info)
        layout.addWidget(_section("Edit"))
        row = QHBoxLayout()
        self.sketch_delete_point = _button("Delete Point")
        self.sketch_delete_point.setToolTip("Remove the selected point; its curves pass the neighbours instead (Delete).")
        self.sketch_delete_point.clicked.connect(lambda: self._emit("model.sketch_delete_point"))
        self.sketch_split = _button("Split Here")
        self.sketch_split.setToolTip("Cut the curve at the selected point (a closed curve opens there).")
        self.sketch_split.clicked.connect(lambda: self._emit("model.sketch_split"))
        row.addWidget(self.sketch_delete_point)
        row.addWidget(self.sketch_split)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.sketch_toggle_closed = _button("Open / Close")
        self.sketch_toggle_closed.setToolTip("Close the selected curve into a loop, or open a closed one.")
        self.sketch_toggle_closed.clicked.connect(lambda: self._emit("model.sketch_toggle_closed"))
        self.sketch_reverse = _button("Reverse")
        self.sketch_reverse.setToolTip("Run the selected curve the other way (matters for lofts).")
        self.sketch_reverse.clicked.connect(lambda: self._emit("model.sketch_reverse"))
        row.addWidget(self.sketch_toggle_closed)
        row.addWidget(self.sketch_reverse)
        layout.addLayout(row)
        layout.addWidget(_section("Make surfaces"))
        layout.addWidget(_hint("Select curves (click them; Ctrl+click adds), then:"))
        self.sketch_face = _button("Face From Curves", primary=True)
        self.sketch_face.setToolTip("A face inside the selected closed curve, or curves whose ends meet in a loop.")
        self.sketch_face.clicked.connect(lambda: self._emit("model.sketch_face"))
        layout.addWidget(self.sketch_face)
        self.sketch_fit = QCheckBox("Fit the face to the scan inside the curves")
        self.sketch_fit.setToolTip("Off: a smooth fill of the boundary that ignores the scan inside it.")
        self.sketch_fit.toggled.connect(lambda value: self._emit("model.configure", {"face_fit_to_scan": bool(value)}))
        layout.addWidget(self.sketch_fit)
        row = QHBoxLayout()
        self.sketch_loft = _button("Loft")
        self.sketch_loft.setToolTip("A surface through the selected curves (two or more, in order).")
        self.sketch_loft.clicked.connect(lambda: self._emit("model.sketch_loft"))
        self.sketch_delete = _button("Delete Curves")
        self.sketch_delete.clicked.connect(lambda: self._emit("model.sketch_delete"))
        row.addWidget(self.sketch_loft)
        row.addWidget(self.sketch_delete)
        layout.addLayout(row)

    def _build_plane_sketch(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_section("Plane"))
        row = QHBoxLayout()
        self.sketch2d_plane_buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        for plane, _label in SECTION_PLANES:
            button = QToolButton()
            button.setText(plane)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setToolTip("Sketch on this plane (before drawing); the scan's cut there is shown grey.")
            button.clicked.connect(lambda _checked=False, plane=plane: self._emit("model.sketch2d_plane", {"plane": plane}))
            group.addButton(button)
            row.addWidget(button)
            self.sketch2d_plane_buttons[plane] = button
        layout.addLayout(row)
        form = QFormLayout()
        self.sketch2d_offset = QDoubleSpinBox()
        self.sketch2d_offset.setRange(-1e6, 1e6)
        self.sketch2d_offset.setDecimals(3)
        self.sketch2d_offset.setSingleStep(0.5)
        self.sketch2d_offset.setToolTip("Where the plane lies along its axis (the grey scan cut follows).")
        self.sketch2d_offset.valueChanged.connect(lambda value: self._emit("model.sketch2d_plane", {"offset": value}))
        form.addRow("Offset", self.sketch2d_offset)
        layout.addLayout(form)
        layout.addWidget(_section("Draw"))
        tools = QGridLayout()
        self.sketch2d_tool_buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        for position, (tool, label, tip) in enumerate(SKETCH2D_TOOLS):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, tool=tool: self._emit("model.sketch2d_tool", {"tool": tool}))
            group.addButton(button)
            tools.addWidget(button, position // 3, position % 3)
            self.sketch2d_tool_buttons[tool] = button
        layout.addLayout(tools)
        row = QHBoxLayout()
        self.sketch2d_construction = _button("Construction")
        self.sketch2d_construction.setToolTip("Selected curves become guides (not part of profiles), or back.")
        self.sketch2d_construction.clicked.connect(lambda: self._emit("model.sketch2d_construction"))
        self.sketch2d_delete = _button("Delete")
        self.sketch2d_delete.setToolTip("Delete the selected points and curves (Delete).")
        self.sketch2d_delete.clicked.connect(lambda: self._emit("model.sketch2d_delete"))
        row.addWidget(self.sketch2d_construction)
        row.addWidget(self.sketch2d_delete)
        layout.addLayout(row)
        layout.addWidget(_section("Constrain the selection"))
        grid = QGridLayout()
        self.sketch2d_constraint_buttons: dict[str, QPushButton] = {}
        for position, (kind, label, tip) in enumerate(SKETCH2D_CONSTRAINTS):
            constraint_button = _button(label)
            constraint_button.setToolTip(tip)
            constraint_button.clicked.connect(lambda _checked=False, kind=kind: self._emit("model.sketch2d_constrain", {"kind": kind}))
            grid.addWidget(constraint_button, position // 2, position % 2)
            self.sketch2d_constraint_buttons[kind] = constraint_button
        layout.addLayout(grid)
        self.sketch2d_dimension = _button("Dimension")
        self.sketch2d_dimension.setToolTip(
            "Dimension the selection at its current size (D): a line's length, two points, a point and a line, "
            "two lines' angle, a circle's diameter, an arc's radius. Change the value below."
        )
        self.sketch2d_dimension.clicked.connect(lambda: self._emit("model.sketch2d_dimension"))
        self.sketch2d_horizontal_dimension = _button("Horizontal Dim.")
        self.sketch2d_horizontal_dimension.setToolTip("The horizontal distance between the two selected points.")
        self.sketch2d_horizontal_dimension.clicked.connect(lambda: self._emit("model.sketch2d_dimension", {"kind": "horizontal_distance"}))
        self.sketch2d_vertical_dimension = _button("Vertical Dim.")
        self.sketch2d_vertical_dimension.setToolTip("The vertical distance between the two selected points.")
        self.sketch2d_vertical_dimension.clicked.connect(lambda: self._emit("model.sketch2d_dimension", {"kind": "vertical_distance"}))
        layout.addWidget(self.sketch2d_dimension)
        row = QHBoxLayout()
        row.addWidget(self.sketch2d_horizontal_dimension)
        row.addWidget(self.sketch2d_vertical_dimension)
        layout.addLayout(row)
        layout.addWidget(_section("Constraints and dimensions"))
        self.sketch2d_constraints = QListWidget()
        self.sketch2d_constraints.setMinimumHeight(110)
        self.sketch2d_constraints.currentRowChanged.connect(lambda _row: self._sketch2d_show_value())
        layout.addWidget(self.sketch2d_constraints)
        row = QHBoxLayout()
        self.sketch2d_value = QDoubleSpinBox()
        self.sketch2d_value.setRange(-1e6, 1e6)
        self.sketch2d_value.setDecimals(3)
        self.sketch2d_value.setSingleStep(0.5)
        self.sketch2d_value.setToolTip("The picked dimension's value: Enter changes it, and the sketch follows.")
        self.sketch2d_value.lineEdit().returnPressed.connect(self._sketch2d_apply_value)
        self.sketch2d_remove = _button("Remove")
        self.sketch2d_remove.setToolTip("Remove the picked constraint or dimension.")
        self.sketch2d_remove.clicked.connect(self._sketch2d_remove)
        row.addWidget(self.sketch2d_value, 1)
        row.addWidget(self.sketch2d_remove)
        layout.addLayout(row)
        self.sketch2d_status = _hint()
        layout.addWidget(self.sketch2d_status)
        self.sketch2d_finish = _button("Finish Sketch", primary=True)
        self.sketch2d_finish.setToolTip("Keep the sketch (Enter): its closed regions are profiles to extrude.")
        self.sketch2d_finish.clicked.connect(lambda: self._emit("model.sketch2d_finish"))
        layout.addWidget(self.sketch2d_finish)

    def _build_section(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_section("Sketch plane"))
        row = QHBoxLayout()
        self.plane_buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        for plane, label in SECTION_PLANES:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.clicked.connect(lambda _checked=False, plane=plane: self._emit("model.section_plane", {"plane": plane}))
            group.addButton(button)
            row.addWidget(button)
            self.plane_buttons[plane] = button
        layout.addLayout(row)
        form = QFormLayout()
        self.section_offset = QDoubleSpinBox()
        self.section_offset.setRange(-1e6, 1e6)
        self.section_offset.setDecimals(3)
        self.section_offset.setSingleStep(0.5)
        self.section_offset.setToolTip("Where the plane cuts, along its normal. Clicking the scan moves it there.")
        self.section_offset.valueChanged.connect(lambda value: self._emit("model.section_plane", {"offset": value}))
        form.addRow("Offset", self.section_offset)
        layout.addLayout(form)
        layout.addWidget(_hint("Click the scan to move the plane through that point (Ctrl+click once a profile is fitted, so edits are not lost)."))
        layout.addWidget(_section("Fit"))
        form = QFormLayout()
        self.section_tolerance = QDoubleSpinBox()
        self.section_tolerance.setRange(0.0, 10.0)
        self.section_tolerance.setDecimals(3)
        self.section_tolerance.setSingleStep(0.01)
        self.section_tolerance.setSpecialValueText("Auto")
        self.section_tolerance.setToolTip(
            "Each line and arc stays this close to the section. Auto: about four times the scan noise, measured on the section."
        )
        self.section_tolerance.valueChanged.connect(lambda value: self._emit("model.configure", {"section_tolerance": value}))
        form.addRow("Tolerance", self.section_tolerance)
        self.section_sharp = QDoubleSpinBox()
        self.section_sharp.setRange(0.0, 100.0)
        self.section_sharp.setDecimals(2)
        self.section_sharp.setSingleStep(0.1)
        self.section_sharp.setSpecialValueText("Auto")
        self.section_sharp.setToolTip(
            "A rounded corner smaller than this is a sharp edge the scanner rounded: the lines meet exactly. "
            "Auto: about the scan's point spacing."
        )
        self.section_sharp.valueChanged.connect(lambda value: self._emit("model.configure", {"section_sharp": value}))
        form.addRow("Sharp below R", self.section_sharp)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.section_fit = _button("Fit Profile")
        self.section_fit.setToolTip("Fit lines and arcs to the section (shown violet over the orange section).")
        self.section_fit.clicked.connect(lambda: self._emit("model.section_fit"))
        self.section_create = _button("Create", primary=True)
        self.section_create.setToolTip("Keep the profile as a sketch: exact lines and arcs, closed loops as faces (Enter).")
        self.section_create.clicked.connect(lambda: self._emit("model.section_create"))
        row.addWidget(self.section_fit)
        row.addWidget(self.section_create)
        layout.addLayout(row)
        self.section_info = _hint()
        layout.addWidget(self.section_info)
        layout.addWidget(_section("Edit the profile"))
        self.section_selection = _hint("Click a corner (drag to move it) or a segment of the violet profile.")
        layout.addWidget(self.section_selection)
        form = QFormLayout()
        self.section_radius = QDoubleSpinBox()
        self.section_radius.setRange(0.001, 1e5)
        self.section_radius.setDecimals(3)
        self.section_radius.setSingleStep(0.5)
        self.section_radius.setToolTip("The picked arc's radius (Enter applies), or the radius a picked corner is rounded with.")
        self.section_radius.lineEdit().returnPressed.connect(self._apply_section_radius)
        form.addRow("Radius", self.section_radius)
        layout.addLayout(form)
        grid = QGridLayout()
        self.section_edit_buttons: dict[str, QPushButton] = {}
        for position, (operation, text, tip) in enumerate(
            (
                ("radius", "Set Radius", "Give the picked arc the radius above (a fillet stays tangent to its lines)."),
                ("fillet", "Round Corner", "Round the picked sharp corner with the radius above."),
                ("sharp", "Sharp Corner", "Take out the picked arc: the lines either side meet."),
                ("axis", "Horizontal / Vertical", "Make the picked line exactly horizontal or vertical."),
                ("delete", "Delete Segment", "Take out the picked segment: its neighbours run on until they meet."),
                ("close", "Close Profile", "Close an open profile (a section broken by a wide hole in the scan)."),
            )
        ):
            edit_button = _button(text)
            edit_button.setToolTip(tip)
            edit_button.clicked.connect(lambda _checked=False, operation=operation: self._section_edit(operation))
            grid.addWidget(edit_button, position // 2, position % 2)
            self.section_edit_buttons[operation] = edit_button
        layout.addLayout(grid)

    def _section_edit(self, operation: str) -> None:
        payload: dict[str, Any] = {"operation": operation}
        if operation in ("radius", "fillet"):
            payload["value"] = self.section_radius.value()
        self._emit("model.section_profile_edit", payload)

    def _apply_section_radius(self) -> None:
        if self.section_edit_buttons["radius"].isEnabled():
            self._section_edit("radius")
        elif self.section_edit_buttons["fillet"].isEnabled():
            self._section_edit("fillet")

    def _build_extrude(self, layout: QVBoxLayout) -> None:
        self.extrude_info = _hint()
        layout.addWidget(self.extrude_info)
        row = QHBoxLayout()
        self.extrude_mode_buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        for mode, label in EXTRUDE_MODES:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.clicked.connect(lambda _checked=False, mode=mode: self._emit("model.configure", {"extrude_mode": mode}))
            group.addButton(button)
            row.addWidget(button)
            self.extrude_mode_buttons[mode] = button
        layout.addLayout(row)
        form = QFormLayout()
        self.extrude_front = QDoubleSpinBox()
        self.extrude_back = QDoubleSpinBox()
        for box, key, tip in (
            (self.extrude_front, "extrude_front", "How far the extrusion runs ahead of the sketch plane (along its normal)."),
            (self.extrude_back, "extrude_back", "How far it runs behind the sketch plane (0: one side only)."),
        ):
            box.setRange(0.0, 1e5)
            box.setDecimals(3)
            box.setSingleStep(0.5)
            box.setToolTip(tip)
            box.valueChanged.connect(lambda value, key=key: self._emit("model.configure", {key: value}))
        form.addRow("Ahead", self.extrude_front)
        form.addRow("Behind", self.extrude_back)
        self.extrude_draft = QDoubleSpinBox()
        self.extrude_draft.setRange(-30.0, 30.0)
        self.extrude_draft.setDecimals(2)
        self.extrude_draft.setSingleStep(0.5)
        self.extrude_draft.setSuffix(" deg")
        self.extrude_draft.setToolTip("Walls taper away from the sketch plane by this angle (holes the other way).")
        self.extrude_draft.valueChanged.connect(lambda value: self._emit("model.configure", {"extrude_draft": value}))
        form.addRow("Draft", self.extrude_draft)
        layout.addLayout(form)
        self.extrude_auto = QCheckBox("Holes keep their own depth from the scan")
        self.extrude_auto.setToolTip("A pocket in the sketch stops where the scan's pocket does, instead of cutting through.")
        self.extrude_auto.toggled.connect(lambda value: self._emit("model.configure", {"extrude_auto": bool(value)}))
        layout.addWidget(self.extrude_auto)
        row = QHBoxLayout()
        self.extrude_measure = _button("Depth From Scan")
        self.extrude_measure.setToolTip("Measure again how far the sketch's walls run in the scan.")
        self.extrude_measure.clicked.connect(lambda: self._emit("model.extrude_measure"))
        self.extrude_create = _button("Create", primary=True)
        self.extrude_create.setToolTip("Keep the extrusion (Enter).")
        self.extrude_create.clicked.connect(lambda: self._emit("model.extrude_apply"))
        row.addWidget(self.extrude_measure)
        row.addWidget(self.extrude_create)
        layout.addLayout(row)

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
        layout.addWidget(
            _hint(
                "Splits the selected surfaces (or all visible ones) by each other and by the cut lines you draw. "
                "Click a piece to keep or drop it (dropped pieces fade), then Apply."
            )
        )
        row = QHBoxLayout()
        self.trim_mode_buttons: dict[bool, QToolButton] = {}
        group = QButtonGroup(self)
        for manual, label, tip in (
            (False, "Automatic", "Keep the pieces lying on the scan."),
            (True, "Manual", "Keep every piece: you click the ones to cut away."),
        ):
            mode_button = QToolButton()
            mode_button.setText(label)
            mode_button.setCheckable(True)
            mode_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            mode_button.setToolTip(tip)
            mode_button.clicked.connect(lambda _checked=False, manual=manual: self._emit("model.configure", {"trim_manual": manual}))
            group.addButton(mode_button)
            row.addWidget(mode_button)
            self.trim_mode_buttons[manual] = mode_button
        layout.addLayout(row)
        row = QHBoxLayout()
        self.trim_cut = _button("Cut Line")
        self.trim_cut.setToolTip("Click points across a surface, Enter cuts it along the line (seen from your view). Works on one surface.")
        self.trim_cut.clicked.connect(lambda: self._emit("model.trim_cut"))
        self.trim_cut_clear = _button("Clear Cuts")
        self.trim_cut_clear.setToolTip("Forget the cut lines drawn so far.")
        self.trim_cut_clear.clicked.connect(lambda: self._emit("model.trim_cut_clear"))
        row.addWidget(self.trim_cut)
        row.addWidget(self.trim_cut_clear)
        layout.addLayout(row)
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
        self.trim_compute = _button("Split Surfaces")
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

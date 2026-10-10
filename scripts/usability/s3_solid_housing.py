"""Audit 3: the Solid workspace as a user - Section Sketch + Extrude from the scan, a 3D Sketch
drawn with the mouse, dimensioned in the panel, extruded by region, History edits."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent))
from human import Human, answer_dialog, log, scan_of, stand_in_file_dialogs  # noqa: E402

h = Human(Path(sys.argv[1]))
w = h.window
stand_in_file_dialogs(open_path=scan_of("housing"))
answer_dialog(choice="mm")
h.click_toolbar("Open Scan")
h.idle()
model = h.composition.state.model
modeling = h.composition.modeling_controller

log("== Solid tab: what is there")
h.tab("Solid")
from PySide6.QtWidgets import QToolBar  # noqa: E402

for bar in w.findChildren(QToolBar):
    if bar.isVisible():
        log(f"  toolbar {bar.windowTitle()!r}: {[(a.text(), bar.widgetForAction(a).isEnabled() if bar.widgetForAction(a) else None) for a in bar.actions() if a.text()]}")

log("== Section Sketch: open, Fit Profile, Create")
h.click_toolbar("Section Sketch")
h.say("section tool")
log(f"  panel info: {w.surfacing_panel.section_info.text()!r}")
h.click_panel("Fit Profile")
h.say("fit")
log(f"  panel info: {w.surfacing_panel.section_info.text()!r}")
h.shot("section_fit")
h.click_panel("Create")
h.say("create")
log(f"  model: {[e.name for e in model.entities]}; tool {modeling.tool}")

log("== Extrude: depth from the scan, Create")
h.click_toolbar("Extrude")
h.say("extrude")
log(f"  panel: {w.surfacing_panel.extrude_info.text()!r}; ahead {w.surfacing_panel.extrude_front.value()} behind {w.surfacing_panel.extrude_back.value()}")
h.click_panel("Create")
h.say("created")
body = next((e for e in model.entities if e.is_body), None)
log(f"  body: {None if body is None else (body.name, round(body.stats.get('volume', 0), 1))} (true 45458)")
h.click_panel("Done")
h.key(Qt.Key_7, "", Qt.ControlModifier)
h.shot("extruded")

log("== History: pick Extrude 1 in the tree, change Ahead in Properties")
history = [n for n in w._scene_nodes() if n.id.startswith("feature:")]
log(f"  history rows: {[n.label for n in history]}")
extrude = next(n for n in history if n.label.startswith("Extrude"))
w.scene_tree.selection_changed.emit((extrude.id,)) if False else w._on_tree_selection(type("S", (), {"ids": (extrude.id,)})())
fields = {f.id: f for f in w._inspector_fields()}
log(f"  properties: {[(f.label, f.value) for f in fields.values()]}")
w._on_inspector_value("feature_front", 20.0)
h.idle()
h.say("edited")
body = next((e for e in model.entities if e.is_body), None)
log(f"  body volume now {round(body.stats.get('volume', 0), 1)}")
h.key(Qt.Key_Z, "z", Qt.ControlModifier)
h.say("undo")

log("== 3D Sketch with the mouse: top view, rectangle, circle")
h.click(5, 5)
h.click_toolbar("3D Sketch")
h.say("3D sketch")
log(f"  hint {h.hint()!r}")
h.key(Qt.Key_5, "", Qt.ControlModifier)
z = modeling.session.sketch2d.offset
h.key(Qt.Key_R, "r")
h.say("R")
for corner in ((-40.0, -30.0), (40.0, 30.0)):
    h.click_world((corner[0], corner[1], z))
    h.say(f"click {corner}")
h.key(Qt.Key_C, "c")
h.click_world((0.0, 0.0, z))
h.click_world((6.0, 0.0, z))
h.say("circle")
log(f"  sketch: {len(modeling.session.sketch2d.sketch.curves)} curves, DOF {modeling.session.sketch2d.sketch.dof()}")
h.key(Qt.Key_S, "s")
h.click_world((0.0, -30.0, z))
h.say("pick bottom edge")
log(f"  selected {modeling.session.sketch2d.selected}")
h.key(Qt.Key_D, "d")
h.say("D")
panel = w.surfacing_panel
log(f"  constraint list: {[panel.sketch2d_constraints.item(i).text() for i in range(panel.sketch2d_constraints.count())]}")
panel.sketch2d_constraints.setCurrentRow(panel.sketch2d_constraints.count() - 1)
from PySide6.QtTest import QTest  # noqa: E402

line_edit = panel.sketch2d_value.lineEdit()
line_edit.selectAll()
QTest.keyClicks(line_edit, "90")
QTest.keyClick(line_edit, Qt.Key_Return)
h.idle()
h.say("typed 90 in the panel")
log(f"  constraint list: {[panel.sketch2d_constraints.item(i).text() for i in range(panel.sketch2d_constraints.count())]}")
h.shot("sketch3d")
h.key(Qt.Key_Return)
h.say("Enter")
log(f"  model: {[e.name for e in model.entities]}; tool {modeling.tool}")

log("== Extrude the 3D Sketch: click inside the circle, Cut from the body")
h.click_toolbar("Extrude")
h.say("extrude tool")
h.click_world((0.0, 0.0, z))
h.say("picked region")
log(f"  regions {modeling.session.extrude_regions if modeling.session else None}; target {modeling.session.extrude_target if modeling.session else None}; mode {modeling.session.extrude_mode if modeling.session else None}")
h.click_panel("Cut")
h.click_panel("Create")
h.say("cut")
log(f"  bodies: {[(e.name, round(e.stats.get('volume', 0), 1)) for e in model.entities if e.is_body]}")
h.click_panel("Done")
h.key(Qt.Key_7, "", Qt.ControlModifier)
h.shot("cut")
log(f"  history: {[n.label for n in w._scene_nodes() if n.id.startswith('feature:')]}")
h.close()
log("done")

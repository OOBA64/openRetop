"""Audit 1: first launch, open a scan through the toolbar, navigate, the Scan workspace tools."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent))
from human import Human, answer_dialog, button_drag, camera, log, scan_of, stand_in_file_dialogs, wheel  # noqa: E402

h = Human(Path(sys.argv[1]))
w = h.window
log("== first launch")
log(f"  title {w.windowTitle()!r}, workspace {w.active_workspace!r}")
log(f"  next steps: {w.next_steps.guidance.title!r}: {[b for b in w.next_steps.step_buttons]}")
h.shot("first_launch")

log("== open a scan with the toolbar (Open Scan), answer the units question")
stand_in_file_dialogs(open_path=scan_of("housing"))
answer_dialog(choice="mm")
h.click_toolbar("Open Scan")
h.idle()
h.say("after open")
log(f"  next steps: {w.next_steps.guidance.title!r}: {list(w.next_steps.step_buttons)}")
log(f"  tree: {[n.label for n in w._scene_nodes()]}")
h.shot("scan_open")

log("== navigate: left drag orbits, right drag?, middle drag pans?, wheel zooms, view cube")
cx, cy = h.view.width() // 2, h.view.height() // 2
before = camera(h)
h.drag((cx, cy), (cx + 120, cy + 40))
log(f"  left drag: camera changed {camera(h) != before}")
before = camera(h)
button_drag(h, Qt.MiddleButton, (cx, cy), (cx + 100, cy))
log(f"  middle drag: camera changed {camera(h) != before} (pan expected)")
before = camera(h)
button_drag(h, Qt.RightButton, (cx, cy), (cx, cy + 100))
log(f"  right drag: camera changed {camera(h) != before}")
before = camera(h)
wheel(h, cx, cy, 3)
log(f"  wheel: camera changed {camera(h) != before}")
before = camera(h)
h.key(Qt.Key_Home)
log(f"  Home: camera changed {camera(h) != before}; status {h.status()!r}")
h.key(Qt.Key_F)
h.say("F")
for key, text in ((Qt.Key_1, "1"), (Qt.Key_7, "7"), (Qt.Key_0, "0")):
    before = camera(h)
    h.key(key, text)
    log(f"  key {text}: camera changed {camera(h) != before}; status {h.status()!r}")
h.shot("navigated")

log("== click the scan: what gets selected, what does the panel show")
h.click(cx, cy)
h.say("click scan")
log(f"  tree selection {w._scene_model.selected_ids}; inspector fields {[f.label for f in w._inspector_fields()][:8]}")
h.click(5, 5)
h.say("click empty")

log("== Scan tab: Move with G, type 10, Enter")
h.tab("Scan")
log(f"  scan toolbar: {[a.text() for a in w.findChildren(type(w.findChild(type(None)))) ] if False else ''}")
h.click(cx, cy)
h.key(Qt.Key_G, "g")
h.say("G")
h.key(Qt.Key_X, "x")
for key, text in ((Qt.Key_1, "1"), (Qt.Key_0, "0")):
    h.key(key, text)
h.say("typed X 10")
h.key(Qt.Key_Return)
h.say("Enter")
mesh = h.composition.state.mesh_object
log(f"  scan location {list(mesh.location)}")
h.key(Qt.Key_Z, "z", Qt.ControlModifier)
h.say("Ctrl+Z")
log(f"  scan location after undo {list(mesh.location)}")

log("== Section Plane, Cut Section")
for label in ("Section Plane", "Cut Section"):
    ok = h.click_toolbar(label)
    h.say(label)
log(f"  tree: {[n.label for n in w._scene_nodes()]}")
log(f"  sketch curves: {len(h.composition.state.model.sketch.curves)}")
h.shot("section")
h.key(Qt.Key_Escape)

log("== Region: click the top")
h.click_toolbar("Region")
h.say("region tool")
log(f"  hint {h.hint()!r}")
h.click(cx, cy)
h.say("clicked")
region = h.composition.state.region_collection.active_region
log(f"  region: {None if region is None else len(region.triangle_indices)} triangles")
h.shot("region")
h.key(Qt.Key_Escape)
h.say("Esc")

log("== Measure two points")
h.click_toolbar("Measure")
h.say("measure")
h.click(cx - 100, cy)
h.click(cx + 100, cy)
h.say("two clicks")
log(f"  measurements {len(h.composition.measure_controller.measurements)}")
h.shot("measure")
h.key(Qt.Key_Escape)
h.key(Qt.Key_Escape)
h.say("Esc Esc")

log("== Save project, New, reopen")
project = Path(sys.argv[1]) / "audit.openretop"
stand_in_file_dialogs(open_path=project, save_path=project)
h.click_toolbar("Save")
h.say("saved")
h.click_toolbar("Open Project")
h.idle()
h.say("reopened")
log(f"  tree: {[n.label for n in w._scene_nodes()]}")
h.close()
log("done")

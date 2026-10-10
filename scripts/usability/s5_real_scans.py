"""Audit 5: the user's own scans - the oil pan and the TurboBumper front end."""

import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent))
from human import Human, answer_dialog, log, stand_in_file_dialogs  # noqa: E402

ROOT = Path(sys.argv[2])
h = Human(Path(sys.argv[1]))
w = h.window
model = h.composition.state.model
modeling = h.composition.modeling_controller


def timed(label, action):
    t = time.perf_counter()
    action()
    h.idle(300)
    log(f"  {label}: {time.perf_counter() - t:.1f}s; status {h.status()[:140]!r}")


log("== oil pan")
stand_in_file_dialogs(open_path=ROOT / "test_assets" / "TSP 302-1 LS Swap Oil Pan.stl")
answer_dialog(choice="mm")
timed("open", lambda: h.click_toolbar("Open Scan"))
mesh = h.composition.state.mesh_object
lo, hi = mesh.source_bounds_min, mesh.source_bounds_max
log(f"  size {np.round(hi - lo, 1).tolist()}, next steps {w.next_steps.guidance.title!r}")
h.shot("oilpan_open")
# the flange: the highest flat ring; look from above and click near an edge of the top
h.key(Qt.Key_5, "", Qt.ControlModifier)
vertices = np.asarray(mesh.source_mesh.vertices)
top = vertices[vertices[:, 2] > hi[2] - 2.0]
flange_point = top[np.argmin(top[:, 0])] + np.array([4.0, 0.0, 0.0])
h.tab("Surface")
h.click_toolbar("Fit Surface")
timed("click the flange", lambda: h.click_world(flange_point))
timed("Create", lambda: h.click_panel("Create"))
log(f"  model: {[(e.name, e.kind, round(e.stats.get('rms', 0), 3)) for e in model.entities]}")
h.shot("oilpan_fit")
h.click_panel("Done")

log("== Section Sketch on the oil pan (XY through the middle)")
h.tab("Solid")
timed("Section Sketch", lambda: h.click_toolbar("Section Sketch"))
log(f"  {w.surfacing_panel.section_info.text()!r}")
timed("Fit Profile", lambda: h.click_panel("Fit Profile"))
log(f"  {w.surfacing_panel.section_info.text()[:300]!r}")
h.shot("oilpan_section")
h.click_panel("Done")

log("== bumper: open, Surface Sketch three clicks along the fender")
stand_in_file_dialogs(open_path=ROOT / "test_assets" / "TurboBumper.stl")
answer_dialog(button="Discard", delay=200)
answer_dialog(choice="mm", delay=900)
timed("open bumper", lambda: h.click_toolbar("Open Scan"))
mesh = h.composition.state.mesh_object
log(f"  {mesh.name}: {mesh.source_triangle_count:,} triangles")
h.key(Qt.Key_7, "", Qt.ControlModifier)
h.tab("Surface")
timed("Surface Sketch tool", lambda: h.click_toolbar("Surface Sketch"))
cx, cy = h.view.width() // 2, h.view.height() // 2
for dx in (-120, 0, 120):
    timed(f"click {dx}", lambda dx=dx: h.click(cx + dx, cy))
timed("Enter", lambda: h.key(Qt.Key_Return))
log(f"  curves {[(c.name, len(c.nodes)) for c in model.sketch.curves]}")
h.shot("bumper_curve")
h.close()
log("done")

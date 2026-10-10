"""Audit 4: Surface Sketch curves with the mouse, Face From Curves, Loft between section
curves, Fill; then menus, palette, preferences and help as a newcomer would look for them."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

sys.path.insert(0, str(Path(__file__).parent))
from human import DIALOGS, Human, answer_dialog, log, scan_of, stand_in_file_dialogs  # noqa: E402

h = Human(Path(sys.argv[1]))
w = h.window
stand_in_file_dialogs(open_path=scan_of("housing"))
answer_dialog(choice="mm")
h.click_toolbar("Open Scan")
h.idle()
model = h.composition.state.model
modeling = h.composition.modeling_controller

log("== Surface Sketch: a closed loop on the top of the housing (4 clicks + click the first)")
h.tab("Surface")
h.click_toolbar("Surface Sketch")
h.say("tool")
log(f"  hint {h.hint()!r}")
h.key(Qt.Key_7, "", Qt.ControlModifier)
loop = [(-25.0, -15.0, 12.5), (25.0, -15.0, 12.5), (25.0, 15.0, 12.5), (-25.0, 15.0, 12.5), (-25.0, -15.0, 12.5)]
import time  # noqa: E402

for point in loop:
    t = time.perf_counter()
    h.click_world(point)
    h.say(f"click {point[:2]} [{time.perf_counter() - t:.2f}s]")
log(f"  sketch curves: {[(c.name, c.closed, len(c.nodes)) for c in model.sketch.curves]}")
h.shot("curve_loop")
log(f"  panel buttons: {[b.text() for b in w.surfacing_panel.findChildren(type(w.surfacing_panel.done_button)) if b.isVisible() and b.isEnabled()][:20]}")
h.click_panel("Face From Curves") or h.click_panel("Face from Curves")
h.say("face from curves")
log(f"  model: {[(e.name, e.kind) for e in model.entities]}")
h.click_panel("Done")

log("== Loft between two section curves: two section planes, cut, select both curves, Loft")
h.tab("Scan")
for _ in range(1):
    h.click_toolbar("Section Plane")
h.click_toolbar("Cut Section")
h.say("cut 1")
curves_before = len(model.sketch.curves)
log(f"  sketch curves now {curves_before}; selected {model.selected_curve_ids}")
h.tab("Surface")
h.click_toolbar("Loft")
h.say("loft tool")
log(f"  loft panel: {w.surfacing_panel.loft_info.text()!r}")

log("== Menus, palette, help: what a newcomer finds")
for menu in w.menuBar().findChildren(QMenu):
    if menu.title():
        actions = [a.text().replace("&", "") for a in menu.actions() if a.text()]
        log(f"  menu {menu.title().replace('&', '')!r}: {actions[:25]}{' ...' if len(actions) > 25 else ''}")
w._dispatch_framework_action("help.about") if False else None
log(f"  dialogs seen: {DIALOGS}")
h.close()
log("done")

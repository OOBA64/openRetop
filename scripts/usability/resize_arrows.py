"""As a user: fit a plane on the housing top, shrink it with the arrows (drag a side, drag a
corner, click an arrow and type a distance)."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent))
from human import Human, log, scan_of  # noqa: E402

h = Human(Path(sys.argv[1]))
w = h.window
w.open_model_path(scan_of("housing"), units="mm")
h.idle()
h.tab("Surface")
h.click_toolbar("Fit Surface")
w._dispatch_framework_action("view.named.top")
h.wait(300)
h.click_world((25.0, 0.0, 12.5))
h.click_panel("Create")
h.click_panel("Done")
model = h.composition.state.model
plane = model.entities[0]
log(f"fitted {plane.name}: area {plane.stats['area']:.1f}, selected {model.selected_ids}, tool {h.composition.modeling_controller.tool}")
w._dispatch_framework_action("view.frame_all")
h.wait(300)
items = w._handle_items()
log(f"arrows: {[item['key'] for item in items]}")
h.shot("arrows")


def area() -> float:
    return float(model.get(plane.id).stats["area"])


def arrow_screen(key: str) -> tuple[tuple[int, int], dict]:
    item = next(i for i in w._handle_items() if i["key"] == key)
    grip = item["point"] + item["direction"] * w._arrow_length(item["point"]) * 0.5
    return h.screen_of(grip), item


log("1. drag the u1 side arrow inwards")
start, item = arrow_screen(next(i["key"] for i in items if i.get("side") and abs(i["direction"][0]) > 0.9 and i["direction"][0] > 0))
target = item["point"] - item["direction"] * 15.0 + item["direction"] * w._arrow_length(item["point"]) * 0.5
end = h.screen_of(target)
before = area()
h.drag(start, end)
h.say("dragged side")
log(f"  area {before:.1f} -> {area():.1f}")
h.shot("side_dragged")

log("2. drag a corner inwards")
corner_key = next(i["key"] for i in w._handle_items() if "sides" in i)
start, item = arrow_screen(corner_key)
end = h.screen_of(item["point"] - item["direction"] * 10.0 + item["direction"] * w._arrow_length(item["point"]) * 0.5)
before = area()
h.drag(start, end)
h.say("dragged corner")
log(f"  area {before:.1f} -> {area():.1f}")

log("3. click an arrow, type -5, Enter")
side_key = next(i["key"] for i in w._handle_items() if i.get("side"))
start, item = arrow_screen(side_key)
h.click(*start)
h.say("clicked arrow")
before = area()
for key, text in ((Qt.Key_Minus, "-"), (Qt.Key_5, "5")):
    h.key(key, text)
h.say("typed")
h.shot("typed")
h.key(Qt.Key_Return)
h.say("enter")
log(f"  area {before:.1f} -> {area():.1f}")
h.key(Qt.Key_Z, "z", Qt.ControlModifier)
h.say("ctrl+z")
log(f"  after undo: {area():.1f}")
h.shot("final")
h.close()
log("done")

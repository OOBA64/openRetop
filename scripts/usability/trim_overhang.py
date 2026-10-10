"""As a user: open the housing scan, fit a plane on its top, trim its overhang by hand."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent))
from human import Human, log, scan_of  # noqa: E402

h = Human(Path(sys.argv[1]))
w = h.window
log("1. open the scan")
w.open_model_path(scan_of("housing"), units="mm")
h.idle()
h.say("opened")
log("2. Surface tab > Fit Surface, click the top rim of the part")
h.tab("Surface")
h.click_toolbar("Fit Surface")
h.say("fit tool")
log(f"  hint: {h.hint()!r}")
w._dispatch_framework_action("view.named.top")
h.wait(300)
h.click_world((25.0, 0.0, 12.5))
h.say("clicked scan")
log(f"  panel fit button enabled: {h.panel_button('Create').isEnabled() if h.panel_button('Create') else None}")
h.click_panel("Create")
h.say("created")
model = h.composition.state.model
log(f"  model: {[(e.name, round(e.stats.get('area', 0), 1)) for e in model.entities]} selected {model.selected_ids}")
h.shot("fitted_plane")
log("3. Trim (toolbar), Manual, Cut Line, two clicks across the overhang, Enter")
h.click_toolbar("Trim")
h.say("trim tool")
log(f"  hint: {h.hint()!r}; panel info: {w.surfacing_panel.trim_info.text()!r}")
h.click_panel("Manual")
h.click_panel("Cut Line")
h.say("cut line")
log(f"  capture owner: {w.viewport.left_capture_owner}")
for point in ((32.0, -12.0, 12.5), (32.0, 12.0, 12.5)):
    ok = h.click_world(point)
    h.say(f"click {point} ok={ok}")
h.shot("cut_line")
h.key(Qt.Key_Return)
h.say("enter")
session = h.composition.modeling_controller.session
log(f"  pieces: {None if session is None or session.trim_pieces is None else [round(p['area'], 1) for p in session.trim_pieces]}")
h.shot("pieces")
log("4. click the overhang to drop it, Apply")
h.click_world((38.0, 0.0, 12.5))
h.say("clicked overhang")
session = h.composition.modeling_controller.session
log(f"  keep flags: {None if session is None or session.trim_pieces is None else [p['keep'] for p in session.trim_pieces]}")
h.shot("overhang_dropped")
h.click_panel("Apply")
h.say("applied")
log(f"  model: {[(e.name, e.visible, round(e.stats.get('area', 0), 1)) for e in model.entities]}")
h.shot("applied")
h.close()
log("done")

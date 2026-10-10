"""Audit 6: general usability - palette, preferences, tree context menu, keys, undo chain."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

sys.path.insert(0, str(Path(__file__).parent))
from human import Human, answer_dialog, log, scan_of, stand_in_file_dialogs  # noqa: E402

h = Human(Path(sys.argv[1]))
w = h.window
stand_in_file_dialogs(open_path=scan_of("housing"))
answer_dialog(choice="mm")
h.click_toolbar("Open Scan")
h.idle()

log("== Ctrl+K palette: search 'trim', 'extrude', 'align', 'fillet', 'hole', 'mirror', 'decimate'")
palette = w._palette_dialog
for query in ("trim", "extrude", "align", "fillet", "revolve", "mirror", "decimate", "fill holes", "smooth", "deviation"):
    results = [item.label for item in w.shell.command_palette.search(query, include_disabled=True)] if hasattr(w, "shell") else None
    if results is None:
        from workbench_ui import CommandPaletteWidget  # noqa: F401

        widget = w.palette
        found = [d.label for d in w._framework_actions.definitions if query.lower() in (d.label + " " + d.description).lower()]
        results = found
    log(f"  {query!r}: {results[:6]}")

log("== Preferences dialog")
answer_dialog(delay=400)
w._dispatch_framework_action("file.preferences")
h.say("preferences")

log("== Tree: right-click the scan row")
from human import DIALOGS  # noqa: E402,F401

tree = w.scene_tree.tree
item = tree.topLevelItem(0)
log(f"  top-level rows: {[tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]}")

log("== Section, then Delete key on the section result, undo chain")
h.tab("Scan")
h.click_toolbar("Cut Section")
results_before = len(h.composition.state.section_collection.results)
node = next(n for n in w._scene_nodes() if n.kind == "section_result")
w._on_tree_selection(type("S", (), {"ids": (node.id,)})())
h.key(Qt.Key_Delete)
h.say("Delete")
log(f"  section results {results_before} -> {len(h.composition.state.section_collection.results)}")
h.key(Qt.Key_F2)
h.say("F2 (rename?)")
for _ in range(3):
    h.key(Qt.Key_Z, "z", Qt.ControlModifier)
    h.say("Ctrl+Z")
h.key(Qt.Key_Y, "y", Qt.ControlModifier)
h.say("Ctrl+Y")
h.key(Qt.Key_Z, "Z", Qt.ControlModifier | Qt.ShiftModifier)
h.say("Ctrl+Shift+Z")
log("== Help menu")
for menu in w.menuBar().findChildren(QMenu):
    if menu.title().replace("&", "") == "Help":
        log(f"  Help: {[a.text() for a in menu.actions()]}")
log("  F1: ")
h.key(Qt.Key_F1)
h.say("F1")
h.close()
log("done")

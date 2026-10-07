# UI/UX audit of openRetop (PySide6 workbench)

Method: launched the real app (not offscreen) at 1500x900, dumped every menu, read the
inspector and toolbar code, and walked the main path: open a mesh -> section ->
curve -> loft -> STEP, plus the Region and Manual Curve tools. Evidence is quoted
from what the app shows. Task IDs refer to [TASKS.md](TASKS.md).

**Goal being served:** a CAD tool a new user can pick up without a manual. The test is
"can someone who has never seen it get from a scan to a STEP file in 10 minutes".

## What already works (keep)

- Consistent action registry: every command has an ID, label, description, shortcut
  and enabling *conditions* (`ActionCondition`). This is the foundation for most of
  the fixes below.
- A Scene tree with visibility checkboxes, dockable panels, and an on-viewport
  orientation gizmo / named-view controls.
- Undo/redo, a progress dialog for long work, and (since the rework) responsive
  background tasks.
- Hints exist in the model: `ToolModeManager` carries per-tool instruction text
  ("Click the mesh to grow a region; Esc finishes").

## Findings

Severity: **S1** blocks or misleads a new user, **S2** slows people down, **S3** polish.

### First run and empty state
| ID | Sev | Finding (evidence) | Fix |
|---|---|---|---|
| F-01 | S1 | Launch shows a black viewport and an empty Properties panel that says only "Selection: No selection / CAD backend: CadQuery". Nothing says "open a scan to begin". | UX-01 welcome / empty state |
| F-02 | S1 | The Scene tree lists 14 empty folders before anything exists (Section Results, Unassigned, Manual, Region Boundaries, Repaired, Projected, Rebuilt, Preview Surfaces, BREP Surfaces, Regions, Editable Features...). It reads like a manual for internals. | UX-02 show only populated categories |
| F-03 | S2 | No drag-and-drop of a mesh/project onto the window; no "recent files" on first screen. | UX-03 |
| F-04 | S2 | A default "Section Plane 1" exists before a model is loaded, so the tree implies work has been done. | UX-02 |

### Discoverability and vocabulary
| ID | Sev | Finding | Fix |
|---|---|---|---|
| F-05 | S1 | **154 menu items, 125 of them disabled at launch, none explaining why.** The Modify menu alone lists 90 entries mixing transforms, section tools, curve repair, manual-curve point edits, regions and BREP rebuilds. | UX-05 menu restructure, UX-06 disabled-reason tooltips |
| F-06 | S1 | A command palette exists but is a hidden bottom dock with no shortcut and no menu entry, so it is effectively undiscoverable. It is the best answer to "where is the command for X?". | UX-04 Ctrl+K palette |
| F-07 | S2 | No tooltips anywhere on toolbar buttons or menu items, even though every action already has a `description`. `setToolTip` is used in exactly one place (view controls). | UX-06 |
| F-08 | S2 | Toolbar is 12 text-only buttons with no icons, no grouping and no separators; `Compute Section` (the command that follows `Add Section Plane`) is not on it. | UX-07 |
| F-09 | S2 | Internal jargon in user-facing labels: "Unassigned", "Repaired", "Projected", "Rebuilt", "Preview Surfaces", "Editable Features", "Mesh-Conforming Loft Preview", "Create Editable BREP Loft", "Convert Boundary to Guide Curve". | UX-08 vocabulary pass |
| F-10 | S2 | View menu has 7 named views with no shortcuts; Frame All has none. Users expect Home/numpad conventions. | UX-09 |

### Guidance and feedback
| ID | Sev | Finding | Fix |
|---|---|---|---|
| F-11 | S1 | **No workflow.** The pipeline (scan -> sections -> curves -> surfaces -> STEP) is implicit; the app never says what the next sensible step is. | UX-10 workspaces/stepper, UX-11 "Next steps" panel |
| F-12 | S2 | The status bar repeats one message three times (e.g. "Drawing curve: left-click to add points..." appears twice plus the tool text) in a one-line bar, and the strip says "Ready  Ready" when idle. | UX-12 |
| F-13 | S2 | Tool hints are only in that status line. While drawing a curve or selecting a region, nothing on the canvas says what the mouse does ("Left-click add point - Enter finish - Esc cancel - Right-drag orbit"). | UX-13 on-canvas tool hint |
| F-14 | S2 | Properties shows nothing useful when idle and little when selected: mesh shows "Display triangles" only (no size, units, source triangle count, watertight); a section curve shows no fit error or tolerance. No contextual buttons ("Compute section", "Loft with...", "Export"). | UX-11, UX-14 |
| F-15 | S2 | Errors are modal `QMessageBox.critical` dialogs plus a one-line label; no "what to do next" and no persistent log. | UX-15 |
| F-16 | S3 | Properties dock has a visual glitch where the "Diagnostics" group title overlaps the panel header after a model is loaded. | UX-16 |

### Learning and safety
| ID | Sev | Finding | Fix |
|---|---|---|---|
| F-17 | S2 | No first-run guidance, sample model or help beyond a one-line About box; no keyboard/mouse cheat sheet although the mouse mapping differs per tool. | UX-17 tour + cheat sheet, UX-18 sample |
| F-18 | S2 | Closing/new/open prompt about unsaved changes, but there is no autosave or recovery after a crash. | UX-19 |
| F-19 | S3 | Dark theme only; no UI-scale option (the pixel-test failure on this display suggests DPI sensitivity). | UX-20 |
| F-20 | S2 | Destructive commands (Delete Mesh, Clear All Sections) have no confirmation and the undo label does not say what will be undone. | UX-21 |

## Design principles (decisions)

1. **One obvious next step.** At any moment the app can answer "what should I do now?"
   (Next-steps panel, empty states, stepper).
2. **Never a dead control.** A disabled command explains why and what enables it.
   `ActionCondition` already knows; surface it.
3. **Progressive disclosure.** ~15 primary commands visible; everything else is one
   Ctrl+K away. Menus group by task, not by implementation.
4. **Direct manipulation with on-canvas hints.** Tools say what the mouse does where
   the user is looking, not in a status bar.
5. **User vocabulary.** Scan, section, curve, surface, export. Internal terms stay in
   docs and tooltips ("Rebuilt" -> "Regenerated").
6. **Forgiving.** Everything undoable, destructive actions confirmable, work autosaved.
7. **Learn by doing.** Sample model, first-run tour, cheat sheet inside the app.

## Target workflow model

Five workspaces in a stepper above the viewport. A workspace picks the toolbar,
which scene categories are expanded, the Next-steps panel content, and what the
Properties panel offers. Renderer choice is independent of the workspace.

```
 1 Scan  ->  2 Sections  ->  3 Curves  ->  4 Surfaces  ->  5 Export
 open,       add planes,     clean, join,   loft, fill,     STEP, project
 orient,     compute         edit, close    patch, review   save
 set units
```

Later workspaces (Align, Repair, Print Prep, CAD) plug into the same stepper model
(see [ROADMAP_REVIEW.md](ROADMAP_REVIEW.md)).

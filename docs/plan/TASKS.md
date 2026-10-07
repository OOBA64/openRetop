# openRetop task list

Owner of the plan: the `claude/openretop-refactor-b59181` line of work.
Supersedes the numbered Codex task files in `docs/v3/tasks/` (kept as history).

Conventions
- **Priority:** P0 do first, P1 next, P2 when convenient.
- **Size:** S under a day, M a few days, L a week or more.
- **Status:** `todo`, `doing`, `done`. A task is done only when its acceptance
  criteria pass in an automated test **and** it was checked in the running app.
- Every task lands as small commits; the full suite, `ruff` and `mypy` stay green.
- Evidence for UX tasks is in [UX_AUDIT.md](UX_AUDIT.md); the reasoning for the R-tasks is in
  [ROADMAP_REVIEW.md](ROADMAP_REVIEW.md).

## Completed in the first rework pass

| ID | Summary |
|---|---|
| D-01 | STL vertices welded at load (tolerance scaled to mesh); box face = 2 triangles |
| D-02 | Loader: ordinary exceptions, honest normals flag; adjacency cache on the mesh |
| D-03 | Atomic project/settings writes, relative mesh path, schema v2 + migrations, region round-trip |
| D-04 | Section curves fitted with tolerance-driven B-splines; CAD builds NURBS edges/lofts; seam alignment |
| D-05 | Units (mm/cm/m/in) at import, in the project, driving tolerances and STEP header |
| D-06 | Vectorised sections/adjacency/normals; worker-thread import, sections and CAD builds |
| D-07 | `openretop` src-layout package, pyproject, ruff, mypy, CI rewrite, feature-named tests |

---

## Track U - UX foundations

Principles and findings: [UX_AUDIT.md](UX_AUDIT.md).

### Slice A (first UX pass)
| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| UX-02 | P0 | S | done | Scene tree shows only categories that have content; no section plane exists before a model is open | Empty project shows a single hint row, not 14 folders. A new category appears the first time an item is created. Existing scene-model tests updated. |
| UX-04 | P0 | S | done | Command palette on Ctrl+K and View menu; searches label, description, category; shows shortcut | Ctrl+K opens and focuses it; typing "loft" lists loft actions; Enter runs the first enabled one; Esc closes. |
| UX-06 | P0 | M | done | Tooltips for every toolbar/menu action: description + shortcut + *why it is disabled* | Hovering a disabled "Compute Section" with no model says "Needs: a loaded model". Reasons come from `ActionCondition`, not hard-coded strings. Every registered action has a non-empty tooltip (test). |
| UX-12 | P0 | S | done | One message area in the status bar plus a separate tool-hint area; no triplicated text; idle state shows model name, units, triangle count | Status bar never shows the same text twice; idle shows e.g. `part.stl - mm - 327,680 triangles`. |
| UX-01 / UX-11 | P0 | M | done | Properties panel when nothing is selected becomes a **Model & Next steps** panel: empty state with *Open scan* / recent files; once a model exists, a model summary and the next sensible actions as buttons | No model: "Open a scan" button, supported formats, recent projects. Model loaded, no sections: "Add a section plane" and "Compute section" buttons. Curves exist: "Loft between curves". BREP exists: "Export STEP". Each button dispatches the existing action and is disabled with a reason when not applicable. |
| UX-03 | P0 | S | done | Drag-and-drop `.stl/.obj/.ply/.openretop` onto the window; recent files list | Dropping a mesh runs the normal import flow (including the unit prompt); dropping a project opens it; other extensions are rejected with a message. |
| UX-09 | P1 | S | done | View shortcuts: Home = Frame All, F = Frame Selected, Ctrl+1/3/7 = Front/Right/Top (Ctrl+Shift for opposite), 0 = Isometric | Conflict check (`shortcut_conflicts`) is empty; documented in the cheat sheet. |
| UX-16 | P2 | S | done | Fix the Properties header/"Diagnostics" overlap | Screenshot comparison in a test or manual check recorded in the commit. |
| UX-26 | P0 | S | done | Selections made in the viewport (picks) now update the Scene tree and Properties panel; the Properties panel no longer paints stale group boxes | Pick a curve in the viewport: tree row highlights, inspector shows its fields (`tests/test_ux_selection_sync.py`). Found while verifying UX-16. |

### Slice B
| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| UX-10 | P0 | L | todo | Workspaces + stepper: Scan, Sections, Curves, Surfaces, Export. A workspace sets the toolbar, expanded tree categories and Next-steps content | Switching workspace changes toolbar contents; the stepper marks steps that have results; works without any renderer setting. |
| UX-05 | P1 | M | todo | Restructure menus by task (File, Edit, View, Scan, Sections, Curves, Surfaces, Tools, Help); manual-curve point editing becomes a submenu that appears only while that tool is active; Modify's 90 entries are split | No menu above ~25 entries; every action reachable from either a menu or the palette; test asserts every registered action appears in exactly one menu or is palette-only by an explicit allow-list. |
| UX-07 | P1 | M | todo | Toolbar: icons, separators, grouping per workspace, `Compute Section` present | Every toolbar action has an icon and tooltip; groups separated. |
| UX-08 | P1 | S | todo | Vocabulary pass over labels and tree categories (see F-09) with a glossary tooltip for retained technical terms | No label in the audit's jargon list remains; docs updated. |
| UX-13 | P1 | M | todo | On-canvas tool hint overlay while Region / Manual Curve / Transform are active | Overlay text matches the tool's instructions and disappears when the tool ends. |
| UX-14 | P1 | M | todo | Richer inspector: mesh bounds in model units, source and display triangle counts, watertight flag, weld count; curve fit tolerance/error; contextual buttons | Values come from existing state; mesh selection shows `extent` with unit. |
| UX-15 | P1 | M | todo | Non-modal notifications with a "Details" expander and an activity log panel; actionable error text | Import failure shows a toast with the reason and suggestion; the log keeps the last 200 events. |
| UX-17 | P1 | M | todo | Help > Mouse & Keys cheat sheet that reflects the *active tool*; optional first-run tour (4 steps) | Cheat sheet shows the mapping for the current tool; tour can be dismissed and not shown again (setting). |
| UX-19 | P1 | M | todo | Autosave + crash recovery: periodic snapshot beside the project, offered on next start | Kill the process during an edit; restart offers recovery; clean exit removes the snapshot. |
| UX-21 | P1 | S | todo | Confirm destructive actions; Edit menu shows "Undo <name>" / "Redo <name>" | Delete Mesh and Clear All Sections ask first; the undo label is the command name. |
| UX-22 | P1 | M | todo | **Multi-section**: "Add N sections between min and max along axis" plus "Compute all" | A dialog creates N evenly spaced planes in one undo step; sections compute in one background task with progress. |
| UX-18 | P2 | S | todo | File > Open Sample (generated mesh) for learning | Opens without a file dialog and demonstrates the full workflow. |
| UX-20 | P2 | M | todo | UI scale setting and a light theme | Settings round-trip; widgets legible at 100/125/150%. |
| UX-23 | P2 | M | todo | Viewport hover highlight and selection outline; consistent colours per object type | Hovering a curve/surface highlights it; selected objects get an outline. |
| UX-24 | P2 | M | todo | Keyboard navigation and accessible names for all custom widgets | Tab order covers docks; every control has an accessible name (test). |
| UX-25 | P1 | S | todo | Usability script: "scan to STEP in 10 minutes" with timing and a notes template; run with at least three people | Results table added to `docs/plan/`; findings feed new UX tasks. |

---

## Track R - architecture roadmap (from the ChatGPT roadmap, re-sequenced)

Rationale and disagreements: [ROADMAP_REVIEW.md](ROADMAP_REVIEW.md). None of these may
change visible behaviour until R-06.

| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| R-01 | P1 | M | todo | `ViewportHost` between the window and the viewport; the window no longer reaches into VTK-specific members | Window code references only the host interface; existing viewport tests pass unchanged. |
| R-02 | P1 | M | todo | Extract `VTKViewportBackend` behind a `ViewportBackend` contract (attach, close, synchronize(snapshot), frame, camera, pick, set_selection, render, capabilities) | `QtSceneViewport` delegates to the backend; a fake backend can drive the window in tests. |
| R-03 | P1 | S | todo | `ViewportCapability` model and a capability report per backend | Window asks capabilities instead of assuming; unit tests for the VTK report. |
| R-04 | P1 | S | todo | `CameraState` (position, focal point, up, projection, scale, fov) with VTK translation both ways and a "Link cameras" option for later | Round trip VTK -> state -> VTK reproduces the view within tolerance. |
| R-05 | P1 | L | todo | `BrepRenderItem` + persistent topology IDs: openRetop face/edge IDs <-> `TopoDS` subshapes <-> tessellation triangle ranges; IDs survive a rebuild when the source curves are unchanged | Test: build a loft, read face/edge IDs, rebuild, IDs match; tessellation exposes `face_id` per triangle. |
| R-06 | P1 | M | todo | VTK face/edge/vertex picking and highlighting from the topology IDs; selection modes in the UI | Clicking a loft face selects "Face N" in the tree/inspector; edges selectable; frame-selected works. |
| R-07 | P2 | M | todo | **OCCT viewport spike** (time-boxed, 1 week) with written go/no-go: embed `V3d_View` in PySide6, display a STEP, orbit/pan/zoom, pick a face | Report in `docs/plan/` with Windows + Linux results. No further OCCT viewport tasks until a *go*. |
| R-08 | P2 | M | todo | Per-viewport renderer override (advanced setting) | Only after R-07 go; otherwise cancelled. |
| R-09 | P2 | L | todo | Split view with two synchronized viewports (shared `CameraState` and selection IDs); scan reference vs reconstruction | Orbiting one rotates the other; selecting in one highlights in both. |
| R-10 | P2 | L | todo | Mesh repair workspace: components, island delete, holes, normals, non-manifold diagnostics, simplify | Each operation undoable and shown in the Next-steps panel. |
| R-11 | P2 | L | todo | Alignment workspace: datum / 3-2-1, point pairs, ICP, deviation colouring | ICP converges on a synthetic displaced scan within a stated tolerance. |
| R-12 | P2 | L | todo | Print-prep workspace: cut planes, segmentation, connectors, wall analysis, STL/3MF export | Splitting a box into two parts exports two watertight meshes. |
| R-13 | P2 | L | todo | CAD depth: guide-rail lofts, four-boundary patches into BREP, trims, intersections, sewing, shells/solids, booleans, fillets | Each is a separate task with a STEP round-trip test; kernel stays CadQuery/OCP unless a blocker is documented (no build123d switch planned). |

---

## Track E - engineering debt

| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| E-01 | P0 | M | todo | Region selection on the **source** mesh (map to display proxy for drawing) | Region triangle indices refer to the source mesh; a >150k-triangle mesh selects the same face as the full mesh; boundary extraction uses source geometry. |
| E-02 | P1 | M | todo | Multiple regions per project | Several regions persisted, listed in the tree, individually selectable and deletable. |
| E-03 | P1 | M | todo | Split `application/manual_curve_controller.py` (1.7k lines) by concern | No file over ~600 lines; behaviour tests unchanged. |
| E-04 | P1 | M | todo | Split `application/brep_controller.py` (1.5k) | As above. |
| E-05 | P1 | M | todo | Move model builders (`_scene_nodes`, `_inspector_fields`, `_surface_previews`) and file lifecycle out of `main_window.py` | Window under ~1,000 lines; builders unit-tested without widgets. |
| E-06 | P1 | L | todo | Clear mypy `ignore_errors` modules one by one | List in `pyproject.toml` shrinks every release; CI keeps new modules clean. |
| E-07 | P2 | S | todo | Tiny-curve thresholds in project units | `CURVE_TINY_MIN_*` derived from `geometry.tolerances`. |
| E-08 | P1 | M | todo | Large-scan performance (1M-5M triangles): memory-lean loader, background proxy build, section prefilter by bounding slab | 2M-triangle STL opens in a stated time budget with the UI responsive; benchmark recorded. |
| E-09 | P2 | S | todo | DPI-independent assertion in the navigation-widget pixel test | Passes at 100%, 125% and 150% scaling. |
| E-10 | P2 | M | todo | Run the visible-Windows UI tests in CI (self-hosted or scheduled) | Job exists and is green or tracked. |
| E-11 | P2 | S | todo | CadQuery compatibility matrix for the STEP unit argument and loft API | Tested against the pinned version and the next minor release. |
| E-12 | P2 | S | todo | Benchmarks with regression thresholds in CI (sections, adjacency, load) | CI fails on a >2x slowdown of the recorded baseline. |

---

## How tasks are run
1. Pick the top `todo` task in the slice being worked.
2. Write the failing test (or script the real-app check for pure-UI work).
3. Implement; run `ruff check .`, `mypy`, and the full suite.
4. Check the behaviour in the real app and note it in the commit message.
5. Flip the status here in the same commit.

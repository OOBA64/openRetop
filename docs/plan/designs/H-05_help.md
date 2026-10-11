# H-05 and H-06 implementation design

Line citations are for commit `233d271`, the current HEAD. The worktree also has uncommitted H-03 edits in `modeling_controller.py`, `jobs.py`, `surfacing.py`, `modeling_scene.py` and `surfacing_workbench.py`, which shift some lines in those files. Rebase onto those edits before implementing.

**Owner's input.** The owner prefers short one-line explanations on hover. So the help stays small: one help window, pages no longer than one screen, and each page opens with the tool's existing hover text (the H-10 descriptions).

## 1. What exists today, and the gaps

### H-05 (help)

**What exists:**
- **Help menu.** It holds only About. The rows in `_FILE_ACTIONS` (`main_window.py:154-166`) are registered at `main_window.py:295` and dispatched in `_dispatch_framework_action(self, action_id: str, payload: Mapping[str, object] | None = None) -> object` (`main_window.py:382`). About is handled at `:409-415`.
  - F1 is bound to nothing anywhere. The only use is `scripts/usability/s6_general.py:66`, which presses it.
- **Active tool.** `self.tool_modes` (`ToolModeManager`, `contracts.py:224`) has `state.id` set to one of `modeling | region | measure | transform | section`.
  - `active` (`contracts.py:249`) says whether a tool is running.
  - All surfacing tools enter the same id, `"modeling"` (`surfacing_workbench.py:147-152`). The specific tool is `composition.modeling_controller.tool`, one of `TOOLS` (`modeling_controller.py:40`).
  - **Name clash:** mode `"section"` means the section-plane tool, but modeling tool `"section"` means Section Sketch.
- **Tooltips.** `action_tooltip(definition: ActionDefinition) -> str` (`shell.py:39`). The descriptions are in `_DESCRIPTIONS` (`actions.py:321`), and the H-10 one-liners are there too.
- **Next steps panel.** `build_guidance(state: AppState, *, selected_curve_count: int = 0) -> Guidance` (`guidance.py:42`) is drawn by `NextStepsPanel.set_guidance(...)` (`next_steps.py:33`). The enabled-state/tooltip closure is inline at `main_window.py:984-989`.
- **Workspace switch.** Only `ApplicationShell._invoke_from_ui(self, action_id: str) -> None` (`shell.py:133`) switches workspace. The palette (`main_window.py:1234`) and Next steps (`:249`) call `registry.invoke`, so they do not switch. Getting Started must use `_invoke_from_ui`.
- **Panel header.** Title plus Done (`surfacing_panel.py:123-134`). `_keep_hotkeys_working` (`:162`) gives buttons `NoFocus`.
- **Panel signal routing.** Panel signals go through `_on_surfacing_action(self, action_id: str, payload: dict[str, Any]) -> None` (`surfacing_workbench.py:133`) to `_dispatch_application_action`, which does not handle `help.*`.
- **Tool keys** live in code:
  - `_surfacing_key` (`surfacing_workbench.py:154-200`): the Enter-to-primary-action dict is at `:185-194`; Esc at `:172`; trim cut-line keys at `:164-169`.
  - `_sketch_key` (`:690`), `_sketch2d_key` (`:214`) and `_brush_key` (`:673`).
- **Content.** `docs/v3/V3_USER_GUIDE.md` is a 37-line overview with no page per tool, and nothing is packaged.
  - The root `pyproject.toml` has no `package-data`, so `.md` files would not ship.
  - The root wheel probably also leaves out `workbench_ui/assets/*.svg`: only `packages/workbench_ui/pyproject.toml` declares them. I did not build a wheel to confirm (the repo is read-only for this task).
- **Qt support, verified offscreen on PySide6 6.11.2:**
  - `QTextBrowser.setMarkdown` draws tables and keeps links with custom schemes (`action:model.trim_apply`, `help:trim`).
  - A `QAction` with shortcut F1 fires when `QApplication.sendEvent(child, KeyPress F1)` is called, including while a `QLineEdit` has focus. So `Human.key(Qt.Key_F1)` will reach it.
- **Constraint.** `tests/test_architecture.py` fixes the exact set of `*_controller.py` files, so no new controller can be added.

**Gaps:** there is no help content, no F1, no help for the active tool, and no "?" button.

### H-06 (trim and sew results)

**What exists:**
- **Kernel.** `S.sew(faces: list[object], *, tolerance: float = 0.01, make_solid: bool = True) -> SewResult` (`surfacing.py:721-759`). It knows only the count `NbFreeEdges()` (`:735`) and adds the warning "N open edges…" (`:758`).
  - `jobs.sew(breps: list[bytes], *, tolerance: float = 0.05) -> dict[str, Any]` (`jobs.py:301-314`) returns `kind`, `solid`, `closed`, `free_edges` and `volume`.
  - Edge polylines come from `shape_edges(shape: Any, samples: int = 48) -> list[np.ndarray]` (`jobs.py:42`), in `TopTools_IndexedMapOfShape` order.
- **Controller.** `trim_apply(self, *, sew: bool = True) -> CommandResult` (`modeling_controller.py:1701-1750`).
  - Message at `:1730-1733`: `"Shell with {n} open edges (not closed yet)"`. It is shown only in the status bar.
  - The panel's `trim_info` line (`surfacing_workbench.py:1309-1321`) shows a stale "N visible surface(s) will be split" after Apply.
- **Stats and undo.** Stats are copied by `entity_from_result(...)` (`document.py:186`, key list at `:201`). They persist through `_plain` (`persistence.py:45-58, 79, 144`). Undo restores entities through `snapshot`/`restore` (`document.py:164-183`).
- **Drawing.** `modeling_items(modeling: ModelingSceneInput, mesh_object: object | None)` (`modeling_scene.py:84`) draws entity edges at `:116-139`.
  - Ordinary edges are dark; the selected entity's edges are yellow.
  - Fill's picked edges get a second, magenta item, `model-chain:` (`:130-139`). Picking maps `model-edges:` and `model-face:` to a node in `_model_node_for_actor` (`main_window.py:1663-1669`) and in `_fill_pick` (`surfacing_workbench.py:1215`).
- **Inspector.** It shows Type "Shell" and "Open edges N" (`surfacing_workbench.py:1683-1684`). Read-only values are a `QLabel` without word wrap (`widgets.py:341`).
- **Compare.** It says nothing about shell versus solid (`modeling_controller.py:1754-1772`). The deviation from a shell is meaningful as it is, so no change is needed.
- **Guidance bug.** It treats any `is_body` as done (`guidance.py:60-71`), so an open shell gets "A body is ready… export it".
- **Export** (`modeling_controller.py:1851`) writes a shell without saying it is not a solid.

**A blocking gap in "fit the missing face, then Trim again":**
- `start("trim")` uses only visible surfaces that are not bodies (`:234`).
- `trim_apply` hides the sources (`:1744-1746`).
- So after a shell exists, fitting the missing face and opening Trim gives one source, and Trim fails with "Trimming needs two surfaces" (`:1613`).
- The message must not tell people to do something that fails.

**Kernel probes (verified):**
- **Box, each face removed in turn.** Counting the faces each edge belongs to (`TopExp.MapShapesAndAncestors_s` from edge to face; one face means free; skip `BRep_Tool.Degenerated_s`) gives 4 edges, the same as `NbFreeEdges`.
  - The indices line up with `jobs.shape_edges`, and the polylines lie on the missing face.
  - A cylinder's seam edge is not counted.
- **Bracket with face 9 (a plane) left out.** 16 free edges, matching `NbFreeEdges`, found in 1.6 ms.
  - `ShapeAnalysis_FreeBounds` gives 5 wires (one outer loop and four hole circles), so a count of "gaps" would mislead. I don't use it.
- **Cube test fixture.** Six oversized planes (14 mm) on a 10 mm cube, plus 2,400 scan points with normals: `jobs.trim` then `jobs.sew` makes a solid of 1000.0 mm³ in 1.65 s. With five planes it makes a shell with 4 free edges in 0.09 s.

## 2. User flow

### H-05

1. A newcomer starts the app. Next steps (the START and SCAN stages) gains a button, "How it works (6 steps)", which runs `help.getting_started`.
   - The menu has Help > Getting Started, Help for This Tool (F1), Mouse and Keys, and About. All of them are also in Ctrl+K.
2. **Getting Started** is a non-modal Help window. Each of the six rows has a number, a title, one line of text, a **Start** button and a "How?" link to the tool's page:
   1. Open the scan (`file.open_model`): "pick its unit".
   2. Check its size (`measure.model_size`): "compare with the real part; wrong unit? Edit > Set Model Units".
   3. Fit a surface to every face (`model.fit_surface`): "click a face, Enter; repeat".
   4. Trim into a solid (`model.trim`): "Split Surfaces, Apply. 'Not closed yet' means red edges show where a face is missing: go back to step 3, then Trim again."
   5. Compare with the scan (`model.compare`).
   6. Export STEP (`file.export_model`).

   - A footer offers the other path: "Prismatic part? Solid: Section Sketch then Extrude", with `help:` links.
   - The current step is bold, chosen from `build_guidance().stage`. A disabled Start button shows the reason from `action_tooltip`, as Next steps does.
   - Start calls `_invoke_from_ui(id)`, so the workspace switches. Focus then goes back to the main window, so Enter and Esc reach the tool. The Help window stays open.
3. **In a tool**, F1 or the panel's **?** button (next to Done; tooltip "How to use Trim Surfaces (F1)") opens that tool's page:
   - Title: the action label. First line: the action's hover text.
   - Sections: Steps, Mouse & keys, If it goes wrong, See also.
   - F1 with no tool open shows Getting Started.
   - Esc closes the Help window. Back and Forward come from `QTextBrowser`.
4. **Help > Mouse and Keys** shows three parts:
   - The mouse table (orbit with left drag, or Alt/Shift+left inside tools; pan with middle or Shift+left; zoom with right drag or the wheel).
   - The active tool's "Mouse & keys" table, or the line "Open a tool to see its keys".
   - Every command that has a shortcut, built from the live registry, so changes made in Preferences show.

   This replaces UX-17.

   The region, measure, transform and section-plane tools have no panel. F1 works for them through `tool_modes.state.id`.

### H-06

1. Trim, then Apply.
   - If the result is not closed, the status bar and the panel's info line say: **"Not closed yet: 4 edges have no neighbouring face (red). Fit the missing face there, or extend the surface that stops short, then Trim again."**
   - The open edges are drawn bright red, 4 px wide, on the open body.
   - A **Show the gaps** button frames the camera on them.
2. The highlight stays as long as that open body exists and is visible. There is no timer, and it is not tied to the next action. It goes away when the body is hidden, deleted, or replaced by a later trim. Undo and redo bring it back.
3. The person fits the missing face (Fit Surface, click it, Enter), then opens Trim.
   - The hidden source surfaces of each visible open body join the new face.
   - Split, then Apply gives **"Closed solid: volume 1,000.0 mm^3. Compare it with the scan, then Export."** The old open body is hidden.
4. With the open body selected, the inspector shows:
   - Type: "Shell (not closed)"
   - Open edges: 4
   - To close it: "fit or extend the face at the red edges, then Trim"

   The tree row reads "Shell 1 (not closed)". Next steps shows a new stage, "Close the gaps", with the buttons Fit Surface (primary), Extend and Trim.
5. Exporting an open body still works, with the warning "Shell 1 is not closed: written as surfaces, not a solid."

## 3. Data and code changes

### H-05

**New package `src/openretop/help/`.** Pure Python, no Qt. It imports nothing from `application`, which avoids cycles.
- `__init__.py`:
  ```python
  TOOL_ACTIONS: Mapping[str, str]   # topic -> the action that starts it (title and one-liner come from the registry)
  #  {"sketch":"model.sketch","plane_sketch":"model.plane_sketch","section":"model.section_sketch","extrude":"model.extrude",
  #   "fit_surface":"model.fit_surface","loft":"model.loft","fill":"model.fill","extend":"model.extend","trim":"model.trim",
  #   "compare":"model.compare","section_plane":"section.add_plane","region":"region.start","measure":"measure.distance",
  #   "transform":"transform.move"}
  @dataclass(frozen=True)
  class HelpStep: action_id: str; title: str; text: str; topic: str = ""
  GETTING_STARTED: tuple[HelpStep, ...]          # the six rows above
  NAVIGATION: tuple[tuple[str, str], ...]        # mouse rows; H-11 presets later swap this tuple
  def page(topic: str) -> str                     # importlib.resources.files(__name__).joinpath(f"{topic}.md").read_text("utf-8"); KeyError for an unknown topic
  def section(markdown: str, heading: str) -> str # the text under "## heading" up to the next "## "
  def topic_for(modeling_tool: str | None, tool_mode: str | None) -> str
  #  modeling_tool if set; otherwise {"section":"section_plane","region":"region","measure":"measure","transform":"transform"}.get(tool_mode, "getting_started")
  def links(markdown: str) -> list[tuple[str, str]]  # (scheme, target) of the action:/help: links, for tests
  ```
- Fourteen pages, `<topic>.md`, each starting at `## Steps`. Each has a `## Mouse & keys` table, `## If it goes wrong`, and a `See also` line with `help:` links.
  - A link with empty text, `[](action:model.trim_apply)`, gets the action's current label and shortcut when the page is drawn. Renames and Preferences changes then cannot make a page wrong. Pages should not spell out menu paths, because H-09 will move them.
- `pyproject.toml`:
  ```toml
  [tool.setuptools.package-data]
  "openretop.help" = ["*.md"]
  workbench_ui = ["assets/*.svg"]   # also fixes the probable missing-icons gap
  ```

**New `src/openretop/presentation/qt/help_window.py`:**
```python
class HelpWindow(QDialog):                       # non-modal, about 520 x 680, setObjectName("help_window")
    action_requested = Signal(str)
    def __init__(self, parent: QWidget | None = None) -> None   # self.browser = QTextBrowser (setOpenLinks(False), anchorClicked -> _on_link); self.steps = a QWidget of rows
    def show_page(self, topic: str, title: str, intro: str, markdown: str) -> None   # "# title\n\nintro\n\n" + markdown; steps hidden
    def show_getting_started(self, steps: Sequence[HelpStep], availability: Availability, current: int | None) -> None
        # one row per step: QLabel plus QPushButton "Start" (objectName f"help_step_{action_id.replace('.', '_')}") plus a "How?" link
    topic: str                                     # read by tests and the usability driver
```
`_on_link` behaviour:
- `help:x` calls `show_page`, through a callback the window injects.
- `action:x` emits `action_requested`.

`Availability` is reused from `next_steps.py:13`.

**`main_window.py`:**
- Add three rows to `_FILE_ACTIONS` (`:154`), before About:
  ```python
  ("help.getting_started", "Getting Started", "Help", None, "The scan-to-STEP path in six steps; each step's button starts its tool."),
  ("help.context", "Help for This Tool", "Help", "F1", "How to use the open tool; Getting Started when none is open."),
  ("help.mouse_keys", "Mouse and Keys", "Help", None, "Mouse buttons, the open tool's keys and every shortcut."),
  ```
  Write "and", not "&": `&` is a mnemonic in a `QAction`.
- `_dispatch_framework_action` (`:382`): `help.getting_started` calls `show_help("getting_started")`; `help.context` calls `show_help()`; `help.mouse_keys` calls `show_mouse_keys()`. The busy guard covers only `file.*`, so help stays available while a job runs.
- New methods:
  ```python
  def show_help(self, topic: str | None = None) -> bool         # topic or self._help_topic(); lazily creates self.help_window, show(), raise_()
  def show_mouse_keys(self) -> bool                              # NAVIGATION + section(page(tool), "Mouse & keys") + a shortcut table from self._framework_actions.definitions
  def _help_topic(self) -> str                                   # topic_for(self.composition.modeling_controller.tool, self.tool_modes.state.id if self.tool_modes.active else None)
  def _action_availability(self, action_id: str) -> tuple[bool, str]   # lifted from the closure at :984-989 and reused there
  def _run_help_action(self, action_id: str) -> None             # QTimer.singleShot(0, lambda: (self._invoke_from_ui(action_id), self.activateWindow(), self._focus_viewport()))
  ```
- The `current` step: START→0, SCAN→2, CURVES→2, MODEL→3, CLOSE→3, EXPORT→4.

**`surfacing_panel.py`:**
- Header (`:130-133`): `self.help_button = QToolButton(); setText("?"); setObjectName("tool_help_button"); clicked -> self._emit("help.context")`. Create it before `_keep_hotkeys_working`, so it gets `NoFocus`.
- `show_session` (`:177`): `self.help_button.setToolTip(f"How to use {facts.title} (F1)")`.

**`surfacing_workbench.py`:**
- `_on_surfacing_action` (`:133`): `if action_id.startswith("help."): self._dispatch_framework_action(action_id, payload or None); return`.
- Lift the Enter dict at `:185-194` into a module constant `ENTER_ACTIONS: dict[str, str]`, so a test can check each page's Enter row against it.

**`guidance.py`:** add `GuidanceStep("help.getting_started", "How it works (6 steps)", ...)` to the START and SCAN stages. It is not primary.

**Unchanged:** no action enters `workflow_service`, there is nothing to undo or persist, and there are no viewport changes.

### H-06

**`cad_kernel/surfacing.py`:**
```python
def free_edge_indices(shape: Any) -> list[int]:
    """0-based, in shape_edges order: edges with exactly one adjacent face (seams count twice, degenerated edges skipped)."""
```
Use `TopExp.MapShapes_s(shape, TopAbs_EDGE, map)` and `TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, owners)`, then keep the edges where `owners.FindFromKey(e).Size() == 1`.

**`cad_kernel/jobs.py`:**
- `sew` (`:301`): add `free_edge_indices=[] if result.solid else S.free_edge_indices(result.shape)`.
- Also add `shells=` (the number of shells), for the case "no free edges, but not one body".

**`modeling/document.py`:**
- Add `"free_edge_indices"` and `"shells"` to the key list at `:201`.
- Add:
  ```python
  @property
  def open_edges(self) -> list[int]:   # ModelEntity; [] unless kind == "shell"
  def closure_text(entity: ModelEntity, units: str) -> str
  ```
- `closure_text` gives:
  - solid: "Closed solid: volume V units^3. Compare it with the scan, then Export."
  - shell with N open edges: "Not closed yet: N edge(s) have no neighbouring face (red). Fit the missing face there, or extend the surface that stops short, then Trim again." N is `len(free_edge_indices)`, or `free_edges` for old projects.
  - shell with no open edges: "The faces close, but not into one body (S pieces): look for a duplicate or overlapping surface, then Trim again."
- `KIND_LABELS` (`:46`): keep "Shell" unless the owner decides otherwise (decision 4).

**`application/modeling_controller.py`:**
- `ToolSession` (near `:84`): add `trim_result: str = ""` and `trim_replaces: tuple[str, ...] = ()`.
- `def _trim_sources(self) -> tuple[tuple[str, ...], tuple[str, ...]]` returns (visible surfaces that are not bodies, plus the hidden sources of each visible `kind == "shell"` entity) and those shells' ids.
  - Read the shell's sources from `entity.params.get("sources")`, falling back to `entity.sources`. Drop ids that no longer exist.
  - Use it at `:193`, `:234`, and at the end of `trim_apply`.
- `trim_compute` (`:1601`) and `trim_start_cut`: set `session.trim_result = ""`.
- `trim_apply` (`:1701`):
  - `status = closure_text(body, self.state.units)` replaces `:1730-1733`. The sew=False case keeps "N trimmed surfaces".
  - Hide `session.trim_replaces` next to `:1744-1746`.
  - Set `session.trim_result = status`, then recompute `trim_sources`/`trim_replaces`.
  - Undo is unchanged: one `_changed` snapshot.
- `export` (`:1851`): add a warning for each open shell in the targets.

**`viewer/modeling_scene.py`:**
- `OPEN_EDGE_COLOR = (1.0, 0.22, 0.16)`.
- New `ModelingSceneInput` field `show_open_edges: bool = True` (where a toggle would plug in).
- In the entity loop (`:116-139`), when the entity is visible, not being trimmed, and has `open_edges`:
  - Leave those indices out of the `model-edges:` item, so the red and yellow lines are never drawn on top of each other.
  - Add `ModelEdgesRenderItem(id=f"model-open:{entity.id}", revision=hash((token, tuple(open))), polylines=..., style=DisplayStyleSnapshot(color=OPEN_EDGE_COLOR, line_width=4.0), selection_keys=(node,))`.

**Picking:**
- `_model_node_for_actor` (`main_window.py:1669`): accept the kind `"model-open"`.
- `_fill_pick` (`surfacing_workbench.py:1215`): accept the prefix `"model-open:"`, so Fill can take the red edges.

**Panel (`surfacing_workbench.py:1309-1321`, `surfacing_panel.py:955-1020`):**
- `trim_text = session.trim_result` when there are no pieces and a result exists.
- `facts.extra["open_bounds"]` gives the bounds of the selected open body's red polylines.
- New `self.trim_show_gaps = _button("Show the gaps")`, visible when those bounds exist. It emits `"view.frame_gaps"`. `_on_surfacing_action` handles that inline: `self._camera_request = CameraRequest.frame_bounds(bounds); self.refresh()`, using `CameraRequest.frame_bounds` from `scene_types.py:480`.

**Inspector (`surfacing_workbench.py:1683`):**
- Add read-only rows "Status" and "To close it", both short.
- `widgets.py:341`: `label.setWordWrap(True)` for read-only fields.

**Tree (`surfacing_workbench.py:1536-1546`):** append " (not closed)" when `entity.open_edges`.

**`guidance.py:60`:** solids are `kind == "solid"`; open bodies are visible shells. Add `Stage.CLOSE`: title "Close the gaps", explanation `closure_text(...)`, steps Fit Surface (primary), Extend, Trim.

**Persistence:** none needed. The stats lists go through `_plain`. Old projects have no indices, so they show no red until the next Trim.

## 4. Tests

### Kernel and controller (no Qt)

- **`tests/test_re_surfacing.py`:**
  - `test_free_edges_outline_the_missing_face_of_a_box`: `BRepPrimAPI_MakeBox`, remove each face in turn; 4 indices; the polylines from `jobs.shape_edges` lie on the removed face's plane.
  - `test_a_cylinder_seam_is_not_an_open_edge`.
  - `test_a_solid_has_none`.
- **`tests/test_re_kernel_worker.py`:** `jobs.sew(...)["free_edge_indices"]` lines up with `["edges"]`.
- **New `tests/test_open_edges.py`**, using the verified cube fixture: six 14 mm `gp_Ax3` planes, 2,400 scan points, an inline worker, `_install` as in `test_surfacing_workflow.py:36`.
  - With five planes, `model.trim` → `model.trim_compute` → `model.trim_apply` gives a status starting "Not closed yet: 4 edges"; `len(stats["free_edge_indices"]) == 4`; a `model-open:` item with 4 polylines in `OPEN_EDGE_COLOR`, and an ordinary item with 8.
  - Add the sixth plane, then `model.trim`: `trim_sources` holds the 5 hidden planes plus the new one. Apply gives a status starting "Closed solid", volume 1000 ± 1; the old shell is hidden.
  - `edit.undo` makes the shell visible again with its red edges.
  - `model_to_dict`/`model_from_dict` keeps the indices.
  - Guidance gives `Stage.CLOSE` for the shell and `Stage.EXPORT` for the solid.
  - Exporting the shell gives a warning.
- **New `tests/test_help.py`:**
  - Every `TOOL_ACTIONS` topic has a page with `## Steps` and `## Mouse & keys`.
  - Every `action:` link is a registered id: core registry plus the window's `_FILE_ACTIONS`.
  - Every `help:` link resolves.
  - `topic_for("section", "modeling") == "section"` and `topic_for(None, "section") == "section_plane"`.
  - `GETTING_STARTED` has 6 distinct ids that are all registered.
  - For each tool in `ENTER_ACTIONS`, its page's Enter row names that action's label.

### Window-level (offscreen; call `set_project_dirty(False)` before `close`)

- F1 through `QTest.keyClick(window.viewport.interactor, Qt.Key_F1)`:
  - With no tool open: `help_window.isVisible()` and `topic == "getting_started"`.
  - After `_invoke_from_ui("model.trim")`: topic `"trim"`, and the browser text contains "Trim Surfaces".
- `QTest.mouseClick(window.surfacing_panel.help_button, Qt.LeftButton)` gives the same result.
- The region tool's F1 gives `"region"`.
- Getting Started's `help_step_model_fit_surface` click (after a scan is installed): `modeling.tool == "fit_surface"` and `active_workspace == "surface"`.
- Mouse and Keys contains "Ctrl+K" and the trim rows; a shortcut changed through `settings.future["shortcuts"]` shows the new key.
- The Help menu lists 4 entries. The existing `test_no_shortcut_is_bound_to_two_actions` (`test_ux_action_help.py:152`) catches F1 clashes. `test_every_action_has_a_description_and_tooltip` covers the new rows.
- H-06 in the window (cube fixture): click the panel's Apply. Then `trim_info.text()` starts "Not closed yet"; `modeling_items(window._modeling_scene_input(), ...)` has `model-open:`; "Show the gaps" is visible and sets a `FRAME_BOUNDS` camera request; the inspector shows "Open edges".

### Real window with real input (`scripts/usability`)

- `human.py`: add `help_text()` (returns `w.help_window.browser.toPlainText()`) and `click_help(object_name)`.
- New `h05_help.py`:
  - F1 at start (log and screenshot).
  - Click each Getting Started Start button in order, using `stand_in_file_dialogs` and `answer_dialog(choice="mm")` for the bracket STL.
  - At step 3, fit faces with the s2 loop.
  - In Trim, F1 then "?".
  - Mouse and Keys.
  - Screenshot every page.
  - Confirm each Start opened its tool and switched workspace.
- New `trim_gap.py`, or a flag on `s2_surface_bracket.py`:
  - Bracket with face 9 skipped. Trim, then Apply: log the status and panel text (expect 16 open edges) and take a view screenshot of the red edges.
  - Click "Show the gaps" and screenshot.
  - Fit face 9, then Trim and Apply: expect "Closed solid".
- The newcomer acceptance ("reaches Export from Getting Started alone") still needs a hallway test with a person. Record it in `HUMAN_AUDIT.md`.

## 5. Risks, edge cases and owner decisions

**Risks and edge cases:**
- **Hidden red edges.** Edge actors share the depth pull `MODEL_EDGE_DEPTH_PULL` (`model_actors.py:16`). Leaving the open edges out of the ordinary item prevents red and yellow lines fighting at the same depth. From some angles the gap edges can still hide behind faces; "Show the gaps" handles that. Drawing them always on top would be a later change.
- **Counts can disagree.** `NbFreeEdges` and the computed indices matched on the box and the bracket, but they could differ with several shells or with edges shared by three or more faces (`NbMultipleEdges` warning at `surfacing.py:737`, a sign of a duplicate surface; see H-13). Show `len(indices)` when present. The "faces close, not one body" message covers several closed shells.
- **What Trim again pulls in.** Any visible open shell's hidden sources join the next Trim, including an unrelated open shell left visible.
- **Manual drops are lost.** Pieces dropped by hand in the earlier trim are not replayed.
- **Cut lines are already lost (existing bug).** `trim_apply` clears `session.trim_cuts` at `:1710` before it builds `params["cuts"]`, so saved cut lines are always empty. Fix it in the same change or note it.
- **Old projects** show no red edges until the person trims again.
- **Packaging.** If `package-data` is left out, F1 raises from `page()` in an installed build. Add a test that `page()` reads every topic, and build a wheel once in a temporary copy to check both the `.md` files and the SVGs.
- **Pages drifting from code.** Pages are written by hand. The tests check structure, links and the Enter row only. Empty-text action links render the live label and shortcut.
- **Workspace switching (existing gap).** The palette and Next steps do not switch workspace. Getting Started uses `_invoke_from_ui`. Fixing the other two is out of scope.
- **Focus.** The Help window takes keyboard focus. `_run_help_action` must give it back to the 3D view, or Enter and Esc go to the dialog.

**Decisions for the product owner:**
1. **Floating Help window or a dock?** The design uses a non-modal window: one class, no saved-layout effects, and it can go on a second monitor. A dock tabbed with Properties would hide the tool panel while reading.
2. **Open-edge highlight:** always on while the open body is visible, or a toggle (View > Show Open Edges, setting `show_open_edges`)? The design uses always on: it marks a defect, not a view preference.
3. **"Trim again" includes the open body's sources.** The alternative is a message saying "Undo (Ctrl+Z), fit the missing face, Trim again": no code, but awkward. The design includes the sources.
4. **Wording:** keep "Shell" in the tree and Type, or say "Open body" (UX-08)? The design keeps "Shell" with "(not closed)" added.
5. **Highlight colour:** red. Magenta, the Rhino-style choice, is already taken by Fill's picked edges.
6. **Getting Started step 2:** "Check its size" (catches wrong units for a newcomer) or "Save the project"?
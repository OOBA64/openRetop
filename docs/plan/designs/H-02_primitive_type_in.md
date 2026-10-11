# H-02: Edit Primitive (Type In and constraints for fitted primitives)

**Short answer:** this is buildable with a small set of changes. Nothing exists today: no primitive can be retyped or constrained after Create, and the fitted axis and radius survive only inside the BREP. The design adds:
- one fitting module (`fitting/constrained.py`);
- one pure helper module (`modeling/primitive_edit.py`);
- two kernel jobs;
- one tool session, one panel page and four actions.

Apply is one undo step and keeps the face where it is.

**Checked:** I prototyped the constrained fits and the face re-hosting in throwaway scripts outside the repo, on the bracket and shaft benchmark scans. No repository file was changed. I did not write the new modules or run the existing test suite.

**Line numbers** are at HEAD 233d271. Another task (H-03) is editing `surfacing.py` (+62 lines after line 165), `jobs.py`, `modeling_controller.py` (+14 lines after 56 and 405), `surfacing_workbench.py` and `modeling_scene.py` in this worktree, uncommitted. This design does not depend on H-03 except the fallback path; rebase on H-03 before starting.

---

## 1. What exists today, and the gaps

**Fitting** (`fitting/primitives.py`)
- `fit_primitive(kind: str, points: object, normals: object | None = None, *, outlier_tolerance: float | None = None) -> PrimitiveFit` (:72).
- Parameter dicts per kind:
  - plane `{normal, point, offset}` (:310)
  - sphere `{center, radius}` (:337)
  - cylinder `{axis, point, radius}` (:398)
  - cone `{apex, axis, half_angle_degrees}` (:462)
  - torus `{center, axis, major_radius, minor_radius}` (:528)
- Axes are flipped into the positive half-space by `_canonical_axis` (:272).
- `_robust(kind, points, normals, min_points, initial_and_refine, distance, outlier_tolerance) -> PrimitiveFit` (:169) works with any `initial_and_refine(points, normals, previous) -> params | None` closure. It subsamples to 3,000 points, trims outliers over 3 rounds, then refines on up to 20,000. A constrained fitter can plug straight into it.
- `primitive_distance(fit: PrimitiveFit, points: object) -> np.ndarray` (:131, via `_DISTANCES` :554) is numpy only. It is enough for a live deviation readout.
- The cylinder solver's unknowns are `[theta, phi, du, dv, r]` (:357-398). Fixing one means dropping its column.
- **Gap:** there is no constraint support at all (RE-06 todo, TASKS.md:69).

**Prototype results** (B1 bracket R4 plate hole, 0.02 mm noise, normals from `vertex_normals`):

| Case | Result | Time |
|---|---|---|
| Free fit | R 4.0001, axis 0.06° off Z | 5 ms |
| Scan tilted 0.4°, axis forced to Z | RMS 0.044 (free 0.018) | 1 ms |
| Radius typed 3.9 | RMS 0.116 | — |
| B2 shaft turned onto X, axis forced perpendicular to Z (5,195 points) | RMS 0.055 | 5 ms |
| Same hole without normals | R 2.93, RMS 1.02 (fails) | — |

Constrained fits must therefore get the scan normals too.

**How a primitive is stored** (the main gap)
- `jobs.fit_surface` (`cad_kernel/jobs.py:92`) returns `"params": _plain_params(primitive.params)` (:145).
- Its `rms` and `max_error` are over **all** selected points, not just inliers (:144, :148-149).
- `entity_from_result(document, result, *, tool, params=None, sources=(), name=None) -> ModelEntity` (`modeling/document.py:186`) keeps only the stats on its whitelist (:201) plus the caller's params, so `result["params"]` is dropped.
- `create_from_preview` (`modeling_controller.py:418`) stores `{kind, control_u, control_v, smoothness, expand, triangles}` (:428-435). `triangles` are display-mesh triangle ids.
- After Create, the fitted axis and radius exist only in the BREP. The scan points survive only as display-triangle ids, which go stale when the display proxy is rebuilt (`main_window.py:1409-1425`).
- `extend` replaces params with `{"distance": length}` (`modeling_controller.py:1521`), so the triangle ids are lost after Extend. `resize_surface` keeps params (:1590).
- Persistence writes `params` and `stats` through `_plain` (`persistence.py:45-58`, :78-79), so new keys persist with no format change.

**Face construction and extent**
- `primitive_patch(fit: PrimitiveFit, points: object, expand: float = 0.15) -> object` (`surfacing.py:160`; H-03 adds `reach=`) calls `primitive_face(fit: PrimitiveFit, center: np.ndarray, extent: float) -> object` (`primitive_solid.py:48`):
  - plane: a square of ±1.5·extent on OpenCASCADE's default axes (:65-69; H-03 replaces this with a rectangle turned to the face);
  - cylinder: a full turn (u from 0 to 2π) and v of ±half around the projected bounding-box centre (:70-75);
  - cone: v from 0 to `reach`, measured from the apex, reference radius 0 (:76-81);
  - sphere and torus: whole (:82-87).
- Existing helpers:
  - `_basis_and_bounds(face) -> (surface, basis, (u0, u1, v0, v1))` (:330);
  - `face_handles(face, samples=33) -> dict` with its "rectangular" test (:377-388);
  - `resize_face(face: Any, changes: dict[str, float]) -> object` (:440-486) rebuilds with `BRepBuilderAPI_MakeFace(basis, u0, u1, v0, v1, 1e-7)` and clamps a cone's v0 at 0 (:481-482).
- **Keeping the extent therefore means:** build the new analytic surface on the old frame (turned and moved), with the **same UV bounds**. Prototype: a cylinder re-hosted onto axis Z with the old bounds kept its area (402.985 vs 402.996), and `face_handles` still reports it as rectangular.

**Replacing an entity with one undo step**
- `resize_surface(self, entity_id: str, changes: dict[str, float]) -> CommandResult` (`modeling_controller.py:1575-1599`) shows the pattern:
  - kernel call;
  - `before = model.snapshot()`;
  - copy id, name, colour, visible and kind onto the new entity;
  - `model.revision += 1`;
  - `_changed(self, name: str, before: Any, status: str) -> CommandResult` (:2281), which makes one `CallbackUndoPayload`.
- The arrow cache is keyed by `id(entity.brep)` (:1556).
- `replace_entity(model, entity_id, result, *, tool, params) -> ModelEntity` (`regeneration.py:143`) does the same in-place swap and keeps name, colour, visible and sources.
- Precedent for "open an existing entity in a tool, and the tool's Create replaces it": `section_edit_entity` and `session.section_editing` (:666-691, :636-662).
- `KernelWorker.call(name, *args, timeout=None, **kwargs) -> KernelReply(ok, value, error, crashed, timed_out, seconds)` (`worker.py:86`, :32).

**Deviation today**
- Fit stats come from `primitive_distance` over the selection.
- Compare uses the kernel `deviation` job over the display vertices (`modeling_controller.py:1754-1773`, `jobs.py:317-323`).
- Neither scores a candidate before Apply. `primitive_distance` on the stored points is enough (milliseconds).

**UI plumbing**
- Panel: one page per tool (`surfacing_panel.py:45` PAGES, :141-159 builders), painted by `show_session` (:174-233) with signals blocked for the widgets listed in `_inputs()` (:402-432). Controls emit `model.configure`.
- Live-preview precedent: a configure change dispatches `model.extrude_preview` (`surfacing_workbench.py:140-141`). Heavy actions run in the background and are **dropped while it is busy** (`main_window.py:452-457`, :1353-1355).
- `session.preview` is drawn for any tool (`modeling_scene.py:179-198`, fed at `surfacing_workbench.py:1273`). The scan-selection overlay is drawn only for Fit Surface (:1244).
- Entry points:
  - Tree rows carry context actions in node metadata (`surfacing_workbench.py:1532-1542` → `widgets.py:168-189` → `main_window.py:583-587`).
  - The viewport only emits `double_click` when it has a capture owner (`viewport.py:454-457`). With no tool open and one surface selected, the owner is `"surface_handles"` (`surfacing_workbench.py:781-785`).
  - But `_surfacing_pointer` returns False when there is no session (:812-813), and the window ignores anything but a release (`main_window.py:660`). **A double-click on a surface does nothing today.**
- The panel has no `QComboBox` yet. `_keep_hotkeys_working` (:162-170) only takes focus away from buttons, checkboxes, sliders and lists. The window passes keys to a focused combo (`main_window.py:709`), so **a combo would swallow Enter**.
- Enter in a number box is consumed by `_field_enter` (`surfacing_workbench.py:108-120`, `main_window.py:705-708`): the first Enter commits the value, the second runs the tool. Keep that.
- Architecture rule: no new `*_controller.py` file is allowed (`tests/test_architecture.py:64-79`).

---

## 2. User flow

**Ways in**
- Double-click a fitted plane, cylinder, cone or sphere in the view (the Design X habit).
- Right-click its row in the Model tree and choose "Model · Edit Primitive".
- With one primitive selected: the Surface toolbar "Edit Primitive" button (after Fit Surface), or Ctrl+K "Edit Primitive".
- When disabled, the tooltip says: "Select one fitted plane, cylinder, cone or sphere."

**Panel: "Edit Primitive — Cylinder 2"**
- One hint line: "Type a value or pick a constraint; deviation updates. Enter applies, Esc cancels."
- The scan area the primitive was fitted to shows in the orange selection colour.
- The original face is replaced by the cyan preview once anything changes.

**Cylinder** (cone and sphere work the same way)
1. **Define by:** Best fit | Type in.
2. **Radius:** `[4.0001]` ☐ Fixed `[Round]` step `[0.01 ▾]`, with a "Ø 8.0002" readout (or the linked Ø box from decision 1).
   - Typing 4 and pressing Enter ticks Fixed, refits the axis and position with the radius held, and updates the deviation.
   - Round snaps to the step and ticks Fixed.
   - A cone has Half-angle (degrees) here instead.
3. **Axis:** `[Free | Parallel to | Perpendicular to | Coaxial with]` of `[reference ▾]`.
   - References: World X/Y/Z axes, World XY/XZ/YZ planes, other fitted planes, cylinder and cone axes, and sketch planes.
   - Clicking another surface in the view while the tool is open makes it the reference.
4. **Readout:** "Axis (0.0000, 0.0000, 1.0000) through (-25.000, 0.000, 0.000); 0.000° to Plane 1's normal".
5. **Deviation:** "Fitted: RMS 0.018, max 0.052 mm / Now: RMS 0.019, max 0.053 mm (4,212 scan points)". It turns red with "over the 0.05 mm tolerance" when Now RMS exceeds `session.fit.tolerance`.
6. **Buttons:** `[Reset]` `[Apply]` (primary).
   - Enter applies. Enter inside a number box commits; the next Enter applies.
   - Esc or Done cancels with no change.
   - Apply closes the tool and keeps the surface selected, so the resize arrows return.
   - Status after Apply: "Cylinder 2: R 4.000, axis ⟂ Plane 1; RMS 0.019 mm (was 0.018)".
   - Ctrl+Z undoes the whole edit; Ctrl+Y redoes it.

**Plane:** Define by `[Best fit | Type in | Offset from plane | Middle of two planes]`
- **Best fit:** Normal `[Free | Parallel to | Perpendicular to]` of `[reference]`; the plane is refitted with that normal.
- **Type in:** Point X/Y/Z and Normal X/Y/Z (VectorEditor).
- **Offset from:** `[Plane 1 ▾]` and a distance `[5.000]`, signed along that plane's normal and prefilled with the measured distance.
- **Middle of:** `[Plane A ▾]` `[Plane B ▾]`.
- Readout: distance and angle to the reference(s).

**What the relations mean** (CAD convention, so "hole axis perpendicular to the base" means what it says):

| feature | relation | reference | rule |
|---|---|---|---|
| axis | parallel | axis | axis ∥ d_ref |
| axis | perpendicular | axis | axis ⟂ d_ref |
| axis | parallel | plane | axis ⟂ n_ref |
| axis | perpendicular | plane | axis ∥ n_ref |
| axis | coaxial | axis | axis line = reference line |
| plane | parallel | plane | n ∥ n_ref |
| plane | perpendicular | plane | n ⟂ n_ref |
| plane | parallel | axis | n ⟂ d_ref |
| plane | perpendicular | axis | n ∥ d_ref |

**For a newcomer:** following your one-line-on-hover idea, every control gets a tooltip of 64 characters or fewer (H-10 already wraps tooltips), and there are no extra paragraphs. Examples:
- Fixed: "Keep this radius; the axis is refitted to the scan."
- Round: "Snap to the nearest step and keep it."
- Coaxial: "Same axis line as the reference; only the radius is fitted."

---

## 3. Data and code changes

### 3.1 New module `src/openretop/fitting/constrained.py`

Numpy/scipy only. It reuses `_robust`, `_least_squares` (:232), `_basis` (:282), `_circle_2d` and `_DISTANCES`, and is exported from `fitting/__init__.py`.

```python
@dataclass(frozen=True)
class FitConstraints:
    radius: float = 0.0                 # > 0 fixes a cylinder or sphere radius
    half_angle_degrees: float = 0.0     # > 0 fixes a cone half-angle
    direction: tuple[float, float, float] | None = None         # axis / plane normal fixed
    perpendicular_to: tuple[float, float, float] | None = None  # axis / normal perpendicular to this
    axis_point: tuple[float, float, float] | None = None        # with direction: the axis line is fixed (coaxial)

def fit_constrained(kind: str, points: object, normals: object | None, constraints: FitConstraints, *,
                    start: dict[str, object] | None = None, outlier_tolerance: float | None = None) -> PrimitiveFit
```

- **No constraints:** call `fit_primitive`.
- **Plane:**
  - fixed normal d: n = d (keeping the start's sign), point = centroid of the inliers (closed form);
  - normal perpendicular to d: the smallest singular vector of the centred points projected onto the plane perpendicular to d (closed form).
- **Cylinder:**
  - coaxial: radius = mean radial distance, or nothing left to fit;
  - fixed direction: a 2-D circle fit (Kasa start, then Levenberg-Marquardt on the centre, plus the radius if free);
  - perpendicular to d: axis = cos t·e1 + sin t·e2 on `_basis(d)`, solving for (t, du, dv, and r if free);
  - radius only: the existing solver with the radius column removed.
- **Cone:** the same pattern on `[apex, theta, phi, half]` for a fixed half-angle, fixed direction, perpendicular, or coaxial.
- **Sphere:** fixed radius, solving for the centre only.
- **Torus or degenerate input:** return `PrimitiveFit(kind, False, reason=...)`. It never raises.
- **Start values:** `start` projected onto the constraint (for example the axis projected onto the plane perpendicular to d, sign kept), passed as `previous` on the first round.

### 3.2 New module `src/openretop/modeling/primitive_edit.py`

Pure Python and numpy, no Qt or OpenCASCADE.

```python
EDITABLE_KINDS = ("plane", "cylinder", "cone", "sphere")
MODES = {"plane": ("fit", "type_in", "offset", "middle"), "cylinder": ("fit", "type_in"),
         "cone": ("fit", "type_in"), "sphere": ("fit", "type_in")}
RELATIONS = ("free", "parallel", "perpendicular", "coaxial")

@dataclass(frozen=True)
class Reference:
    id: str; label: str; kind: str            # "axis" | "plane"
    direction: np.ndarray; point: np.ndarray

@dataclass
class PrimitiveEdit:                           # tool state; only Apply is undoable
    entity_id: str; kind: str; brep_id: int
    original: dict[str, Any]                   # params as fitted (Reset goes back here)
    points: np.ndarray; normals: np.ndarray | None; mask: np.ndarray | None
    point_source: str = "selection"            # or "nearby" (fallback)
    mode: str = "fit"
    value: float = 0.0; value_fixed: bool = False   # radius, or cone half-angle
    step: float = 0.01
    relation: str = "free"; reference: str = ""
    offset_reference: str = ""; offset: float = 0.0
    middle_a: str = ""; middle_b: str = ""
    point: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    direction: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    before: tuple[float, float] = (math.nan, math.nan)
    revision: int = 0
    def to_dict(self) -> dict[str, Any]: ...       # saved as entity.params["edit"]
    def restore(self, data: dict[str, Any]) -> None: ...

def references(entities: Sequence[Any], exclude: str) -> list[Reference]
def direction_constraint(feature: str, relation: str, reference: Reference) -> FitConstraints   # the table in section 2
def plane_offset(reference: Reference, distance: float) -> dict[str, Any]
def plane_middle(a: Reference, b: Reference) -> dict[str, Any]     # parallel: mid-plane; otherwise the bisector
def solve(edit: PrimitiveEdit, refs: Mapping[str, Reference]) -> tuple[dict[str, Any] | None, str]
def measure(kind: str, params: dict[str, Any], points: np.ndarray) -> tuple[float, float]   # rms, max of |distance| over ALL points, as jobs.fit_surface
def round_to(value: float, step: float) -> float
def describe(params: dict[str, Any]) -> str      # "R 4.000 fixed; axis ⟂ Plane 1" for Properties
```

`references()` lists the World X/Y/Z axes and XY/XZ/YZ planes first. It then adds every entity with `params["primitive"]`: a plane becomes a plane reference; a cylinder, cone or torus becomes an axis reference. Sketch profiles become planes from `params["frame"]` (normal = u × v).

### 3.3 Kernel

Add to `cad_kernel/surfacing.py` and its `__all__`:

```python
def primitive_params(face: Any) -> tuple[str, dict[str, Any]]   # kind + params read from the Geom surface (for older entities)
def replace_primitive(face: Any, kind: str, params: dict[str, Any]) -> object
```

`replace_primitive`:
1. Read `_surface, basis, bounds = _basis_and_bounds(face)`. Refuse unless the surface is analytic and `face_handles(face)["rectangular"]` is true.
2. Find the face's middle M: `basis.Value(um, vm)`, or the axis point at vm for a cylinder or cone.
3. Turn the old frame by the smallest rotation from its main direction to the new one. First flip the new direction to match the old sign: the trim and solid steps rely on which side a plane faces.
4. Move the frame so M lands on its projection onto the new plane or axis.
5. Keep the UV bounds. Cone: remap v so the axial positions stay the same under the new apex and half-angle, with v0 ≥ 0 (as :481-482). Sphere: clamp v to ±π/2.
6. Build with `BRepBuilderAPI_MakeFace(new_surface, u0, u1, v0, v1, 1e-7)`.

Add two jobs to `cad_kernel/jobs.py` and to `JOBS` (:464):

```python
def primitive_info(brep: bytes) -> dict[str, Any]       # {"kind", "params", "rectangular", "bounds"}
def edit_primitive(brep: bytes, kind: str, params: dict[str, Any]) -> dict[str, Any]
    # surface_result(S.replace_primitive(face, kind, params), kind=kind, params=_plain_params(params))
```

### 3.4 Controller (`application/modeling_controller.py`)

**Changes to existing code**
- `TOOLS` (:40): add `"edit_primitive"`. `TOOL_TITLES` (:43): `"Edit Primitive"`. Add a hint in `start` (:267-278).
- `ToolSession` (:70): add `primitive: PrimitiveEdit | None = None`.
- `configure` (:290):
  - add `"primitive"` to the protected names (:300-304);
  - add a `primitive_` branch like the `fit_` one (:298): set `session.primitive.<name>`, cast to the field's type (lists for vectors), then `revision += 1` and `session.preview = None`;
  - setting `primitive_value` also sets `value_fixed = True`.
- `create_from_preview` (:428-435): also store `"primitive": result.get("params") or {}` and `"display_triangles": len(display.triangles)`.
- `extend` (:1521): use `params={**target.params, "distance": length}` so Edit Primitive still finds its points after Extend.
- `discard_stale` (:177): close an edit session whose entity is gone, or whose `id(entity.brep)` no longer matches `edit.brep_id`.

**New methods**

```python
def editable_primitive(self, entity: ModelEntity | None) -> bool
def primitive_edit_start(self, entity_id: str | None = None) -> CommandResult
def primitive_preview(self) -> CommandResult
def primitive_reset(self) -> CommandResult
def primitive_apply(self) -> CommandResult
def _primitive_points(self, entity: ModelEntity, params: dict[str, Any]) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None, str]
```

`primitive_edit_start`
1. Take one selected editable entity.
2. Use `params = entity.params.get("primitive")`. If missing, call `worker.call("primitive_info", entity.brep)` and cache the result into `entity.params`; it is derived data.
3. Find the points (`_primitive_points`):
   - If `display_triangles` matches the current display mesh (for older entities: all ids are in range), build a mask from `params["triangles"]` and call `_selected_scan_data(self, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]` (:2315). That gives world points and normals.
   - Otherwise use the "nearby" fallback: source vertices within `max(4·stats rms, 2·_scan_spacing())` (:1398) of the primitive, inside the entity's bounding box grown by that band.
4. Call `self.start("edit_primitive")`, fill a `PrimitiveEdit`, restore `entity.params.get("edit")`, and set `before = measure(original)`. That equals `entity.stats` to 1e-9 when the points are the original selection.

`primitive_preview`
1. `solve` (numpy), then `measure`.
2. Call `worker.call("edit_primitive", entity.brep, kind, params)`.
3. Store `session.preview = {**reply.value, "rms", "max_error", "revision": edit.revision, "primitive": params}`.
4. If the fit or the kernel fails, return the reason as a failure but keep the numbers.

`primitive_apply`
1. Run the preview if there is none or it is out of date. If nothing changed, return `ok("Nothing to change")`.
2. `before = model.snapshot()`.
3. `replace_entity(model, id, preview, tool=entity.tool, params={**entity.params, "primitive": params, "edit": edit.to_dict()})`, keeping the kind.
4. `model.selected_ids = [id]`, `model.revision += 1`, `self.session = None`.
5. If any entity has this one in its `sources`, add the warning "Solid 1 was made from it: trim again to update it".
6. `return self._changed(f"Edit {name}", before, status)`.

`primitive_reset` puts the fields back to the original values and clears the preview.

### 3.5 Actions and dispatch

In `application/actions.py`, next to `model.section_edit` (:543), using `_workflow_action(action_id, label, category, legacy_handler, *, enabled_when, visible_when, shortcut=None, description=None, **metadata)` (:381):

```python
_workflow_action("model.edit_primitive", "Edit Primitive", "Surfacing", "primitive_edit_start", enabled_when=(ActionCondition.HAS_MODEL_SELECTION, ActionCondition.NOT_BUSY)),
_workflow_action("model.primitive_preview", "Preview Primitive", "Surfacing", "primitive_preview", enabled_when=(ActionCondition.MODEL_TOOL_ACTIVE, ActionCondition.NOT_BUSY), visible_when=(ActionCondition.MODEL_TOOL_ACTIVE,)),
_workflow_action("model.primitive_reset", "Reset Primitive", "Surfacing", "primitive_reset", ...same conditions...),
_workflow_action("model.primitive_apply", "Apply Primitive", "Surfacing", "primitive_apply", ...same conditions...),
```

Add to `_DESCRIPTIONS` (:350): `"model.edit_primitive": "Type exact values into a fitted plane, cylinder, cone or sphere, or constrain it to another feature; the scan deviation updates before you apply."`

In `application/workflow_service.py`, `_dispatch_model` (:343, beside `model.section_edit` :403): route the four ids to the four controller methods; the `entity` payload is optional.

### 3.6 Window glue (`presentation/qt/surfacing_workbench.py`)

- **Action sets:** add `model.edit_primitive` to `SURFACING_ACTIONS` (:27). Add `model.edit_primitive`, `model.primitive_preview` and `model.primitive_apply` to `SURFACING_HEAVY_ACTIONS` (:31). Add an `edit_primitive` entry to `TOOL_HINTS` (:74).
- **Live preview:** in `_on_surfacing_action` (:133), after a configure while the edit tool is open, call `_request_primitive_preview()`. If `self._executor.busy`, it retries with `QTimer.singleShot(80, …)`.
- **Tool mode:** in `_surfacing_tool_mode` (:147):
  - `model.primitive_apply` succeeded → `tool_modes.finish()`;
  - `model.primitive_preview` finished but `edit.revision != preview["revision"]` → request again.
- **Enter:** in `_surfacing_key` (:184-194), map `"edit_primitive"` to `"model.primitive_apply"`.
- **Pointer:** in `_surfacing_pointer` (:805):
  - before `if session is None: return False` (:812), handle `double_click`: `pick_scene_object` → `model_id_from_node` → if editable, dispatch `model.edit_primitive {"entity": id}`;
  - inside the tool, a click on another model surface calls `configure(primitive_reference=id)` and requests a preview.
- **Scene:** in `_modeling_scene_input` (:1241):
  - while editing, set `selection_mask = edit.mask`;
  - hide the edited entity once `session.preview` exists;
  - draw the preview's axis and the reference's through `sketch2d_lines` (`modeling_scene.py:80`, :167-178).
- **Panel facts:** in `_refresh_surfacing_panel` / `_sketch_facts` (:1339, :1357), set `extra = self._primitive_facts(session)`. It carries the references (id, label, kind), the numbers, readouts, `point_source` and `has_preview`.
- **Tree:** in `_surfacing_nodes` (:1532-1542), editable rows get `("model.edit_primitive", "view.frame_selected", "model.extend", "model.delete_selected", "file.export_model")`.
- **Properties:** in `_surfacing_inspector_fields` (:1660), add a read-only "Primitive" group: Radius / Ø, Axis, and Constraints from `describe`.

### 3.7 Panel (`presentation/qt/surfacing_panel.py`)

- Add `"edit_primitive"` to PAGES (:45) and `("edit_primitive", self._build_primitive)` to the builders (:141).
- Call `_show_primitive(session, facts)` from `show_session` (:174). Add the new widgets to `_inputs` (:402).
- Widget objectNames (used by tests and the usability driver):
  - mode and value: `primitive_mode`, `primitive_value`, `primitive_fixed`, `primitive_round`, `primitive_step`;
  - constraint: `primitive_relation`, `primitive_reference`;
  - Type in: `primitive_point`, `primitive_direction` (VectorEditor, `widgets.py:195`, `committed` signal);
  - plane modes: `primitive_offset_reference`, `primitive_offset`, `primitive_middle_a`, `primitive_middle_b`;
  - readouts: `primitive_readout`, `primitive_deviation`;
  - buttons: `primitive_reset`, `primitive_apply` (primary).
- Spin boxes use `setKeyboardTracking(False)`, so there is one preview per committed value, not per keystroke.
- Combos emit on `activated` and then emit `editing_done`, so the keyboard returns to the view and Enter applies.
- Rows are shown or hidden per kind and mode.

### 3.8 Toolbar, undo, persistence

- **Toolbar** (`main_window.py:353-361`): add `("model.edit_primitive", "fit_surface", "Edit Primitive", False)` after Fit Surface. The Surface row goes from 56 to 70 label characters; the budget in `tests/test_toolbar_icons.py:81-98` is 115.
- **Undo:** Apply is one undo step (`_changed`). Field changes are tool state, like the extrude options. Esc discards them.
- **Persistence:** `params["primitive"]`, `params["edit"]` and `params["display_triangles"]` persist through `_plain` with no format change.

---

## 4. Tests

**Unit: `tests/test_re_primitive_constraints.py`** (B1/B2 benchmarks, noise 0.02, normals from `vertex_normals`)
- R4 hole with radius fixed at 4.0: axis within 0.05° of Z, RMS within 10% of the free fit.
- Radius typed as 3.9: RMS > 0.08, still success.
- Scan tilted 0.4°, axis fixed to Z: axis exactly Z, RMS above the free fit.
- B2 turned onto X, axis perpendicular to Z: |axis·Z| < 1e-12, radius within 0.01.
- Boss hole coaxial with the boss: R 5 ± 0.01.
- Plane with fixed and with perpendicular normal; cone with fixed half-angle; sphere with fixed radius.
- Torus, two points, a zero direction: success False with a reason, no exception.

**Unit: `tests/test_primitive_edit.py`**
- The 9-row relation table.
- `plane_offset` and `plane_middle` (parallel and bisector, normal sign).
- `references`: world references first; excludes the entity itself, bodies, freeform and trimmed pieces; includes a sketch frame as a plane.
- `round_to`; `to_dict` / `restore` round trip.

**Kernel** (OpenCASCADE, in the style of `tests/test_surface_handles.py`)
- `primitive_params` round-trips `primitive_patch` for plane, cylinder, cone and sphere.
- `replace_primitive`:
  - keeps the UV bounds;
  - a cylinder going from R4 to R5 scales its area by 5/4;
  - a tilted axis keeps the face's middle in place (within 1e-9);
  - after `resize_face(v1=-3)` the edit keeps that v1;
  - keeps the plane normal's sign and the cone's axial positions;
  - refuses freeform and trimmed faces.

**Controller** (inline worker; `_composition_with("bracket")` from `tests/test_section_sketch.py:42`; faces picked by `scan.face_labels` as in `tests/test_surfacing_workflow.py:115`)
- Fit the base plane and the R4 hole, then dispatch `model.edit_primitive`.
- A preview with no change gives RMS equal to `stats["rms"]` (within 1e-9). This checks that the right scan points were recovered.
- Configure `primitive_value=4.0` and the axis perpendicular to the base plane, preview, then apply. Check:
  - same id, name and colour;
  - axis parallel to the plane normal (within 1e-9);
  - `params["primitive"]["radius"] == 4.0` and updated stats;
  - exactly one undo entry; undo restores the BREP and stats; redo works.
- Esc leaves the BREP object unchanged (`is`).
- Extend keeps `params["triangles"]`.
- Replacing the display mesh switches to `point_source == "nearby"` and says so.
- `model_to_dict` / `model_from_dict` keeps `primitive` and `edit`; reopening the editor restores the fields.
- Undoing the fit while the edit tool is open closes the tool.

**Window** (offscreen `OpenRetopV3Window`, as `tests/test_surface_handles.py:140`)
- The tree offers `model.edit_primitive` only on primitive rows.
- `_on_viewport_pointer("double_click", …)` with `pick_scene_object` patched to the cylinder opens the tool on the edit_primitive page; the radius row shows and the plane-only rows are hidden.
- `QTest.keyClicks` "4" plus Return in `primitive_value` sets `value_fixed`, and the status mentions RMS. A second Return applies, and `model.primitive_apply` closes the tool.
- Picking a reference in a combo hands focus back to the viewport, so Enter applies.
- Esc cancels. The toolbar width test still passes.

**Real window:** `scripts/usability/edit_primitive.py` plus a README row. Add `Human.double_click(x, y)` to `human.py`, sending `QEvent.MouseButtonDblClick` through `_send` (:169).
1. Open `scan_of("bracket")`, go to the Surface tab, start Fit Surface. In the top view, click the plate top and Create.
2. In the isometric view, click the far wall of the R4 hole (point = (-25, 0, 0) − 4 × the horizontal view direction, at z = +3), Create, Done.
3. Double-click the hole surface and take a screenshot.
4. Type 4 into `primitive_value` (QTest.keyClicks on its line edit, as in `s3_solid_housing.py:96-99`), press Return, and log the deviation.
5. Set Axis to Perpendicular to Plane 1. Log the readout and deviation; screenshot "before apply".
6. Press Enter and log the params. Press Ctrl+Z, then Ctrl+Y; log that the length along the axis is unchanged.

Expected: RMS stays near 0.02 mm, axis·Z = 1, one undo step.

---

## 5. Risks, edge cases and decisions

**Decisions for you**
1. **Radius or diameter.** The task says "typed radius (e.g. 8.00)", but the acceptance line ("a hole re-typed to 8.00") only makes sense as a diameter on the bracket, whose hole is R4 (Ø8). Proposal: a Radius box with a linked Ø box beside it.
2. **Constraints applied once, or kept live?** Proposal: applied at Apply and stored for re-editing, but not live. If a reference plane is edited later, this face does not move. Live links belong to the feature tree (RE-07).
3. **Faces already used by a trim or solid.** Trim hides its source faces (`modeling_controller.py:1744`), and the body is not rebuilt when a source changes. Proposal: allow the edit and warn "trim again". The alternative is to block editing those faces.
4. **Rounding steps per unit.** Proposal: mm 0.01 / 0.05 / 0.1 / 0.5 / 1; inches 0.001 / 0.005 / 1/64 / 1/32.
5. **Apply closes the tool** (like QuickSurface's OK) rather than staying open.
6. **Middle of two non-parallel planes:** the bisector (proposed), or refuse.
7. **Scope cuts:**
   - QuickSurface's "Fit to selected points" maps to delete plus Fit Surface; there is no reselect in v1.
   - Torus is not editable in v1.
   - Type in for cylinder, cone and sphere is included because VectorEditor makes it cheap.

**Risks and edge cases**
- **Stale triangle ids.** A display-proxy rebuild (and later H-07 scan cleanup) invalidates the stored triangle ids. This is guarded by `display_triangles` and the "nearby" fallback. The fallback can pick up neighbouring faces that lie in the same plane or on the same axis, so the panel labels it.
- **Scan moved after fitting.** A transform (or H-01 Align) makes the points and the surface disagree; the deviation will show it. H-01 must move the model surfaces along with the scan.
- **Sign flips.** Plane normals keep their old sign (face orientation, and the solid's material test). Axes are compared ignoring sign.
- **A constraint far from the data** (for example forcing an axis perpendicular to its own fitted direction) can settle on a poor answer. The fit starts from the start projected onto the constraint, shows the deviation, and returns a reason rather than raising.
- **Dropped live previews while busy.** Handled by the retry timer and the revision check. Spin boxes have keyboard tracking off.
- **Undo while the tool is open:** handled in `discard_stale`.
- **References:** a deleted reference comes back as "free" with a note when the editor reopens. The entity itself and bodies are never offered.
- **Geometry limits:**
  - cone: keep v0 ≥ 0 so it does not cross the apex, and the half-angle within 0.2°–89° as the fitter does (`primitives.py:460`);
  - sphere: v within ±π/2;
  - plane Type in with a zero normal is an error.
- **Alarming max values.** Max error is over all selected points, so it includes bleed onto neighbouring faces (0.29 mm on a crude hole selection in the prototype). It matches the numbers Fit Surface shows, but may look alarming; consider showing the inlier share in the readout.
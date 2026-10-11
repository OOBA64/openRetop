# H-04 (automatic segmentation in the app) and H-07 (scan cleanup): implementation design

Line numbers refer to HEAD `233d271`. Another session has uncommitted H-03 work in this worktree:
- `cad_kernel/jobs.py`: `fit_surface(..., reach=0.0)`
- `modeling_controller.py`: `fit_preview` passes `reach=`; lines after 56 shift by about 14
- `viewer/modeling_scene.py`: `surface_opacity`
- `surfacing_workbench.py`: `FITTING_SURFACE_OPACITY`

Land this design on top of that work. All paths are under `src/openretop/` unless noted.

On the user's hover request: every new command gets a one-line `_DESCRIPTIONS` entry. That entry is the hover tooltip and the palette text, as H-10 already does for the sketch tools.

---

## 1. What exists today, and the gaps

### Segmentation (RE-03): only benchmarks and tests reach it
- **Entry point** (`segmentation/segment.py:102`):
  `segment_mesh(vertices, triangles, *, tolerance=None, angle_tolerance_degrees=None, min_region_triangles=30, seed_radius=None, progress: Callable[[float], None] | None = None) -> SegmentationResult`
- **Result types:**
  - `SegmentationResult.labels` gives the segment id of each triangle, with `UNASSIGNED = -1` (`:31`, `:49-64`).
  - `Segment(id, kind, triangles, fit, area, width, edge_band)` is at `:34-46`.
- **Internals I will rely on:**
  - `_estimate_noise(vertices, triangles, vertex_normals, offsets, neighbours, samples=300) -> (sigma, jitter)` at `:198`. It is private.
  - The candidate kinds are hard-coded at `:320` (`for kind in ("plane","cylinder","sphere","cone","torus")`) and `_SIMPLER` at `:276`.
  - The seed loop at `:136` has no cancel and calls `progress` only when a region is accepted (`:155`).
- **Measured runtimes** (venv, this machine):

| Scan | Triangles | All kinds | No torus | Regions | Noise σ |
|---|---|---|---|---|---|
| bracket_scan (B1) | 71k | 2.5 s | 1.8 s | 23 (11 plane, 4 cyl, 8 ff) | 0.021 |
| casting_scan (B5) | 45k | 13.5 s | 9.9 s | 34–35 | 0.021 |
| Oil pan | 64k | 35.4 s | 17.3 s | 313 / 293, 89–91% assigned | 0.145 |
| TurboBumper, full | 794k | **171.9 s** | – | 122 (73 torus!) | 0.012 |
| TurboBumper, display proxy | 220k | – | 25.8 s (+6.9 s to build the proxy) | 130 | – |

- **Where the time goes:** under cProfile, 47 of 53 s on the oil pan is `fit_primitive`, and 27.6 s of that is torus. Torus is the cost driver.

### Fit Surface "Auto": why the oil pan flange came out freeform
- `ModelingController.fit_preview()` (`application/modeling_controller.py:382`) sends `tolerance=options.tolerance` (`:404`). The default is `FitOptions.tolerance = 0.05` (`:66`).
- `jobs.fit_surface(points, triangles=None, normals=None, *, kind="auto", ..., tolerance=0.05)` (`cad_kernel/jobs.py:92`) calls `auto_surface_kind(points, normals, tolerance)` (`:155`).
- That calls `classify_region(points, normals, *, tolerance, min_inliers=0.75)` (`fitting/primitives.py:100`). It accepts a type only if its RMS is at most `tolerance`.
- **Root cause, measured:** the oil pan flange smart selection (2,158 triangles) fits a plane at RMS **0.081** with 99% inliers. At tol 0.05 Auto gives freeform; at tol ≥ 0.1 it gives a plane. The tolerance sits below the scan noise.

### Scan selection (S-05)
- `ScanSelection(vertices, triangles)` (`modeling/scan_selection.py:17`) is a mask over **display-mesh** triangles. Its methods:
  - `matches()` checks array identity (`:42`).
  - `smart_select(seed, angle, *, add, connected) -> int` (`:64`), `set_mask` (`:57`), `invert` (`:53`).
- `SourceMapping.source_triangles_for(display_mask)` (`:189`) maps the mask to the full-resolution scan by nearest centroid.
- The controller side:
  - `select_at(self, triangle: int | None, *, add: bool | None = None)` (`modeling_controller.py:333`)
  - `brush_at` (`:346`)
  - `_source_mapping()` (`:2299`) and `_selected_scan_data()` (`:2315`)
  - `SELECTION_MODES` (`:55`)
- **Drawing:** the selection is a `ScanOverlayRenderItem("scan-selection")` with `triangle_mask` (`viewer/modeling_scene.py:221-237`).
  - The item supports only `triangle_mask` / `vertex_colors` (`viewer/scene_types.py:362-377`).
  - `update_scan_overlay_actor` (`viewer/model_actors.py:63`) sets point scalars only. There is no per-triangle colour.
  - All overlays share one depth pull, `SCAN_OVERLAY_DEPTH_PULL` (`model_actors.py:15`).

### How the scan mesh is held
- `MeshObjectState` (`application/state.py:27-47`) holds:
  - `source_mesh`, `display_mesh` (a proxy when the scan has more than 150k triangles), the counts, and `display_proxy_enabled`
  - `source_bounds_min/max`, and `file_path`
  - It has no revision and no "edited" flag.
- **Loading:**
  - `_install_model` (`presentation/qt/main_window.py:1384`) builds it.
  - `_rebuild_display_proxy` (`:1409`) runs `display_proxy.build(source, quality)` in the background.
  - `build_display_mesh(source_mesh, *, quality=DEFAULT_PROXY_QUALITY) -> DisplayMeshResult` is at `mesh/display_proxy.py:46`. It uses VTK decimation; `_remove_degenerate_faces` is at `:302`.
- **Caches keyed by array or object identity.** Replacing the mesh objects invalidates them automatically:
  - `transformed_source_mesh` (`application/transform_controller.py:638`, `cached[0] is source` at `:651`)
  - `ScanSelection.matches`
  - `_mapping` (`:2304`), `sketch_projector` (`:1888` in the working tree), `_scan_normals` (`:2324`)
  - the scene `_mesh_revision` (`viewer/scene_builder.py:53`)
- **Exception:** `measure_controller._snapped` keys on `id(mesh.source_mesh)` (`application/measure_controller.py:180`). Python can reuse an id after garbage collection, so a revision counter is needed.
- **Edited in place:** only `center_geometry_on_origin` (`source_mesh.translate`, `transform_controller.py:256`) and `_restore_object` (`:917`). Both assign new arrays, and undo is last-in-first-out, so keeping references to old mesh objects in undo entries is safe.
- **Undo machinery:**
  - `UndoStack` has no size limit (`application/undo.py:31`).
  - `CallbackUndoPayload(name, undo_action, redo_action)` is at `application/controller_support.py:112`.
  - `WorkflowService.dispatch` pushes the payload when `success and undo_payload and changed` (`application/workflow_service.py:98-99`).

### What depends on display-triangle indices (stale after any mesh edit)
- `ScanSelection` and `SourceMapping`.
- The legacy Region Select: `RegionSelection.triangle_indices`, a single `active_region` (`regions/region_state.py:16-37`). It is saved in the project.
- `Deviation.distances`, one value per display vertex (`modeling_controller.py:138`). The scene only checks the length (`modeling_scene.py:248`), so smoothing would leave a stale map on screen.
- `params["triangles"]` on Fit entities (`:434`). Nothing reads it (grep), so it is harmless.
- **Not affected:** model BREPs, Surface Sketch nodes (positions), section results (polylines) and timeline inputs. These are geometry, not indices.

### Persistence gap
- The project stores only `mesh_path` (`project/project_state.py:58-63`). A cleaned scan would be lost on reopen.
- There is no mesh export anywhere.

### Libraries in the venv

| Package | Version | Notes |
|---|---|---|
| trimesh | 5.1.1 | declared in `pyproject.toml:12-19` |
| vtk | 9.6.2 | declared |
| numpy | 2.5.3 | declared |
| scipy | 1.18.1 | used but **not declared** |
| numba | 0.68 | not declared |
| pyvista | 0.49 | unused in `src/` |

- **Not installed:** open3d, pymeshlab, fast-simplification. So `trimesh.simplify_quadric_decimation` cannot be used.
- **VTK filters are allowed by the architecture rules:** only `vtkRendering*`, `vtkInteraction*`, `vtkGUISupport*` and `vtkViews*` are banned (`scripts/report_architecture_metrics.py:45-49`).

### Cleanup operations, measured
- **TurboBumper (794k triangles):**
  - Connected pieces: **0.72 s**, 28 pieces. The pieces come in **mirrored pairs: 263,189 ×2, 58,507 ×2, 28,848 ×2…**; the strays are 7, 7, 1, 1. **So "keep largest" would delete half the bumper.**
  - Boundary loops: **0.46 s**, 58 loops, 28,960 boundary edges, 0 non-manifold edges.
  - `vtkQuadricDecimation` to 300k: **4.4 s**. Deviation over 20k sampled points: RMS **0.009 mm**, max **0.46 mm** (measured in 0.3 s with `MeshProjector`).
  - Smoothing: `vtkWindowedSinc` (15 iterations) 0.4 s; trimesh Taubin (10 iterations) 0.4 s.
  - **Rebuilding the display proxy: 5.9–6.9 s.** This is the main cost of each edit.
  - `vtkFillHolesFilter` adds no interior points and assumes planar holes.
- **Oil pan:** 8 pieces (63,731 plus strays of 13, 3, 1, 1, 1, 1, 1). Of its 78 hole outlines:
  - 1.6–7.7 mm across with 3–14 edges: dropouts.
  - 8.9–13.1 mm across with 18–32 edges: probably **bolt holes**, which must not be auto-filled.
- **Bracket:** four 3-edge pinholes (0.6 mm) and two 5.7 mm holes.
- **Decimation side effect:** decimating B1 from 71k to 28k created one non-manifold edge.

### Gaps
- No action, panel or overlay reaches segmentation.
- No per-triangle colour overlay.
- No cancel or progress for background jobs. `_progress` calls `setCancelButton(None)` (`main_window.py:1597`).
- No mesh editing, no mesh undo, no saving of an edited scan.
- No Delete-key handling inside tools. The window's `Delete` shortcut (`scene.delete_selected`) could delete the whole scan.

---

## 2. User flow

### H-04: Find Regions → one click per face
1. In the **Scan** workspace, the toolbar shows **Find Regions**. Hover text: *"Colour the scan by its faces (plane, cylinder, … or freeform); in Fit Surface a click then selects a whole face."*
2. A progress dialog appears: "Finding regions… 43%" with **Cancel**. Cancel leaves the scan unchanged.
3. When it finishes:
   - The scan is coloured. Each type has its own hue family; neighbouring regions of the same type get different lightness. Edge bands and unassigned triangles are dark grey.
   - Status line: *"Found 23 regions in 2.5 s: 11 planes, 4 cylinders, 8 freeform (scan noise about 0.02 mm). In Fit Surface a click selects a whole region."*
4. **Fit Surface** opens in **Region** mode whenever regions match the current scan. The selection buttons are now Smart | Region | Brush | Erase.
   - A legend line shows the counts by type, with a **Clear Regions** button.
   - If there are no regions, the panel shows a **Find Regions** button and the hint *"Colours each face; then one click selects it."*
5. Clicking a region adds it to the selection. Clicking an already selected region removes it.
   - Clicking an edge band or an unassigned triangle falls back to Smart select.
   - Ctrl+click works as today.
6. **Enter** (Create) fits the surface. With Auto, a selection that is at least 80% one exact-type region uses that type. The preview line says *"Plane (matches its region) – RMS 0.081, max … mm"*. Otherwise the noise-aware Auto applies: *"Plane (fits within 2× scan noise 0.29 mm)"*.
7. Create clears the selection (existing behaviour, `:437`), so the next click is the next face.
   - Region colours stay visible while Fit Surface is open and in the Scan workspace.
   - They are hidden while Compare, Body Lines or Clean Up is shown.
8. **Undo:** Find Regions and Clear Regions are view state, not undoable, the same as the Compare map. Each Create stays undoable, as today.

### H-07: Clean Up tool (Scan toolbar), each step one undo entry
1. Click **Clean Up**. Hover text: *"Prepare the scan: delete areas and stray pieces, fill small holes, reduce the triangle count, smooth. Each step can be undone."*
   - It runs as a heavy action: about 1.2 s on the bumper to find pieces and holes.
   - The panel header gives a health check: *"793,996 triangles · 28 pieces · 58 holes (3 small) · 0 non-manifold edges"*.
2. **Section 1, Delete an area:** the same Smart / Brush / Erase, Angle, "whole connected piece", Clear and Invert controls as Fit Surface. Then **Delete Selected (Del)**.
   - Hint: *"To keep one piece: tick whole connected piece, click it, Invert, Delete."*
   - Del is claimed by the tool, so the window's Delete shortcut cannot remove the scan.
3. **Section 2, Stray pieces:** "Pieces under [0.10] % of the scan". The status reads *"4 pieces, 16 triangles"* and those pieces are shown **red** live.
   - **Delete Pieces**.
   - **Keep Largest Only**: the preview shows what goes first, e.g. *"removes 27 pieces, 530,807 triangles (67%)"*.
4. **Section 3, Holes:** small holes are outlined in yellow, the rest in cyan.
   - "Fill holes up to [7.7] mm across". The status reads *"24 of 78 holes"*.
   - The default is the largest hole with at most 8 boundary edges: 0.6 mm on the bracket, 7.7 mm on the oil pan. Bolt holes (18+ edges) are left alone.
   - **Fill Holes** fills all outlined small holes.
   - Clicking any outline fills just that hole. Status: *"Filled a 24-edge hole (31 mm around); Ctrl+Z brings it back."*
5. **Section 4, Reduce:** "Triangles [300,000] (now 793,996)" then **Decimate**. The default is min(current, 300k) when the scan is over 300k, else 50%.
   - Result: *"Decimated to 300,000 in 9.8 s: deviation RMS 0.009, max 0.46 mm."*
6. **Section 5, Smooth:** Light / Medium / Strong, with "Selected area only" ticked by default. Then **Smooth**.
   - Result: *"Moved points RMS 0.012, max 0.05 mm."* Open borders never move.
7. **Keys:**
   - Del deletes the selected area.
   - `[` / `]` change the brush size.
   - Esc closes the tool.
   - Ctrl+Z / Ctrl+Y undo and redo each step, with names like "Undo Delete 4 pieces".
   - **No Enter action**, because every step is destructive.
8. **After an edit:** regions, the deviation map and the legacy Region Select are cleared. Undo brings them back. Status: *"Regions cleared: the scan changed – Find Regions again."*
9. **Save Project with an edited scan:** writes `<project stem> scan.ply` beside the project, and the project now points to it. The original file is never touched.

---

## 3. Data and code changes

### Library (pure, no Qt)

**`segmentation/segment.py`**
- New `PRIMITIVE_ORDER = ("plane","cylinder","sphere","cone","torus")` and `class SegmentationCancelled(Exception)`.
- `segment_mesh(..., progress=None, kinds: tuple[str, ...] = PRIMITIVE_ORDER, cancel: Callable[[], bool] | None = None) -> SegmentationResult`
  - Thread `kinds` through `_grow_best` (`:320`) and filter `_SIMPLER` to `kinds` (`:276-284`).
  - In the seed loop (`:136`): check `cancel()` on each seed and raise `SegmentationCancelled`. Every 64 seeds, call `progress(np.mean(tried | (labels != UNASSIGNED)))`. Today the bumper shows no progress for the first 100 s.
- New `estimate_noise(vertices, triangles) -> float`: wraps `triangle_adjacency` + `_vertex_normals` + `_estimate_noise`. About 0.17 s at 70k.
- Export both in `segmentation/__init__.py`.

**`cad_kernel/jobs.py`**
- New `AUTO_NOISE_FACTOR = 2.0`.
- `fit_surface(..., tolerance=0.05, reach=0.0, noise: float = 0.0, kind_hint: str | None = None)`
- `auto_surface_kind(points, normals, tolerance, *, noise=0.0, hint=None) -> tuple[str, str]`, returning `(kind, reason)`:
  - `limit = max(tolerance, AUTO_NOISE_FACTOR * noise)`.
  - If `hint` is an exact type and `fit_primitive(hint, ...)` has RMS ≤ `limit` with inliers ≥ 0.75, return `(hint, "region")`.
  - Otherwise use `classify_region(..., tolerance=limit)`.
- The result dict gains `auto_reason` and `auto_limit`.

**New `modeling/scan_regions.py`**
```python
@dataclass(frozen=True)
class ScanRegions:
    labels: np.ndarray; kinds: tuple[str, ...]; edge_band: np.ndarray
    noise_sigma: float; seconds: float; triangles_ref: object  # identity of display.triangles
    @classmethod
    def from_result(cls, result: SegmentationResult, triangles: np.ndarray) -> ScanRegions
    def matches(self, triangles: object) -> bool
    def region_at(self, triangle: int) -> int
    def mask_of(self, region: int) -> np.ndarray
    def dominant(self, mask: np.ndarray) -> tuple[int, float] | None   # region, share of mask
    def colors(self) -> np.ndarray       # (T, 3) uint8, cached
    def summary(self) -> str
```
`ScanRegions` matches on triangles only, so smoothing (same topology) keeps the regions.

**New `mesh/cleanup.py`** (numpy, scipy, `vtkFiltersCore`)
```python
@dataclass(frozen=True)
class ScanAnalysis:
    component: np.ndarray; piece_sizes: np.ndarray
    loops: tuple[np.ndarray, ...]; loop_edges: np.ndarray; loop_diameter: np.ndarray
    median_edge: float; nonmanifold_edges: int
def analyse(vertices, triangles) -> ScanAnalysis
def small_pieces(a: ScanAnalysis, percent: float) -> np.ndarray      # triangle mask
def all_but_largest(a: ScanAnalysis) -> np.ndarray
def auto_hole_size(a: ScanAnalysis, max_edges: int = 8) -> float
def holes_up_to(a: ScanAnalysis, diameter: float) -> tuple[int, ...]
def remove_triangles(vertices, triangles, drop: np.ndarray) -> tuple[np.ndarray, np.ndarray]
def fill_holes(vertices, triangles, loops: Sequence[np.ndarray], max_edges: int = 400) -> tuple[np.ndarray, np.ndarray, int]
def decimate(vertices, triangles, target: int) -> tuple[np.ndarray, np.ndarray]
def smooth(vertices, triangles, *, iterations: int, movable: np.ndarray | None = None) -> np.ndarray
```
- **`analyse`:** pieces come from `triangle_adjacency` + scipy `connected_components`. Loops come from edges used once, traced in half-edge order.
- **`remove_triangles`:** compacts unused vertices and keeps the order of the triangles it keeps.
- **`fill_holes`:**
  - Appends vertices and triangles only, so existing indices are unchanged.
  - Per loop: minimal-area dynamic-programming triangulation (vectorised over k), then split triangles larger than the boundary average and flip interior edges, then Laplacian fairing of the new vertices with `scipy.sparse.linalg.spsolve` (boundary plus one ring fixed).
  - New triangles take the reversed half-edge direction, so orientation stays consistent.
  - Loops over 400 edges are refused: "use Fill Surface".
- **`decimate`:** `vtkQuadricDecimation`, `VolumePreservationOn`, `SetBoundaryWeightFactor`, then `_remove_degenerate_faces`.
- **`smooth`:** Taubin (λ 0.5, μ −0.53) on a uniform sparse Laplacian. Boundary vertices and vertices outside `movable` stay fixed.

### Application

**`application/state.py`**
- `MeshObjectState`: add `edited: bool = False` and `revision: int = 0`.
- `AppState`: add `scan_regions: ScanRegions | None = None` (derived, not saved).

**New `application/scan_controller.py`**
```python
class JobMonitor:  # written by the worker thread, read by a UI timer
    fraction: float
    def report(self, value: float) -> None
    def cancel(self) -> None
    def cancelled(self) -> bool
    def reset(self) -> None

@dataclass(frozen=True)
class ScanVersion:  # everything a scan edit replaces, held by reference (no copies)
    source_mesh: TriangleMeshData; display_mesh: TriangleMeshData
    source_triangle_count: int; display_triangle_count: int; display_proxy_enabled: bool
    display_reduction_percent: float; source_bounds_min: np.ndarray; source_bounds_max: np.ndarray
    file_path: Path | None; edited: bool; regions: ScanRegions | None
    active_region: RegionSelection | None; selection_mask: np.ndarray | None; analysis: ScanAnalysis | None

class ScanController(ControllerBase):
    def __init__(self, state: AppState, *, transform: TransformController, modeling: ModelingController,
                 proxy_quality: Callable[[], str], events: EventPublisher | None = None) -> None
    job: JobMonitor
    def reset(self) -> None
    def segment(self) -> CommandResult
    def clear_regions(self) -> CommandResult
    def analysis(self) -> ScanAnalysis | None   # cached per source mesh
    def delete_selected(self) -> CommandResult
    def remove_pieces(self, *, percent: float | None = None, keep_largest: bool = False) -> CommandResult
    def fill_holes(self, *, diameter: float | None = None, holes: tuple[int, ...] | None = None) -> CommandResult
    def decimate(self, target: int | None = None) -> CommandResult
    def smooth(self, *, strength: str = "medium", selection_only: bool = True) -> CommandResult
    def _replace(self, name: str, vertices: np.ndarray, triangles: np.ndarray, status: str, *, same_topology: bool = False) -> CommandResult
    def _apply(self, version: ScanVersion) -> None
```
- **`segment`:** runs on the display mesh (it is the source itself for scans of 150k triangles or fewer) with `kinds=` everything except torus, `progress=job.report`, `cancel=job.cancelled`.
- **`delete_selected`:** uses `modeling.selected_source_triangles()`.
- **`_replace`:**
  1. Build the new `TriangleMeshData` and call `compute_vertex_normals()`.
  2. Call `build_display_mesh(new, quality=proxy_quality())` (`display_proxy.py:46`). With `same_topology` and no proxy, give the display mesh the new vertices directly.
  3. Capture the before and after `ScanVersion`, then `_apply(after)` as one block.
  4. Set `modeling.deviation = None`, `state.scan_regions = None`, and `region_collection.active_region = None`.
  5. Set `edited = True`, `revision += 1`, then `publish_scene_change(...)`.
  6. Return `CommandResult.ok(..., changed=True, dirty=True, undo_payload=CallbackUndoPayload(name, lambda: self._apply(before), lambda: self._apply(after)))`.
  7. Also report the deviation for decimate and smooth: 20k samples with `MeshProjector`.
- **`_apply`:** restores every field, restores the selection mask on the restored display mesh, and bumps `revision` (monotonic).

**`application/modeling_controller.py`**
- `TOOLS` (`:40`) gains `"cleanup"`. `TOOL_TITLES["cleanup"] = "Clean Up"` and a hint at `:267`.
- `SELECTION_MODES` (`:55`) gains `"region"`.
- `ToolSession` (`:70`) gains `cleanup_piece_percent: float = 0.1`, `cleanup_hole_size: float = 0.0` (0 means auto), `cleanup_target: int = 0`, `cleanup_strength: str = "medium"`, `cleanup_selection_only: bool = True`.
- `start()` (`:218`):
  - `"cleanup"` requires a mesh (`:221`).
  - `fit_surface` switches `smart` to `region` when `state.scan_regions` matches the current display mesh.
- `select_at` (`:333`): in region mode, toggle `regions.mask_of(r)`. When the label is −1 or the region is an edge band, fall back to `smart_select`.
- `fit_preview` (`:382`): pass `noise=self.scan_noise()`, plus `kind_hint` when `regions.dominant(mask)` has a share of at least 0.8 and an exact kind.
- New `scan_noise(self) -> float`: cached by source-array identity, measured on the world-space source.
- New `selected_source_triangles(self) -> np.ndarray`: `self._source_mapping().source_triangles_for(selection.mask)`.
- `reset()` (`:198`) also clears the noise cache.

**`application/workflow_service.py`**
- The constructor gains `scan: ScanController`.
- In `_dispatch` before `:217`, add `if action.startswith("scan."): return self._dispatch_scan(action, payload)`.
- `scan.cleanup` maps to `self.modeling.start("cleanup")`. The other `scan.*` actions map to the controller methods above.

**`application/actions.py`**
- New actions (category `"Scan"`):
  - `scan.segment` "Find Regions" and `scan.cleanup` "Clean Up", both `_MESH`.
  - `scan.regions_clear`.
  - `scan.delete_selected`, `scan.remove_pieces`, `scan.fill_holes`, `scan.decimate`, `scan.smooth`, all with `MODEL_TOOL_ACTIVE` and `NOT_BUSY`.
- Each gets a one-line `_DESCRIPTIONS` entry (`:321`), as quoted in section 2.

**`bootstrap/composition_root.py`**
- Build `ScanController(...)` after `:101`, with `proxy_quality=lambda: settings.import_settings.default_proxy_quality`.
- Add the field `scan_controller` and pass it to `WorkflowService` (`:103`).

**`application/guidance.py`:** the "Model the part" step list (`:96-108`) gains Find Regions and Clean Up.

### Presentation

**`presentation/qt/main_window.py`**
- Scan toolbar (`:345`): add `("scan.cleanup","cleanup","Clean Up",True)` and `("scan.segment","segment","Find Regions",False)`.
- Add the SVGs to `ICONS` in `packages/workbench_ui/workbench_ui/icons.py`.
- `HEAVY_ACTIONS` (`:104`) gains `scan.segment`, `scan.cleanup` and the five operations. `_heavy_label` gets matching labels.
- `_run_background` (`:1339`) and `_progress` (`:1593`) take optional `cancel: Callable[[], None]` and `fraction: Callable[[], float]`. They show a Cancel button and a 200 ms `QTimer` that polls `fraction`. Used for `scan.segment`.
- `save_project` (`:1431`): if `mesh_object.edited`, write the scan via trimesh as binary PLY (new `infrastructure` helper), then set `file_path` and clear `edited`.
- `_finish_open_project` and project reset call `scan_controller.reset()`.

**`presentation/qt/surfacing_workbench.py`**
- `SURFACING_ACTIONS` (`:27`) gains `scan.cleanup`. `TOOL_HINTS["cleanup"]` (`:74`).
- Add `SELECTING_TOOLS = ("fit_surface","cleanup")`, replacing the fit-only checks at `:673`, `:797`, `:828`, `:854`, `:1244`, `:1290` and the brush ring (`:1492`).
- `_surfacing_claims_key` (`:202`) claims `Key_Delete` in cleanup when the selection has any triangles. `_surfacing_key` (`:154`) maps Delete to `scan.delete_selected`.
- Clean Up clicks: a new `_hole_at(x, y)` (screen distance to the projected outlines, the same pattern as `_sketch_curve_at` at `:884`) dispatches `scan.fill_holes {"holes": (i,)}`; any other click goes to `select_at`.
- `_modeling_scene_input` (`:1241`) passes region colours (only when they match, the tool is None or fit_surface, and there is no deviation map or creases), the red removal mesh, and the hole outlines.
- `_refresh_surfacing_panel` (`:1282`) adds `_cleanup_facts`, the regions summary for the Fit page, and the Auto reason in the preview text (`:1293`).

**`presentation/qt/surfacing_panel.py`**
- `SELECTION_MODES` (`:43`) gains `("region","Region")`. Its button is enabled only when `facts.extra["regions"]` is set.
- The Fit page (`:437`) gains the Find Regions button, the legend and Clear Regions.
- `PAGES` (`:44`) gains `"cleanup"`, built by `_build_cleanup` / `_show_cleanup` and called from `show_session` (`:174`).

**`viewer/scene_types.py:362`**
- `ScanOverlayRenderItem` gains `triangle_colors: np.ndarray | None = None` and `depth_pull: tuple[float, float] = (-1.0, -4.0)`.

**`viewer/model_actors.py:63`**
- When `triangle_colors` is set: use `shaded_polydata` (it keeps cell order), set `GetCellData().SetScalars`, `SetScalarModeToUseCellData`, and apply `item.depth_pull`.

**`viewer/modeling_scene.py:84`**
- `ModelingSceneInput` gains `region_colors`, `region_revision`, `removal: tuple[np.ndarray, np.ndarray] | None`, `hole_lines` and `hole_auto`.
- New overlays: `scan-regions` with pull (−0.5, −2), behind the selection; `scan-removal` in red, drawn as source vertices and triangles with the scan's transform. Also edge items `scan-holes` / `scan-holes-auto`.

---

## 4. Tests

### Unit tests (no Qt)
- **`tests/test_scan_cleanup.py`:**
  - Two grids plus a one-triangle shard: `analyse` finds 3 pieces. `small_pieces(0.1)` returns only the shard. `all_but_largest` drops the second grid. `remove_triangles` keeps the order of kept triangles.
  - A plate with a pinhole, a 6-triangle hole and its outer border: `auto_hole_size` covers both inner holes and not the border.
  - `fill_holes` leaves only the outer loop, adds no non-manifold edges, and orients every interior edge once each way. The original triangles are an exact prefix of the result. A planar hole stays planar to 1e-9.
  - A sphere cap with a hole: filled points within 5% of the hole diameter from the sphere.
  - `decimate` on B1 from 71k to 30k: count within 1%, deviation RMS under 0.02 (measured 0.0092).
  - `smooth`: noise drops, boundary and non-`movable` vertices are bit-identical.
- **`tests/test_re_segmentation.py` additions:**
  - `kinds=("plane","cylinder")` yields only those kinds plus freeform.
  - `cancel` raises `SegmentationCancelled`.
  - Progress values are increasing.
  - `estimate_noise` on B1 is 0.02 ± 30%.
- **`tests/test_re_surfacing.py` additions:**
  - A noisy plane with σ 0.08: `auto_surface_kind(..., 0.05)` gives freeform; with `noise=0.08` it gives plane.
  - A `hint` is honoured, and a wrong hint falls back to classification.
  - The oil pan flange, `skipUnless(test_assets exists)`: the smart selection at the s5 seed fits as a plane.

### Controller-level tests (`workflow.dispatch`, `KernelWorker(inline=True)`, `_install` as in `tests/test_surfacing_workflow.py:36`)
- B1: after `scan.segment`, Fit Surface starts in region mode.
  - For every non-edge-band region of at least 200 triangles: `select_at(t)` selects exactly that region, and `model.fit_create` gives its exact kind with RMS under 0.03. This is the acceptance "every face is one click".
- Clean Up:
  - `delete_selected` → `edit.undo` restores the same source object (identity), the selection mask and the regions. `edit.redo` applies the edit again.
  - The deviation map and the active Region Select region are cleared by an edit.
  - `remove_pieces`, `keep_largest`, `fill_holes`, `decimate` and `smooth` (selection only) are each undoable.
- Save after an edit writes `<stem> scan.ply`. Reopening the project gives the edited triangle count.

### Window-level tests (offscreen; call `set_project_dirty(False)` before close, per the memory note)
- The Scan toolbar shows Find Regions and Clean Up, and their tooltips hold the description.
- Region mode: `_on_viewport_pointer("left_release", x, y, MeshPickResult(...))` selects the whole region, the panel shows the reason, and Enter creates the surface.
- Clean Up Delete through **`QTest.keyClick(viewport.interactor, Qt.Key_Delete)`**. QTest sends the shortcut override that a person's key press would, so the window's Delete shortcut gets its chance. Assert that the scan is still loaded and the selected triangles are gone; Ctrl+Z restores them.
- The `scan-regions` overlay is present in the scene snapshot and hidden while Compare is up.
- Esc closes Clean Up.

### Real-window check: new `scripts/usability/s7_scan_prep.py` using `human.py`
- **Bracket:** `scan_of("bracket")`, `tab("Scan")`, `click_toolbar("Find Regions")`, `idle()`, then for each face centre: `click_world` + `key(Enter)`. Log the kinds and RMS.
- **Oil pan:** Find Regions (log the time), then click the flange point from s5 and Create. Expect a Plane.
- **Bumper:** open, Clean Up (log the analysis time and the "4 pieces, 16 triangles" text), `click_panel("Delete Pieces")`, type 300000 in the target field and press Enter, `click_panel("Decimate")`. Log the total time against the **under 30 s** acceptance (estimate: about 1 + 6 + 4.4 + 4 s), Ctrl+Z, and screenshots.
- **Note:** `Human.key` uses `sendEvent`, which bypasses QAction shortcuts. Add a `key_real()` helper based on `QTest.keyClick` for the Delete check.

---

## 5. Risks, edge cases, open questions

**Decisions for the product owner**
1. **Persisting an edited scan:** the proposal writes `<project> scan.ply` beside the project on Save. Alternatives: ask for a path, or embed the mesh in the project. Should we also add **File > Export Scan** (STL/PLY), which Design X users expect?
2. **Torus off by default in Find Regions:** about 2× faster (oil pan 35 → 17 s). Tori come out as cylinder, cone or freeform instead.
3. **Regions are not saved** with the project (recompute: 2.5–26 s). Saving labels for the display mesh would add about 1 MB.
4. **Default thresholds:**
   - pieces under 0.1%
   - holes: the largest with at most 8 edges (0.6 mm bracket, 7.7 mm oil pan; bolt holes kept)
   - decimate default 300k
   - Auto factor 2σ
5. **Undo memory:** each scan edit keeps about 75 MB at 794k triangles, and the undo stack has no limit. Should old scan versions be capped (e.g. 8 steps)?
6. **Smoothing in P0:** it moves the measured data and rounds sharp edges. The proposal limits it to the selection by default and reports the displacement, or it can be deferred.

**Technical risks**
- **Speed:** segmentation is 26 s on the bumper proxy and 172 s at full resolution (`segment_mesh` holds the GIL in its per-seed Python loops, so the UI may stutter). It runs on the display mesh with progress and cooperative cancel.
- **Organic scans:** on the bumper, segmentation gives many spurious primitive regions (61 cylinders, 25 cones). Region mode is useful on mechanical parts; Smart stays available.
- **The 2σ rule:** on 13 random oil pan selections, it changed 4 results.
  - Three became planes at RMS 0.054–0.083, all plausible.
  - One 297-triangle area became a cylinder at RMS 0.236 against freeform 0.049.
  - Possible guard: reject an exact type whose RMS is more than 2.5× the freeform RMS (costs one extra freeform fit, about 0.2 s). Validate on B1–B5 and the oil pan.
  - On the coarse oil pan the noise estimate is inflated (σ 0.145 against the flange's 0.081), so show it as "about".
- **Display proxy rebuild:** 6–7 s per edit at 800k dominates every step. The display→source mapping makes delete boundaries jagged by up to one proxy triangle for scans over 150k.
- **Decimation:** can create non-manifold edges (one on B1). Report the count in the warnings.
- **Threading:** edits run on the executor thread. Apply each `ScanVersion` in one block, and keep the window locked while busy (the existing behaviour).
- **Region mode on edge bands:** a click on a scanner-rounded edge would select a thin strip, so it falls back to Smart select.
- **Related existing hazard:** in Fit Surface, the window's Delete shortcut may delete the whole scan when the scan node is selected. Claim Delete there too.
- **No lasso or rectangle selection yet.** Design X users will look for it to delete fixtures or the turntable. Brush plus "whole connected piece" and Invert cover the P0 cases.
- **`params["triangles"]` on Fit entities** (`modeling_controller.py:434`) is stale after an edit. Nothing reads it; drop it or document it.
- **scipy** is a runtime dependency that is not declared in `pyproject.toml`. The new code relies on it more.
# Task 82B - Viewport Interaction, Scene Visibility, Gizmo, and View Controls Repair

## Status

The Task 82B implementation is complete. The objective acceptance checks pass
through a real visible Windows Qt/VTK path, including the exact
`FrontNoseTest.openretop` project. Camera navigation, tree checkbox commands,
transform-overlay lifecycle, the fixed orientation gizmo, view controls,
framing, resize, maximize, minimize/restore, and normal shutdown all completed
without a render error or application crash.

Base commit: `c08d108746999d036ef3f9c44da918993f2595e1` on
`v3-refactor`.

Repair commit message: `Task 82B: repair viewport interaction and scene controls`.

The repair commit's SHA is reported by `git rev-parse HEAD` after this document
is committed. A commit cannot embed its own SHA because changing this file
would change that content-addressed SHA.

## Baseline and historical research

The fetched `origin/v3-refactor` head matched the required base. The read-only
`origin/main` branch and merge base
`a0b2c530e5f47b3fcb3cfb08fd227ac2f5aea226` were not modified, merged, reset,
or cherry-picked. The existing untracked editable-install metadata under
`packages/workbench_ui/openretop_workbench_ui.egg-info` was preserved and is
not part of this commit.

The old viewport, overlay, scene-browser, and interaction implementations were
inspected together with these commits:

- `98368287` - stable dedicated orientation-gizmo renderer;
- `7e08b998` - section-plane transform and gizmo separation;
- `25bd5989` - camera-relative transform input;
- `521d8045` and `4969ed0a` - camera stability across tool/style refreshes;
- `ab2c458e` - actor reuse;
- `e6761fcd` - tool and region pointer semantics;
- `da29de67` - CAD view controls.

Task 82B reuses the proven four-logical-pixel click threshold, native
TrackballCamera semantics, dedicated overlay renderer, and centralized named
views. It does not restore the Tk shell or monolithic legacy viewport.

## Root causes

### Camera and event routing

The QVTK child used `vtkInteractorStyleSwitch`, while five custom VTK pointer
observers also watched the same interactor. The custom path picked mesh and
scene objects during every motion event, including camera drags, and the main
window selected on every left release without a click/drag distinction.
Selection and tool refreshes could therefore run inside a native VTK gesture.

The final acceptance sweep exposed one additional edge of that conflict:
secondary-button press and release bypassed the application, but secondary
`MouseMove` was still emitted as openRetop tool motion. An active transform
then refreshed the scene during TrackballCamera's drag. Task 82B now bypasses
tool dispatch for the complete middle/right/modified-left gesture, not just its
button transitions.

### Scene-tree checkboxes

`SceneTreeWidget` gave every root, organizational group, and leaf a checkbox.
The application handler responded to a checkbox by selecting that node and
running `scene.show_selected` or `scene.hide_selected`. A synchronous refresh
could rebuild the tree while Qt was still inside `itemChanged`, deleting the
active `QTreeWidgetItem` and producing the observed Shiboken deleted-object
failure. Checkbox state was also incorrectly dependent on selection.

### Axes, gizmo, and controls

One main-renderer `vtkAxesActor` was acting as permanent world axes and as the
orientation indicator. It therefore changed apparent size with project scale,
contributed to the main scene, and remained at world origin while idle.
`show_viewcube` existed in settings but stopped before `SceneBuildOptions`; no
V3 presentation object consumed it.

### Reported white rectangle

Structured prop isolation identified the reported light slab precisely. It was
not the grid, a section plane, an axes caption, an opaque overlay renderer, or
an unfinished view-control prop. It was part of the synchronized
`mesh:mesh` actor loaded from `TurboBumper.stl`.

The source mesh contains 28 connected components. Its full source data has
411,469 processed vertices and 793,998 faces; the displayed proxy used in the
exact-project acceptance has 122,209 points and 220,000 polygon cells. Hiding
only `mesh:mesh` removed the slab, while hiding section/overlay actors did not.
Task 82B therefore does not corrupt user geometry to conceal it. Correct
framing and named-view parallel scale make the part read as the restored bumper
geometry rather than an unexplained screen-space rectangle. The final idle
renderer contains no unidentified visible opaque prop at world origin.

## Final interaction contract

`VTKViewportWidget` owns native camera navigation and configures one
`vtkInteractorStyleTrackballCamera` at construction. Repeated `start()` calls
preserve that style, interactor, render window, and renderer.

`QtSceneViewport` owns the small Qt event filter and toolkit-neutral
`PointerGestureState`:

- middle drag, right drag, wheel, Shift+left, and Alt+left pass to QVTK exactly
  once and never enter openRetop tool motion;
- unmodified left press/move/release is consumed by openRetop tools or click
  selection and is not also forwarded to TrackballCamera;
- Qt logical coordinates and Euclidean distance classify releases at a
  four-pixel threshold;
- an unmodified left drag, including one beginning over an actor, cannot become
  a selection click on release;
- idle motion performs no pick in the viewport adapter;
- manual-curve hover performs one mesh pick only when its preview requires it;
- scene-object selection picks only on a genuine click release.

`OpenRetopV3Window` remains the application-policy owner for manual curves,
regions, transforms, and selection. Ordinary snapshot, style, visibility, and
selection refreshes carry no camera request and preserve position, focal point,
view up, projection scale, and clipping. Only explicit Frame/Reset/Named View
requests and intentional project-load framing alter the camera.

Named views now recompute framing from current visible bounds when switching to
orthographic projection. Previously VTK's unrelated default parallel scale
could move a large project outside the visible volume even though the camera
direction was correct.

## Scene visibility command path

`SceneNode.checkable` is now explicit. The application marks the root, all
organizational groups, and curve groups non-checkable and non-selectable;
editable feature rows are selectable but non-checkable, and renderable leaves
retain checkboxes. Group visibility remains available
through existing context commands rather than an unimplemented tri-state.

The path is now:

```text
SceneTreeWidget visibility_changed(node_id, visible)
  -> OpenRetopV3Window queued visibility slot
  -> scene.set_visibility {node_ids, visible}
  -> WorkflowService
  -> VisibilityController.set_visibility
  -> one reversible undo payload
  -> authoritative scene/tree refresh
```

It never calls `select_nodes`, `show_selected`, or `hide_selected`. Tree rebuilds
block signals, checkbox clicks suppress incidental selection changes, failures
refresh from authoritative domain state, stale IDs return a visible command
failure, and repeated no-op settings create no extra undo command.

Automated coverage includes mesh, section plane/result, ordinary curve, manual
curve, region-boundary curve, preview surface, BREP surface, and active region.
Existing project round-trip tests continue to cover persistence for supported
visibility fields.

## Overlay design

The viewport now has three separate concepts:

1. The grid is one non-pickable world-space line actor in the main renderer. It
   follows `show_grid` and is not included in snapshot framing bounds.
2. Transform axes and the rotation ring are hidden main-renderer props while
   idle. They appear only for active Move/Rotate at the selected mesh or
   section-plane world origin, follow `show_axes`, emphasize the constrained
   axis, and disappear immediately on confirm/cancel. Rotate adds a colored
   ring plus radial angle indicator.
3. The orientation gizmo is one noninteractive, transparent layer-1 renderer
   containing one non-pickable axes actor. Its viewport is fixed to 96 logical
   pixels with a 12-pixel DPI-aware top-left margin. It is excluded from scene
   bounds and tracks only changes to main-camera direction/up; ordinary scene
   refreshes reuse the actor/renderer and do not rewrite an unchanged gizmo
   camera.

Structured diagnostics retain role, renderer layer and viewport, prop/mapper
class, visibility, pickability, bounds, point/cell counts, color, and opacity
for synchronized scene actors and all overlay roles.

## View controls

`show_viewcube` now flows from settings through `SceneBuildOptions`,
`SceneSnapshot.display`, and `QtSceneViewport`. It remains independent from
`show_axis_gizmo`.

Seven individually masked `QAbstractButton` children sit beside the top-left
gizmo. There is no rectangular container intercepting VTK input: only each
painted triangle accepts a click, while its corners pass through. The compact
two-row layout maps directly to the centralized actions:

- Top / Bottom -> `view.named.top` / `view.named.bottom`;
- Front / Back -> `view.named.front` / `view.named.back`;
- Left / Right -> `view.named.left` / `view.named.right`;
- Isometric -> `view.named.isometric`.

Direction, positive/negative pairing, hover/pressed color, accessible names,
and tooltips are presentation-only. Buttons dispatch existing action IDs;
camera policy stays in the existing `CameraRequest` path. No camera-roll
controls were invented because a stable intended legacy contract was not
recoverable.

## Files changed

Added:

- `src/presentation/qt/pointer_gestures.py`
- `src/presentation/qt/view_controls.py`
- `tests/test_task82b_viewport_interaction.py`
- `docs/v3/tasks/task-82b-viewport-interaction-controls-repair.md`

Modified:

- `packages/workbench_ui/workbench_ui/contracts.py`
- `packages/workbench_ui/workbench_ui/demo.py`
- `packages/workbench_ui/workbench_ui/viewport.py`
- `packages/workbench_ui/workbench_ui/widgets.py`
- `scripts/diagnose_vtk_viewport.py`
- `src/application/actions.py`
- `src/application/workflow_service.py`
- `src/presentation/qt/main_window.py`
- `src/presentation/qt/viewport.py`
- `src/viewer/camera_controller.py`
- `src/viewer/scene_builder.py`
- `tests/test_task82a_viewport_startup.py`
- `docs/v3/STATUS.md`

No files were moved or removed. No Tk code, schema change, geometry algorithm,
synthetic production actor, second selection state, or second visibility state
was introduced.

## Automated verification

Environment:

- Windows 10 build 26200
- Python 3.11.9
- PySide6 6.11.1
- VTK 9.6.2
- render window: `vtkWin32OpenGLRenderWindow`
- renderer: `vtkOpenGLRenderer`
- interaction style: `vtkInteractorStyleTrackballCamera`

The supported roots were:

```powershell
$env:PYTHONPATH = "src;packages/workbench_ui"
```

Final focused visible-Windows results:

- Task 77: 10 passed in 0.005 seconds.
- Task 79: 9 passed in 0.396 seconds.
- Task 80: 7 passed in 1.416 seconds.
- Task 81: 5 passed in 0.311 seconds.
- Task 82: 5 passed in 0.004 seconds.
- Task 82A: 18 passed in 1.629 seconds.
- Task 82B: 26 passed in 3.181 seconds.
- Total focused: 80 passed, no skips.

Complete discovery on the real visible Windows Qt platform passed 528 tests,
no skips, in 11.346 seconds. Complete offscreen discovery passed 526 tests
with the two narrowly scoped visible-render tests skipped, in 7.799 seconds.

Additional results:

- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed.
- `python scripts/report_architecture_metrics.py --fail-on-new`: passed with 0
  dependency violations, 0 practical cycles, and 0 duplicate action/menu
  labels.
- `scripts/diagnose_vtk_viewport.py --offscreen`: passed with native start and
  render safely suppressed.
- `scripts/diagnose_vtk_viewport.py --duration-ms 400`: completed one visible
  Win32 OpenGL render; interactor initialized, actor rendered, no captured
  error, and clean teardown.
- `git diff --check`: passed; only Git's existing LF-to-CRLF notices were
  printed.

## Real Windows acceptance

The exact project was
`C:\Users\devan\OneDrive\Desktop\openRetop Tests\FrontNoseTest.openretop`.
It restored one 122,209-point / 220,000-cell mesh actor, two curve actors, and
one hidden section-plane actor. Snapshot counts and actor inventory agreed,
one camera-to-gizmo observer was registered, renderer size remained valid, and
the last rendering error was `None`.

The visible acceptance used real Qt widgets, `vtkWin32OpenGLRenderWindow`, and
the installed OpenGL driver. Pointer gestures were injected through Qt's test
input API into the shown QVTK native child; this was not a fake renderer or an
offscreen acceptance substitute. A desktop capture of the named top view was
visually inspected and showed the complete bumper, dark viewport, grid, fixed
gizmo, and triangular controls.

Camera results:

- middle pan, right navigation/dolly, Alt+left, Shift+left, and wheel in both
  directions changed camera state once per gesture;
- perspective state and orthographic `ParallelScale` were both measured;
- an unmodified left drag over the viewport did not change selection;
- genuine click selection and click/drag policy passed focused tests;
- Frame All and Frame Selected passed for the exact mesh and a restored curve;
- Top, Bottom, Front, Back, Left, Right, and Isometric each rendered with
  finite position, focal point, clipping, and fitted orthographic scale;
- middle/right navigation remained active during Move, Rotate, manual-curve,
  and region modes;
- repeated refreshes and gesture release did not reset or jump the camera.

Tree results:

- real checkbox clicks hid and restored the exact mesh, section plane, and
  curve without changing selection or camera;
- all root/group/curve-group rows were non-checkable;
- repeated/no-op toggles produced no recursive refresh or duplicate undo;
- preview/BREP/active-region families were absent from this project and passed
  the explicit in-memory application/controller coverage instead;
- stale and deliberately failed commands rolled UI state back and surfaced a
  status message.

Overlay/control results:

- no permanent main-scene axes or unidentified white opaque prop remained;
- Move showed constrained transform axes at the selected origin and cancel hid
  them; Rotate additionally showed the ring/angle indicator and cancel hid it;
- the orientation gizmo stayed independent, fixed, non-pickable, and constant
  size through camera movement and project scale;
- every triangular control dispatched its registered named-view action without
  scene picking;
- Show Axis Gizmo and Show View Controls toggled independently;
- resize, maximize, minimize, and restore completed with a valid 934 x 848
  renderer and no render error;
- normal close was clean.

The only subjective release review still recommended is physical-pointer feel
and icon legibility on additional DPI/driver combinations. The tested native
path showed no doubled movement or hypersensitive event duplication.

## Windows PowerShell verification

```powershell
.\.venv-v3\Scripts\Activate.ps1
python -m pip install -e .\packages\workbench_ui
$env:PYTHONPATH = "src;packages/workbench_ui"

python .\scripts\diagnose_vtk_viewport.py
python .\scripts\diagnose_vtk_viewport.py --offscreen
python .\src\main.py

python -m compileall -q src packages\workbench_ui\workbench_ui
python -m unittest tests.test_task77_viewport
python -m unittest tests.test_task79_workbench_ui
python -m unittest tests.test_task80_v3_ui
python -m unittest tests.test_task81_legacy_boundary
python -m unittest tests.test_task82_release
python -m unittest tests.test_task82a_viewport_startup
python -m unittest tests.test_task82b_viewport_interaction
python scripts\report_architecture_metrics.py --fail-on-new
python -m unittest discover -s tests -p "test_*.py"
git diff --check
git status --short
```

## Remaining limitations

- Linux/Xvfb was not available in this Windows workspace. Offscreen behavior
  passed, but no Linux rendering claim is made.
- The exact project does not contain preview surfaces, BREP surfaces, section
  results, or an active region. Their tree visibility paths are covered by
  real controllers and VTK-independent focused tests rather than falsely
  reported as manual project checks.
- Physical-pointer sensitivity and high-DPI visual preference remain release
  sign-off items across hardware, although the real Windows event path,
  logical-pixel hit geometry, and one-event/one-camera-change behavior passed.
- The disconnected components in `TurboBumper.stl` are user source geometry
  and intentionally remain; Task 82B removes unexpected viewport props rather
  than deleting mesh components.

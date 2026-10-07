# Task 82F - Transform Overlays and World-Origin Artifact Cleanup

## Status

Task 82F is complete. Move and Rotate presentation has one focused owner,
transform props do not exist while the viewport has only seen idle snapshots,
and the retained props are non-pickable, non-draggable, and excluded from VTK
visible bounds. The real Windows application and `FrontNoseTest.openretop` were
used for the complete visual and isolation pass.

The required checkpoint was verified before editing:

- branch: `v3-refactor`;
- starting commit, `origin/v3-refactor`, and `v3-task-82e`:
  `328aaba3ecc732f197ea084b2a731eb35bdf32a3`;
- starting subject: `Task 82E: build viewport navigation widget`.

The required commit message is
`Task 82F: repair transform overlays and origin artifacts`. The final SHA is
reported by `git rev-parse HEAD` and in the completion response; a Git commit
cannot contain its own content-addressed SHA. The pre-existing untracked
editable-install metadata under
`packages/workbench_ui/openretop_workbench_ui.egg-info/` was preserved and is
not part of this task.

## Artifact result and exact source

The historical light rectangular/slab-like visual was reproduced in
`FrontNoseTest.openretop`. It is not at world origin and is not an openRetop
overlay. Controlled isolation produced these results:

| Isolation | Slab result |
|---|---|
| transform axes hidden | remained |
| rotation ring hidden | remained |
| grid hidden | remained |
| section planes hidden | remained |
| orientation renderer hidden | remained |
| imported mesh hidden | disappeared |

The exact responsible prop is `scene:mesh:mesh`, a `vtkOpenGLActor` backed by a
`vtkOpenGLPolyDataMapper`. It is the Medium display proxy for
`TurboBumper.stl`, with 122,209 points and 220,000 triangles. Its material is
the configured mesh color `(0.7215686, 0.7411765, 0.7803922)` with opacity 1,
not a white selection or overlay material.

Sparse triangle connectivity found 25 components in that proxy. The component
matching the slab is region 2:

- 15,112 points and 26,947 triangles;
- local bounds: `(-3340.8201, 3823.9731, 252.6355)` to
  `(-3075.3135, 5050.2261, 386.2460)`;
- transformed world bounds: `(-859.4128, -621.9180, 377.6106)` to
  `(-593.9062, 604.3349, 511.2211)`;
- size: `(265.5066, 1226.2529, 133.6105)`.

The imported mesh and display proxy were not changed. Diagnostics now classify
the actor as `imported_scene_geometry`, so it cannot be mistaken for an
unidentified overlay. The empty-project square at origin was also identified:
it is the expected default section-plane scene actor (four points/four line
cells), not a transform prop.

## Transform origin source of truth

For a model transform, the explicit `mesh.origin` remains authoritative. The
new focused conversion applies the object's 4 x 4 transform to
`[origin.x, origin.y, origin.z, 1]`, validates all inputs, and divides XYZ by
the finite nonzero homogeneous weight. If no transform matrix exists, the
explicit finite object location is used. Missing or invalid input returns
`None`; it never becomes `(0, 0, 0)`.

For a section-plane transform, the existing `plane_origin()` result remains
authoritative. No bounding-box center or geometry centroid is substituted.

For the restored test project, the calculation is:

- local origin: `(-2493.4351, 4437.0996, 144.6376)`;
- transform translation: `(2481.4073, -4445.8912, 124.9751)`;
- world origin: `(-12.0278, -8.79155, 269.6127)`.

The actual Move and Rotate prop inventories reported that same world origin.

## Ownership and lifecycle

`TransformOverlayController` in
`src/presentation/qt/transform_overlays.py` is the sole owner of:

- one reusable `vtkAxesActor` for Move;
- one reusable polyline actor containing all Rotate rings;
- constrained-axis styling;
- geometry signatures and reuse;
- transform-overlay diagnostics and shutdown.

`QtSceneViewport` passes each authoritative `SceneSnapshot` to this controller.
The domain continues to own mode, selected target, display axis, true axis
constraint, object origin, angle delta, confirmation, and cancellation.

Actors are created lazily on the first valid active-transform snapshot. An
idle project therefore has no transform props in any renderer. After creation,
both retained props follow the explicit valid origin, including the currently
hidden prop. Confirm, cancel, a disabled `show_axes`, an unsupported mode, or an
invalid origin hides both immediately without discarding the actor objects.
Close removes them before the native render window is finalized.

This lazy-ready lifecycle is also important for suite stability: creating VTK
props in every not-yet-ready test window accumulated native resources. Deferring
them until a valid operation restored clean one-process execution of all 579
tests.

## Idle, Move, and Rotate presentation

Idle contract:

- no Move actor or Rotate actor is created by project load, selection, an
  origin-only update, or repeated idle refresh;
- previously created props are hidden and retained at the last valid origin;
- no transform prop is pickable, draggable, or included in bounds;
- grid, orientation gizmo, and navigation-control settings remain independent.

Move design:

- one world-aligned, caption-free `vtkAxesActor`;
- cylinder shafts and cone tips;
- red X, green Y, and blue Z;
- unconstrained axes have equal length and opacity;
- a constrained axis is 12 percent longer at opacity 1 while the other two
  remain visible at opacity 0.22;
- size is 28 percent of the selected bounds' largest extent, clamped to
  `[0.25, 750]` world units.

Rotate design:

- one actor with three independently colored closed polylines;
- 128 segments per X/Y/Z ring, plus a radial angle indicator;
- unconstrained rings all use full opacity, while a constrained ring remains
  at full opacity and the other two use alpha 58/255;
- radius is 22 percent of the selected bounds' largest extent, clamped to
  `[0.25, 600]` world units;
- the true constraint is separate from the domain's display axis, so an
  unconstrained model Rotate no longer falsely highlights Z;
- Move is hidden for the entire Rotate operation.

The current angle updates polydata only when the angle signature changes. The
inspected screenshots show 22.5-degree unconstrained and 40-degree constrained-Z
feedback. No actor is recreated.

## Framing, picking, geometry, and navigation isolation

Both transform props use `PickableOff()`, `DragableOff()`, and `UseBoundsOff()`.
They never enter `SceneSnapshot.visible_bounds()` or selected bounds. Frame All
and Frame Selected continue to consume only scene item bounds, and tests assert
the exact mesh bounds while overlays are visible.

The callable `QtSceneViewport.renderer_prop_inventory()` traverses every
renderer and prop on demand. It reports semantic category, renderer layer and
viewport, VTK and mapper classes, visibility, pickability, draggable state,
UseBounds, bounds, position, user matrix, color, opacity, representation, line
width, point/cell counts, main-renderer membership, and visible-bounds
contribution. Normal startup does not log this inventory.

`ViewportDiagnosticState.transform_overlay` additionally reports active mode,
display axis, true constraint, requested and actual visibility, world origin,
reference extent, actor creation counts, geometry update count and signature,
actor bounds and renderer membership, picking/drag/bounds flags, hidden reason,
and last error.

Task 82C's `eventFilter` was not modified. Task 82E's navigation cluster,
controls, layout, icons, camera synchronization, and lifecycle were not
modified. Their focused and real visible Windows tests remain green.

## Actual project and prop validation

The exact visible project was:

```text
C:\Users\devan\OneDrive\Desktop\openRetop Tests\FrontNoseTest.openretop
```

It restored one visible 122,209-point / 220,000-triangle mesh, two visible
manual curves, and one hidden section plane. The idle main renderer contained
five props (grid plus four cached scene props), with four visible. It contained
no transform actor. After the first Move, the main renderer contained the same
scene props plus two transform props; only Move was visible. Rotate reused those
same two props, hid Move, and rendered a 386-point/four-cell RGB ring actor.

Across all states, transform props were non-pickable, non-draggable,
`UseBounds=false`, and reported no main-visible-bounds contribution. The mesh
actor remained visible, pickable, opaque, finite, transformed, and unchanged.

## Files changed

Production:

- `src/presentation/qt/transform_overlays.py`: focused controller, origin and
  extent validation, Move styling, three-ring Rotate geometry, reuse, cleanup,
  and diagnostics;
- `src/presentation/qt/viewport.py`: controller integration and complete
  callable renderer-prop inventory;
- `src/presentation/qt/main_window.py`: finite homogeneous model-origin helper;
- `src/viewer/scene_types.py` and `src/viewer/scene_builder.py`: separate true
  transform constraint in scene presentation state.

Tests and evidence:

- `tests/test_transform_overlays.py`: grouped coverage for all 46
  required idle, Move, Rotate, artifact, framing, camera, lifecycle, and visible
  Win32 requirements;
- `tests/test_viewport_interaction.py`: updated obsolete single-ring
  and eager-idle-prop expectations for the new presentation contract;
- seven inspected screenshots under `docs/v3/artifacts/task-82f/`;
- `docs/v3/STATUS.md` and this report.

No generic workbench, startup lifecycle, transform-domain math, imported mesh,
scene-tree behavior, persistence schema, geometry algorithm, Task 82C routing,
or Task 82E navigation source was changed.

## Automated verification

Environment:

- Windows 10.0.26200.0;
- Python 3.11.9;
- PySide6 6.11.1;
- VTK 9.6.2;
- render window: `vtkWin32OpenGLRenderWindow`;
- renderer: `vtkOpenGLRenderer`;
- screenshot DPR: 1.25.

Required focused results on the visible Windows Qt platform:

- Task 82A: 18/18 in 1.715 seconds;
- Task 82B: 26/26 in 4.519 seconds;
- Task 82C: 15/15 in 2.427 seconds, unchanged;
- Task 82D: 13/13 in 3.308 seconds;
- Task 82E: 11/11 in 3.032 seconds, unchanged;
- Task 82F: 12/12 in 2.359 seconds, no skips;
- Task 79: 9/9 in 0.284 seconds;
- Task 80: 7/7 in 1.238 seconds;
- Task 81: 5/5 in 0.348 seconds;
- Task 82: 5/5 in 0.005 seconds.

Complete visible Windows discovery passed 579 tests with no skips in 21.746
seconds. Compileall and architecture verification passed. Architecture reported
109 production Python files, 59 test files, zero dependency violations, zero
practical cycles, zero legacy-window methods, and zero duplicate detectable
labels. `git diff --check` passed after the final documentation update.

## Real visible Windows acceptance

The real `OpenRetopV3Window` was shown against the Windows QVTK native child;
the screenshots combine the actual Qt shell with the actual QVTK framebuffer.
The render window was `vtkWin32OpenGLRenderWindow`, not offscreen or a fake.

The pass covered empty and restored projects, selection-only idle, Move
unconstrained and X/Y/Z, confirm, cancel, Rotate unconstrained and X/Y/Z,
live angle updates, repeated refreshes, camera preservation, resize,
maximize/restore, minimize/restore, and actor identity/count preservation. Task
82C's real Win32 suite covered click selection, left orbit, middle pan, wheel
zoom, and tool arbitration. Task 82E's real Win32 suite covered all navigation
buttons, both roll controls, orientation synchronization, and window states.

All seven committed screenshots were reopened and inspected after the final
capture:

- [idle](../artifacts/task-82f/idle.png);
- [Move unconstrained](../artifacts/task-82f/move-unconstrained.png);
- [Move constrained to X](../artifacts/task-82f/move-X.png);
- [Rotate unconstrained with 22.5-degree feedback](../artifacts/task-82f/rotate-unconstrained.png);
- [Rotate constrained to Z with 40-degree feedback](../artifacts/task-82f/rotate-Z.png);
- [after cancel](../artifacts/task-82f/after-cancel.png);
- [artifact isolation with imported mesh hidden](../artifacts/task-82f/artifact-isolation.png).

The idle and after-cancel images contain no transform visual. The Move images
show one three-axis origin overlay. The Rotate images show three smooth RGB
rings without the Move actor. Comparing idle to artifact isolation shows that
the light slab disappears with the imported mesh while the grid, curves, and
top-left navigation remain.

## Windows PowerShell verification

```powershell
.\.venv-v3\Scripts\Activate.ps1
python -m pip install -e .\packages\workbench_ui
$env:PYTHONPATH = "src;packages/workbench_ui"

python -m compileall -q src packages\workbench_ui\workbench_ui
python -m unittest tests.test_viewport_startup
python -m unittest tests.test_viewport_interaction
python -m unittest tests.test_viewport_mouse_orbit
python -m unittest tests.test_orientation_gizmo
python -m unittest tests.test_navigation_widget
python -m unittest tests.test_transform_overlays
python -m unittest tests.test_workbench_ui_framework
python -m unittest tests.test_main_window_workflows
python -m unittest tests.test_entry_points_and_legacy_removal
python -m unittest tests.test_release_fixtures_and_composition
python scripts\report_architecture_metrics.py --fail-on-new
python -m unittest discover -s tests -p "test_*.py"
python .\src\main.py
git diff --check
git status --short
```

For visible verification, do not set `QT_QPA_PLATFORM=offscreen`.

## Remaining limitations

- Linux/Xvfb was not available in this Windows workspace, so no Linux visible
  rendering claim is made.
- The imported slab is valid user mesh data. Removing or repairing it would be
  a separate, user-authorized mesh-cleanup task.
- Physical-pointer feel, mixed-monitor DPI transitions, and additional GPU/
  driver combinations remain release-hardware review. Native Windows input and
  rendering were functionally exercised here.

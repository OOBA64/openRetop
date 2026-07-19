# Task 82E - Build the Viewport Navigation Widget

## Status

Task 82E is complete. The V3 viewport now has one compact top-left navigation
cluster containing a clear X/Y/Z orientation gizmo, four unlettered directional
triangles, a clickable central isometric target, and two 15-degree roll controls.
The cluster has one lifecycle owner, respects the two existing visibility
settings independently, and preserves Task 82C's native QVTK mouse route.

The checkpoint was verified before editing:

- branch: `v3-refactor`;
- starting commit and `origin/v3-refactor`:
  `48238454de9008fe934f2b3235f77ef11b7cc260`;
- starting subject: `Task 82D: restore orientation gizmo`;
- `v3-task-82c`: `32f3eb68f2f948e44263b0af7e995eb02ea25b1a`.

The required commit message is `Task 82E: build viewport navigation widget`.
The final SHA is reported by `git rev-parse HEAD` and in the completion response;
a Git commit cannot contain its own content-addressed SHA. The pre-existing
untracked editable-install metadata at
`packages/workbench_ui/openretop_workbench_ui.egg-info/` was preserved and is
not part of this task.

## Reproduction and demonstrated root cause

The actual Windows startup path used repository source, PySide6 6.11.1, VTK
9.6.2, and `vtkWin32OpenGLRenderWindow`; no stale package or alternate source
tree was involved. The persisted user settings at reproduction time contained:

```json
{
  "show_axis_gizmo": false,
  "show_viewcube": true
}
```

Consequently, the normal application had a valid layer-1 overlay renderer but
its draw state and axes visibility were false. The scene renderer was healthy,
and the old seven lettered controls remained visible. At DPR 1.25 and a
1354 x 949 physical render window, the disabled gizmo viewport was finite and
in bounds, its independent camera was at `(0, 0, 4)` with parallel scale `0.82`,
and the actor retained finite bounds and total length `0.86`. This ruled out
backend registration, layer ordering, camera validity, DPI placement, resize
timing, and stale installation as the reason it was absent.

Temporarily enabling the setting proved Task 82D could render, but also showed
the secondary usability defect: the colored actor occupied only 61 x 65
physical pixels and contained 174 red, 155 green, and 54 blue classified pixels.
The seven `T/B/F/K/L/R/I` triangles formed a separate, visually dominant layout.
The user's observation was therefore caused primarily by the persisted disabled
setting, with a real presentation weakness when enabled. Task 82E addresses both
without globally overriding or rewriting the user's setting.

## Ownership and lifecycle

`ViewportNavigationCluster` in `src/presentation/qt/view_controls.py` is the one
navigation-cluster owner. It coordinates the Task 82D
`OrientationGizmoController` and all Qt hit targets, but it does not own scene
synchronization, picking, or native gestures.

`QtSceneViewport` constructs the cluster once, starts it after VTK readiness,
forwards snapshot visibility and camera synchronization, and asks it to update
layout on resize or device-pixel-ratio change. The cluster attaches one overlay
renderer, creates its Qt controls once, registers one interaction observer,
reuses everything across refreshes and window-state changes, and detaches during
viewport close. Compatibility aliases preserve the existing viewport test and
presentation surface while the cluster remains the sole lifecycle/layout owner.

The generic `workbench_ui` QVTK host was not changed. The Task 82C `eventFilter`,
TrackballCamera ownership, four-logical-pixel click/drag arbitration, middle pan,
wheel zoom, right-button behavior, and tool capture were not changed.

## Final visual design and layout

The cluster is a transparent, screen-space presentation at a 12-logical-pixel
top-left margin:

```text
              triangle: Top
 triangle: Left   [104 px X/Y/Z gizmo]   triangle: Right
              triangle: Bottom

             roll left       roll right
```

- orientation viewport: 104 x 104 logical pixels;
- directional triangles: 20 x 20 logical pixels;
- roll targets: 24 x 24 logical pixels;
- central isometric target: 28 x 28 logical pixels;
- complete logical bounds: 148 x 175 pixels;
- no opaque container or backing rectangle.

The axes now use stronger red, green, and blue geometry, thicker cylinder
shafts, larger cone tips, higher source resolution, and 16-pixel X/Y/Z captions.
The central circular plate paints an independent isometric-cube glyph, subtle
hover/pressed states, and a color-coded endpoint letter when an axis is nearly
end-on. Its VTK actor remains noninteractive and non-pickable.

Each triangle has a polygon mask and matching `hitButton()` region; transparent
corners do not consume input. The two roll buttons have elliptical masks and
painted counterclockwise/clockwise arrows. Only visible child controls intercept
input. All controls expose tooltips and accessible names.

## Action mapping and camera roll

The deliberately fixed canonical mapping is:

| Visual control | Application action |
|---|---|
| top triangle | `view.named.top` |
| bottom triangle | `view.named.bottom` |
| left triangle | `view.named.left` |
| right triangle | `view.named.right` |
| central gizmo plate | `view.named.isometric` |
| counterclockwise arrow | `view.roll_left` |
| clockwise arrow | `view.roll_right` |

This matches the widget's canonical/default visual language and is deterministic
after any orbit or roll: a triangle requests the named world view indicated by
its screen position, while the center restores isometric. No old Front, Back,
or seventh Isometric triangle remains.

Roll is implemented through the application action registry and a typed
`CameraRequest`, not by the button. `CameraController.roll()` applies Rodrigues
rotation to normalized view-up around the current direction of projection, then
orthogonalizes the camera basis. Left uses -15 degrees and right uses +15
degrees. Position, focal point, distance, projection mode, and parallel scale
remain unchanged. Unit and visible tests cover parallel and perspective modes,
inverse rolls, repeated accumulation, named/isometric requests, and gizmo
synchronization.

## Visibility settings

The existing settings remain independent and retain their existing persistence
path:

| `show_axis_gizmo` | `show_viewcube` | Result |
|---|---|---|
| on | on | complete cluster |
| on | off | VTK X/Y/Z gizmo only |
| off | on | controls plus central isometric fallback plate |
| off | off | no cluster |

Task 82E does not force either setting. Changing display settings updates the
same cluster and never recreates an actor, renderer, observer, or control.

## Files changed

Production:

- `src/presentation/qt/orientation_gizmo.py`: stronger 104-pixel gizmo styling
  and cluster-relative DPI-aware layout;
- `src/presentation/qt/view_controls.py`: unified cluster, four masked
  triangles, two roll controls, central isometric target, layout, visibility,
  lifecycle, and diagnostics;
- `src/presentation/qt/viewport.py`: single cluster integration;
- `src/presentation/qt/main_window.py`: roll action-to-request dispatch;
- `src/application/actions.py` and `src/application/workflow_service.py`:
  centralized roll actions and presentation routing;
- `src/viewer/scene_types.py` and `src/viewer/camera_controller.py`: typed roll
  request and finite camera roll operation.

Tests and evidence:

- `tests/test_task82e_navigation_widget.py`: focused unit, lifecycle, layout,
  action, camera, rendered-pixel, and visible Win32 coverage;
- `tests/test_task82b_viewport_interaction.py`: the obsolete hard-coded
  96-pixel expectation now uses the shared gizmo-size constant;
- `docs/v3/artifacts/task-82e/default.png`;
- `docs/v3/artifacts/task-82e/maximized.png`;
- `docs/v3/artifacts/task-82e/rolled-right-15deg.png`;
- `docs/v3/artifacts/task-82e/controls-hidden.png`;
- `docs/v3/artifacts/task-82e/gizmo-hidden.png`;
- `docs/v3/STATUS.md` and this report.

No generic workbench code, project schema, scene tree, geometry, persistence,
framing algorithm, transform controller, or production diagnostic actor was
changed.

## Automated verification

Environment:

- Windows 10.0.26200.0;
- Python 3.11.9;
- PySide6 6.11.1;
- VTK 9.6.2;
- render window: `vtkWin32OpenGLRenderWindow`;
- scene and overlay renderer: `vtkOpenGLRenderer`;
- visual-acceptance DPR: 1.25.

Required focused results on the visible Windows Qt platform:

- Task 82A: 18/18 in 1.751 seconds;
- Task 82B: 26/26 in 3.815 seconds;
- Task 82C: 15/15 in 2.703 seconds, unchanged;
- Task 82D: 13/13 in 3.287 seconds;
- Task 82E: 11/11 in 2.978 seconds;
- Task 79: 9/9 in 0.406 seconds;
- Task 80: 7/7 in 1.350 seconds;
- Task 81: 5/5 in 0.333 seconds;
- Task 82: 5/5 in 0.005 seconds.

The first Task 80 invocation omitted the required `PYTHONPATH` and therefore
failed at test import; rerunning the exact required command with
`PYTHONPATH=src;packages/workbench_ui` passed 7/7. No application failure was
hidden or converted to a skip.

Complete visible Windows discovery passed 567 tests with no skips in 21.504
seconds. It ended without an unhandled traceback or late WGL error.

Additional checks:

- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed;
- `python scripts/report_architecture_metrics.py --fail-on-new`: passed;
- architecture: 108 production files / 34,422 lines, 58 test files / 16,370
  lines, 56 `OpenRetopV3Window` methods, zero legacy-window methods, zero
  dependency violations, zero practical cycles, and zero duplicate detectable
  action/menu labels;
- `git diff --check`: passed after the final documentation update.

The focused Task 82E tests cover the requested behavior in grouped cases:
single creation/attachment/observer, enabled defaults, RGB rendered pixels and
minimum footprint, transparency, camera signatures, four exact directional
controls, no letters or old actions, two roll controls, central activation,
precise hit regions, hover/press/accessibility, no scene picks, all visibility
combinations, compact two-size and three-DPR layout, primary-prop/bounds
isolation, perspective/parallel roll invariants, inverse/repeated rolls,
registered request routing, transform-overlay separation, and real visible
Win32 pixels/window states.

## Real visible Windows acceptance

The exact project was:

```text
C:\Users\devan\OneDrive\Desktop\openRetop Tests\FrontNoseTest.openretop
```

It visibly restored `TurboBumper.stl`, two manual curves, a section plane, and
the grid. The final layer-1 gizmo contained 410 red, 282 green, and 330 blue
classified pixels, zero white pixels, and a 76 x 72 physical colored footprint
at DPR 1.25. This is larger and substantially denser than the measured Task 82D
61 x 65 footprint. The cluster reported one actor, renderer, controller, and
observer with no last render or cluster error.

All four triangles produced their documented camera directions. The center
produced isometric without a pick. The right roll measured
14.999999999999996 degrees while preserving camera position, focal point, and
distance; the orientation signature changed. A real rendered-project click
selected scene geometry, while control clicks did not. Native left orbit,
middle pan, and wheel zoom remained functional. Independent setting states,
normal/maximized/minimized/restored sizes, repeated refresh, and clean close all
passed without duplication or layout drift.

All five screenshots were opened and inspected after capture. They show the
actual running Qt shell and QVTK framebuffer, not synthetic geometry or an
unrelated mockup:

- [default window](../artifacts/task-82e/default.png);
- [maximized window](../artifacts/task-82e/maximized.png);
- [after right roll](../artifacts/task-82e/rolled-right-15deg.png);
- [controls hidden](../artifacts/task-82e/controls-hidden.png);
- [gizmo hidden](../artifacts/task-82e/gizmo-hidden.png).

## Windows PowerShell verification

```powershell
.\.venv-v3\Scripts\Activate.ps1
python -m pip install -e .\packages\workbench_ui
$env:PYTHONPATH = "src;packages/workbench_ui"

python -m compileall -q src packages\workbench_ui\workbench_ui
python -m unittest tests.test_task82a_viewport_startup
python -m unittest tests.test_task82b_viewport_interaction
python -m unittest tests.test_task82c_mouse_orbit
python -m unittest tests.test_task82d_orientation_gizmo
python -m unittest tests.test_task82e_navigation_widget
python -m unittest tests.test_task79_workbench_ui
python -m unittest tests.test_task80_v3_ui
python -m unittest tests.test_task81_legacy_boundary
python -m unittest tests.test_task82_release
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
- Visible acceptance used Windows DPR 1.25. DPR 1.0 and 1.5 layout math is
  automated, but a physical mixed-DPI monitor transition remains release-
  hardware review.
- The fixed triangle mapping is world-named rather than dynamically remapped
  after arbitrary camera roll. This is deliberate and documented; changing it
  would require a separate interaction-language decision.
- Physical-pointer feel and additional GPU/driver combinations remain subjective
  release review. The functional visible path was genuinely exercised through
  the native QVTK child.

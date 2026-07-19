# Task 82D - Restore the Fixed Top-Left Orientation Gizmo

## Status

Task 82D is complete. The V3 viewport now presents one readable, transparent,
noninteractive X/Y/Z indicator at a fixed 96-logical-pixel size and 12-logical-
pixel top-left margin. It tracks camera orientation, remains independent of
scene geometry and transform overlays, and does not alter Task 82C input
routing.

The checkpoint was verified before editing:

- branch: `v3-refactor`;
- starting commit: `32f3eb68f2f948e44263b0af7e995eb02ea25b1a`;
- checkpoint tag: `v3-task-82c`;
- tag commit: `32f3eb68f2f948e44263b0af7e995eb02ea25b1a`.

The required commit message is `Task 82D: restore orientation gizmo`. The final
commit SHA is reported by `git rev-parse HEAD` and in the completion response;
a Git commit cannot contain its own content-addressed SHA.

The pre-existing untracked editable-install metadata under
`packages/workbench_ui/openretop_workbench_ui.egg-info` was preserved and is
not part of Task 82D.

## Root cause and baseline

Task 82B did construct a layer-1 `vtkAxesActor`, so the defect was not a missing
Python object or a renderer that was wholly detached. Direct visible Windows
reproduction showed why that construction-only evidence was misleading:

- the actor used short `0.72` axes with a `1.15` parallel scale;
- all axis labels were disabled;
- in the front view, Z was end-on and the remaining red/green lines occupied
  only about 35 physical pixels;
- the adjacent triangular controls were visually dominant;
- ownership, layout, camera observation, diagnostics, and shutdown were mixed
  into `QtSceneViewport` instead of forming a testable presentation lifecycle;
- no real rendered-pixel test had proved colored, readable gizmo output.

The result was technically an actor but not a usable orientation gizmo. The
baseline screenshot looked like a tiny unlabeled red/green L beside the named-
view buttons, matching the reported absence of a persistent X/Y/Z indicator.

Read-only comparison with `origin/main:src/viewer/embedded_viewport.py` and
commits `98368287` and `7e08b998` confirmed that a dedicated transparent
renderer, independent parallel camera, and reused actor were the stable design
to retain. No legacy Tk code was restored.

## Ownership and lifecycle

`OrientationGizmoController` in
`src/presentation/qt/orientation_gizmo.py` is the sole openRetop-specific gizmo
owner. The generic `workbench_ui.VTKViewportWidget` remains unchanged and owns
only QVTK construction, the main render window/renderer/interactor, and native
startup/finalization.

After the viewport becomes ready, `QtSceneViewport` starts the controller. The
controller then:

1. creates one overlay renderer and one `vtkAxesActor`;
2. selects the first unoccupied renderer layer above layer 0;
3. increases the render-window layer count only if that layer requires it;
4. attaches the renderer only if it is not already attached;
5. registers one interactor `InteractionEvent` observer;
6. applies the current display setting, viewport layout, and camera orientation.

Repeated ready signals, snapshots, settings toggles, camera changes, and
refreshes reuse those objects. On close, the controller removes its observer,
disables drawing, releases overlay graphics resources while the Win32 context
is valid, detaches its renderer, and clears toolkit references. An accepted
`OpenRetopV3Window` close now explicitly closes its child viewport because Qt
otherwise hides the child without sending it a close event. This is a shutdown
repair only; application startup and Task 82C gesture routing are unchanged.

## Renderer and actor configuration

The observed normal arrangement is:

- layer 0: the existing `vtkOpenGLRenderer` for scene, grid, and world-space
  transform overlays;
- layer 1: one dedicated `vtkOpenGLRenderer` containing only the orientation
  actor.

If another renderer already occupies layer 1, the controller chooses the next
free higher layer without changing the primary renderer.

The overlay renderer uses `InteractiveOff()`, alpha `0`, preserved color,
non-preserved depth, `EraseOff()`, and no opaque backing prop. The actor is one
non-pickable, non-draggable `vtkAxesActor` with restrained cylinder shafts and
cone tips. X/Y/Z labels are enabled with transparent caption backgrounds and
red, green, and blue text. Total axis length is `0.86`, normalized shaft/tip
lengths are `0.72`/`0.28`, and the overlay parallel scale is `0.82`.

The overlay does not enter the primary renderer's props, scene bounds, snapshot,
actor cache, picking service, selection, or project serialization. It therefore
cannot affect Frame All or Frame Selected. Transform axes and the rotation ring
remain ordinary primary-renderer overlays controlled by transform state.

## Layout and DPI behavior

`normalized_gizmo_viewport()` derives normalized coordinates from physical
render-window dimensions and the Qt device-pixel ratio:

```text
size_pixels   = min(96 * DPR, render_width, render_height)
margin_pixels = 12 * DPR, clamped so the square stays in bounds
```

The square is anchored from the top-left by converting that pixel rectangle to
VTK's bottom-left normalized viewport coordinates. Zero, nonfinite, and invalid
dimensions return safely. Resize and `DevicePixelRatioChange` events recalculate
the rectangle only when it changed. The existing Task 82B controls are offset
to start 8 logical pixels to the right of the enabled gizmo; their behavior and
implementation were not changed.

Visible acceptance at DPR `1.25` measured approximately 96 x 96 logical pixels
at initial, horizontal-resize, vertical-resize, maximized, restored, and
minimize/restored sizes. The accepted project run placed the controls at logical
x `116`, after the gizmo's x `12..108` rectangle and its 8-pixel gap.

## Camera synchronization and settings

The overlay camera is separate from the scene camera. It focuses on the origin,
uses a fixed distance of `4.0`, parallel projection, and a fixed parallel scale.
The main camera's direction-of-projection and view-up vectors are normalized;
view-up is orthogonalized with a finite fallback basis. Their rounded values
form a cached orientation signature.

One `InteractionEvent` observer updates the signature during native camera
interaction. Known programmatic camera requests also synchronize explicitly
after scene actors and camera state are applied. Orbit and named views update
the overlay. Pure pan and wheel zoom leave its orientation signature unchanged.
No update causes a scene refresh or installs another observer.

`settings.display.show_axis_gizmo` continues through the existing display
snapshot as `show_axis_gizmo`. The controller sets both actor visibility and
renderer draw state. Repeated off/on toggles restore the same actor, renderer,
camera, and observer. View-control and transform-overlay visibility remain
independent.

Structured viewport diagnostics now include enabled/attached state, renderer
layer and viewport, transparency/draw/interaction state, actor visibility and
pickability, orientation signature, observer and creation counts, camera and
layout update counts, and the last controller error.

## Files changed

Production:

- `src/presentation/qt/orientation_gizmo.py` (new focused controller);
- `src/presentation/qt/viewport.py` (controller integration, settings, camera,
  resize/DPI, diagnostics, and compatibility views);
- `src/presentation/qt/main_window.py` (deterministic accepted-close shutdown).

Tests and evidence:

- `tests/test_task82d_orientation_gizmo.py` (new);
- `tests/test_task82b_viewport_interaction.py` (only its factually invalid
  120 x 30 synthetic-surface coordinate assumption was corrected);
- `docs/v3/artifacts/task-82d-orientation-gizmo.png` (visible acceptance);
- `docs/v3/STATUS.md` and this report.

No workbench-specific policy, Task 82E control, production test geometry,
alternate interactor, camera-framing change, scene-tree change, persistence
change, or Tk code was added.

## Automated verification

Environment:

- Windows 10.0.26200.0;
- Python 3.11.9;
- PySide6 6.11.1;
- VTK 9.6.2;
- render window: `vtkWin32OpenGLRenderWindow`;
- primary/overlay renderer class: `vtkOpenGLRenderer`;
- device pixel ratio: 1.25 during visual acceptance.

Required focused results on the visible Windows Qt platform:

- `tests.test_task82a_viewport_startup`: 18 passed in 1.609 seconds;
- `tests.test_task82b_viewport_interaction`: 26 passed in 3.074 seconds;
- `tests.test_task82c_mouse_orbit`: 15 passed in 2.450 seconds;
- `tests.test_task82d_orientation_gizmo`: 13 passed in 3.043 seconds;
- `tests.test_task79_workbench_ui`: 9 passed in 0.360 seconds;
- `tests.test_task80_v3_ui`: 7 passed in 1.459 seconds;
- `tests.test_task81_legacy_boundary`: 5 passed in 0.327 seconds;
- `tests.test_task82_release`: 5 passed in 0.004 seconds.

The complete visible Windows discovery passed 556 tests with no skips in
15.745 seconds. It ended cleanly without a traceback or late Win32 WGL error.

Additional checks:

- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed;
- `python scripts/report_architecture_metrics.py --fail-on-new`: passed;
- architecture: 108 production files / 34,002 lines, 57 test files / 15,826
  lines, 56 `OpenRetopV3Window` methods, zero legacy-window methods, zero
  dependency violations, zero practical cycles, and zero duplicate detectable
  action/menu labels;
- `git diff --check`: passed after the final documentation update.

The 13 Task 82D tests cover single creation/attachment, layer conflicts,
transparency, noninteractivity/non-pickability, visibility independence,
primary-prop/bounds/picking isolation, separate cameras, observer lifecycle,
orbit/pan/zoom/named-view signatures, fixed logical sizing, invalid dimensions,
high-DPI math, pointer pass-through, deterministic main-window shutdown, and a
real visible Win32 rendered-pixel/interaction/window-state test.

## Real visible Windows acceptance

The exact project was:

```text
C:\Users\devan\OneDrive\Desktop\openRetop Tests\FrontNoseTest.openretop
```

It restored `TurboBumper.stl`, two manual curves, and one section plane. The
shown QVTK viewport used `vtkWin32OpenGLRenderWindow`, two renderers, and one
layer-1 gizmo. Direct back-buffer validation of the 96-pixel overlay region
found 177 red, 142 green, and 155 blue axis pixels and zero white pixels.

Top, Front, Right, and Isometric produced the expected finite signatures.
Injected left drag begun over the gizmo area still reached Task 82C native orbit
and changed both main-camera and gizmo orientation. Middle pan and wheel zoom
left the orientation signature unchanged. Selection, checkbox visibility,
Frame All, Frame Selected, project refresh, Move/Rotate, Enter/Escape, and the
show-axis-gizmo off/on toggle did not recreate or relocate it. Resize, maximize,
restore, minimize, and restore retained one actor, one renderer, one observer,
constant logical size, and no render error.

An additional genuinely empty visible project run directly inspected the VTK
back buffer. It showed the configured `#101316` background, grid, and labeled
X/Y/Z gizmo with one observer/creation and no rendering error. No diagnostic
geometry was inserted.

The inspected artifact is
[`task-82d-orientation-gizmo.png`](../artifacts/task-82d-orientation-gizmo.png).
It shows the complete application, restored model/grid, the fixed labeled
top-left gizmo, no idle transform axes, and no white backing rectangle.

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

- Linux/Xvfb was not available in this Windows workspace, so no Linux visible-
  rendering claim is made.
- The fixed-size/DPI calculations are covered with multiple synthetic ratios,
  and the visible run used DPR 1.25. A physical move between two monitors with
  different scaling was not available; the `DevicePixelRatioChange` path is
  implemented and remains a release-hardware check.
- Injected Qt input objectively exercised the real native QVTK path. Physical-
  pointer feel and additional GPU/driver combinations remain subjective release
  review, not a missing functional acceptance item.
- Task 82E's triangular and rotation controls are intentionally outside this
  task. Task 82D only reserves an 8-logical-pixel adjacent gap.

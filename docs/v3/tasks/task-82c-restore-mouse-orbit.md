# Task 82C - Restore Native Mouse Orbit

## Status

Task 82C is complete. Ordinary unmodified left drag again orbits through the
shown native QVTK widget and `vtkInteractorStyleTrackballCamera`. True click
selection, manual-curve input, region input, and transform input remain
available without introducing a second camera implementation.

The repair was verified with injected Qt mouse and wheel events against a real
visible Windows QVTK child, both with focused synthetic geometry and with the
exact `FrontNoseTest.openretop` project. This was not an offscreen or fake-camera
substitute.

Base commit: `d90bb4500de8e142e239222303065f0644811f3a` on
`v3-refactor`.

Repair commit message: `Task 82C: restore native mouse orbit`.

The repair commit's SHA is reported by `git rev-parse HEAD` after this document
is committed. A commit cannot contain its own content-addressed SHA.

## Baseline and investigation

After fetch/prune and fast-forward pull, the local branch, `HEAD`, and
`origin/v3-refactor` all resolved to the required base. The existing untracked
editable-install metadata under
`packages/workbench_ui/openretop_workbench_ui.egg-info` was preserved and is
not part of this commit.

The installed VTK 9.6.2
`vtkmodules.qt.QVTKRenderWindowInteractor.QVTKRenderWindowInteractor` source
already implements the native Qt route:

- `mousePressEvent()` calls the generic VTK interactor's
  `LeftButtonPressEvent()`;
- `mouseMoveEvent()` updates VTK event information and calls
  `MouseMoveEvent()`;
- `mouseReleaseEvent()` calls `LeftButtonReleaseEvent()`;
- wheel input calls the corresponding native VTK wheel event.

Qt runs an installed event filter before the target widget handler. Returning
`True` from the filter consumes the event; returning `False` allows the QVTK
handler above to execute.

Task 82B's filter returned `True` for every unmodified left press, move, and
release. It emitted openRetop `left_press`, `motion`, and `left_release` signals
instead. Consequently:

1. the native TrackballCamera received no ordinary left press;
2. it received no left-drag motion;
3. it received no matching release;
4. application selection/tool policy ran in place of the native gesture;
5. native event duplication was not the failure - the native event count was
   zero;
6. middle/right/modified-left routes still worked because Task 82B explicitly
   allowed those events through.

A pre-edit visible Win32 reproduction used the real `QtSceneViewport`, its
`vtkInteractorStyleTrackballCamera`, and an 80 x 40 logical-pixel left drag.
Camera position, focal point, view-up, and direction were unchanged, while the
application received all three pointer events. That isolated the regression to
event arbitration rather than backend startup, actor synchronization, camera
math, or rendering.

The read-only historical implementations were also compared. Commit
`e6761fcd` and `origin/main:src/viewer/embedded_viewport.py` first offered a
gesture to the active application tool, forwarded it to VTK when not consumed,
and selected only after native release when movement remained within four
pixels. Task 82C restores that ownership contract without restoring the Tk
viewport or manually forwarding QVTK events in parallel.

## Repaired event path

There is exactly one camera owner: the existing QVTK child plus its one
`vtkInteractorStyleTrackballCamera`.

When no left-capture tool is active, the path is:

```text
Qt left press
  -> QtSceneViewport records gesture state and returns False
  -> QVTK mousePressEvent
  -> vtkGenericRenderWindowInteractor.LeftButtonPressEvent
  -> vtkInteractorStyleTrackballCamera

Qt left move
  -> QtSceneViewport accumulates logical-pixel distance
  -> movement > 4 permanently invalidates selection
  -> filter returns False; no pick, refresh, or CameraRequest
  -> QVTK forwards one MouseMoveEvent to TrackballCamera

Qt left release
  -> filter classifies click versus drag and returns False
  -> QVTK forwards one LeftButtonReleaseEvent and ends interaction
  -> only a still-eligible click schedules one application left_release
  -> application performs one final scene-object pick and selection
```

The zero-delay callback is one release-order deferral, not a camera or render
path. It ensures native release has completed before selection can synchronize
scene style. Drag release schedules nothing.

When a tool owns left input, `QtSceneViewport` consumes the complete ordinary
left press/move/release sequence and emits it to application policy. It never
forwards that same sequence to VTK. Ownership is recomputed from authoritative
controller state on each application refresh, with this priority:

1. active transform;
2. active manual-curve session;
3. active region session;
4. no owner.

Middle, right, wheel, Shift+left, and Alt+left remain native even while a tool
owns ordinary left input. Tool ownership captured at press remains stable for
that gesture.

## Gesture state and threshold

`PointerGestureState` now records:

- press button;
- press and current logical positions;
- accumulated Euclidean movement;
- the four-logical-pixel click threshold;
- active tool owner at press;
- whether native interaction began;
- permanent selection eligibility;
- whether the gesture crossed into drag.

A cumulative distance of exactly 4.0 logical pixels remains click-eligible.
Any accumulated distance greater than 4.0 marks the gesture as drag and
selection cannot become eligible again, even if the pointer returns near its
press position. A tool-owned gesture is never scene-selection eligible.

The structured viewport diagnostics expose the owner, active/native state,
selection eligibility, and accumulated distance alongside the existing actor,
snapshot, render-window, and error information.

## Scope and files changed

Modified production files:

- `src/presentation/qt/pointer_gestures.py`
- `src/presentation/qt/viewport.py`
- `src/presentation/qt/main_window.py`

Modified tests/documentation:

- `tests/test_task82b_viewport_interaction.py`
- `tests/test_task82c_mouse_orbit.py` (new)
- `docs/v3/STATUS.md`
- `docs/v3/tasks/task-82c-restore-mouse-orbit.md` (new)

The Task 82B test edits only replace its superseded assertion that ordinary
left drag must not navigate. Its scene-tree visibility, controls, overlay,
framing, and selection-preservation checks are unchanged.

No production test actor, alternate camera implementation, extra renderer,
mesh/schema change, scene refresh on native motion, or Tk dependency was added.

## Automated verification

Environment:

- Windows version 10.0.26200.0
- Python 3.11.9
- PySide6 6.11.1
- VTK 9.6.2
- render window: `vtkWin32OpenGLRenderWindow`
- renderer: `vtkOpenGLRenderer`
- style: `vtkInteractorStyleTrackballCamera`

Focused final results:

- `tests.test_task79_workbench_ui`: 9 passed in 1.552 seconds.
- `tests.test_task80_v3_ui`: 7 passed in 2.089 seconds.
- `tests.test_task82a_viewport_startup`: 18 passed with no skips on visible
  Windows in 1.684 seconds.
- `tests.test_task82b_viewport_interaction`: 26 passed with no skips on visible
  Windows in 3.366 seconds.
- `tests.test_task82c_mouse_orbit`: 15 passed with no skips on visible Windows
  in 2.518 seconds.
- Task 82C offscreen run: 14 passed and the one real-visible-Windows test
  skipped in 2.093 seconds.

Complete discovery on the real visible Windows Qt platform passed 543 tests
with no skips in 16.129 seconds.

Additional checks:

- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed.
- `python scripts/report_architecture_metrics.py --fail-on-new`: passed with
  zero dependency violations, practical cycles, and duplicate action/menu
  labels.
- Architecture metrics: 107 production files / 33,523 lines, 56
  `OpenRetopV3Window` methods, and zero legacy-window methods.
- `git diff --check`: passed.

The new focused coverage proves:

- TrackballCamera style preservation and idempotent viewport start;
- ordinary left events bypass application policy exactly once;
- horizontal and vertical orientation change, not merely distance change;
- drag-over-mesh orbit;
- release without camera snap or selection;
- one final pick for a true click;
- no idle-motion pick;
- no refresh, scene synchronization, actor recreation, or CameraRequest during
  native orbit;
- exact one-call QVTK-to-VTK forwarding at the public interactor boundary;
- middle pan and wheel zoom;
- manual-curve, region, and transform left ownership;
- middle and wheel navigation during an active tool;
- finite state over ten repeated orbit gestures;
- retained Task 82B checkbox selection behavior;
- retained Task 82A visible startup behavior.

## Real Windows project acceptance

The exact project was:

```text
C:\Users\devan\OneDrive\Desktop\openRetop Tests\FrontNoseTest.openretop
```

It loaded the referenced `TurboBumper.stl` and synchronized one mesh, two
curves, and one section plane. The viewport reported 12 current renderer actors
including scene and presentation props, finite visible bounds, and no rendering
error.

The shown native window used properly injected Qt gestures against the QVTK
child. A mesh pixel was first confirmed with the structured scene picker, then
the orbit began at that pixel. The horizontal orbit recorded:

| Camera value | Before | After |
| --- | --- | --- |
| Position | `(-12.027768, -8.791549, 5979.220088)` | `(-2399.865301, -8.791549, 5455.926267)` |
| Focal point | `(-12.027768, -8.791549, 269.612721)` | `(-12.027768, -8.791549, 269.612721)` |
| View up | `(0.0, 1.0, 0.0)` | `(0.0, 1.0, 0.0)` |
| Direction | `(0.0, 0.0, -1.0)` | `(0.418214, 0.0, -0.908349)` |
| Distance | `5709.607367` | `5709.607367` |

The state captured immediately before release equaled the post-release state;
there was no release snap. Selection and pick count remained unchanged. There
were zero calls to `refresh()`, zero scene synchronizations, no actor identity
changes, and no CameraRequest during the orbit.

The following vertical drag changed the camera to:

- position `(-2248.373277, 1992.516133, 5126.890005)`;
- focal point `(-12.027768, -8.791549, 269.612721)`;
- view up `(0.146591, 0.936557, -0.318391)`;
- direction `(0.391681, -0.350516, -0.850720)`;
- distance `5709.607367`.

A no-drag click selected `model` and increased the scene-pick count by exactly
one. Middle drag changed position and focal point while preserving direction.
One wheel-forward event changed camera distance from `5709.607367` to
`4718.683774`.

Ten subsequent orbit gestures all changed direction and retained finite camera
state. Final direction was `(0.152062, -0.896269, -0.416628)`, final distance
was `4718.683774`, and `last_rendering_error` remained `None`.

## Windows PowerShell verification

```powershell
.\.venv-v3\Scripts\Activate.ps1
$env:PYTHONPATH = "src;packages/workbench_ui"

python -m compileall -q src packages\workbench_ui\workbench_ui
python -m unittest tests.test_task82a_viewport_startup
python -m unittest tests.test_task82b_viewport_interaction
python -m unittest tests.test_task82c_mouse_orbit
python -m unittest tests.test_task79_workbench_ui
python -m unittest tests.test_task80_v3_ui
python scripts\report_architecture_metrics.py --fail-on-new
python -m unittest discover -s tests -p "test_*.py"
git diff --check
git status --short
```

For a visible run, do not set `QT_QPA_PLATFORM=offscreen`.

## Remaining limitations

- Linux/Xvfb was unavailable in this Windows workspace. Offscreen lifecycle
  coverage passed, but no Linux rendering claim is made.
- Injected input objectively verifies the real native event and render path,
  one-event forwarding, camera vectors, selection, and repeated stability. A
  physical mouse on additional DPI/GPU/driver combinations remains useful for
  subjective sensitivity and proportional-feel release review; it is not an
  unverified functional dependency of this repair.
- `FrontNoseTest.openretop` contains no preview surfaces, BREP surfaces, section
  results, or active region. Their Task 82B scene-tree behavior remains covered
  by focused controller/presentation tests and was not represented as part of
  this project's orbit acceptance.

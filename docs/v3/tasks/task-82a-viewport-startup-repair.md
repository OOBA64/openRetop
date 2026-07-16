# Task 82A — Windows VTK Viewport Startup and Rendering Repair

## Status

The startup/rendering repair is implemented and verified on a real Windows
Qt/VTK rendering path. The white native surface is eliminated, the concrete
Win32 OpenGL backend renders restored project geometry, and normal application
close is clean. Four hands-on interaction checks remain for human release
sign-off: Frame Selected, orbit/pan/zoom, live resize, and minimize/restore.

Base commit: `f5d79e55c42d32e88ae16a5a92479e2358884e22` on
`v3-refactor`.

Repair commit message: `Task 82A: repair Windows VTK viewport startup`.

The repair commit's SHA is reported by `git rev-parse HEAD` after this document
is committed. A Git commit cannot embed its own SHA because changing this file
changes that content-addressed SHA.

## Baseline and reproduction

The local branch and fetched remote both resolved to the required base commit.
The initial worktree contained only generated, untracked
`packages/workbench_ui/openretop_workbench_ui.egg-info` metadata; it was not
treated as source or included in the repair.

The default system Python did not contain PySide6 or VTK. The supported V3
environment was `.venv-v3`:

- Python: 3.11.9
- executable: `.venv-v3\Scripts\python.exe`
- PySide6: 6.11.1
- VTK: 9.6.2
- editable framework import:
  `packages\workbench_ui\workbench_ui\viewport.py`

The editable package was installed from repository source with:

```powershell
python -m pip install -e .\packages\workbench_ui --no-build-isolation
```

VTK 9.6.2's public `QVTKRenderWindowInteractor` example imports
`vtkRenderingOpenGL2` and `vtkInteractionStyle`, constructs and embeds the
widget, shows it, and then calls `Initialize()` and `Start()`.

Before editing, a real Windows Qt event loop reported:

- render window: `vtkRenderWindow`
- renderer: `vtkRenderer`
- interactor: `vtkGenericRenderWindowInteractor`
- interactor initialized: true
- renderer size: 1354 × 949
- renderers: 1
- synchronized actors: 1
- submitted snapshot: 0 meshes and 1 section plane
- renderer background: `(0.0, 0.0, 0.0)` instead of configured `#101316`

The generic `vtkRenderWindow` result proved that no concrete platform render
factory had been registered. Importing `vtkmodules.vtkRenderingOpenGL2` before
QVTK construction changed the result to `vtkWin32OpenGLRenderWindow`; a
temporary diagnostic sphere and `TurboBumper.stl` then rendered successfully.

## Root cause

The regression had three cooperating causes.

1. Modular VTK backend registration was incomplete. Importing only QVTK and
   `vtkRenderingCore.vtkRenderer` created the abstract factory product
   `vtkRenderWindow`. The legacy broad `vtk` import had previously registered
   concrete implementations as a side effect. A native Qt child could exist
   and paint its default surface while VTK had no Win32 OpenGL implementation
   to render the scene, producing the observed white surface on the affected
   startup path.
2. `OpenRetopV3Window.__init__()` called `refresh()` before the main window and
   QVTK child were shown or the interactor was initialized. `QtSceneViewport`
   immediately synchronized actors, attempted camera work, and the main window
   consumed its initial Frame All request. The entry point later showed and
   initialized the widget but did not perform one authoritative post-ready
   scene synchronization.
3. The application display background was carried in snapshot display colors
   but never applied to `vtkRenderer`. Rendering with a registered backend
   therefore changed the native surface from white to VTK's default black,
   which proved painting worked but did not complete application policy.

The import changed white to black because loading `vtkRenderingOpenGL2`
registers VTK's object-factory override from `vtkRenderWindow` to
`vtkWin32OpenGLRenderWindow`. Black was the concrete renderer's default clear
color; it did not itself prove actors, framing, or settings were correct.

## Final lifecycle

`VTKViewportWidget` is the single readiness owner. There are no startup timer
chains, `showEvent()` refreshes, constructor renders, or entry-point renders.

1. The generic framework module imports `vtkRenderingOpenGL2`,
   `vtkInteractionStyle`, and, when available, `vtkRenderingFreeType` before
   constructing QVTK or a renderer.
2. `VTKViewportWidget` constructs one QVTK child, one render window, and one
   renderer and adds the renderer once.
3. The main-window constructor builds ordinary Qt models and submits its first
   `SceneSnapshot`. `QtSceneViewport` retains that snapshot without creating
   scene services or rendering.
4. `run_v3_app()` shows the main window and calls `viewport.start()` once.
5. Idempotent `start()` uses QVTK's public `Initialize()` and `Start()` exactly
   once, validates initialized state, marks readiness, and emits `ready` once.
6. `QtSceneViewport` reacts to readiness by constructing `PickingService`,
   `SceneSynchronizer`, and `CameraController`, then registering five pointer
   observers once.
7. The newest retained snapshot replaces any stale early snapshot. It applies
   the configured background and display overlays, synchronizes cached actors,
   applies any pending camera request only after valid renderer dimensions,
   and renders.
8. Later refreshes synchronize incrementally and reuse actors. A camera request
   remains pending if dimensions are not valid rather than being discarded.
9. Errors are logged, retained in structured diagnostics, emitted by Qt
   signals, and shown in the main-window Diagnostics dock and status bar.

`start()` and `render()` deliberately suppress native OpenGL work when
`QT_QPA_PLATFORM=offscreen`. During diagnosis, initializing
`vtkWin32OpenGLRenderWindow` with Qt's offscreen plugin failed pixel-format
selection and could hang. Headless tests therefore validate construction,
scene synchronization, actor creation, and lifecycle with fakes or an inert
native host; the real renderer is covered by the separate visible Windows test.
No process globally changes `QT_QPA_PLATFORM` in production.

Multisampling was not disabled. The installed VTK 9.6.2 Win32 backend rendered
reliably with its defaults, so there was no evidence justifying a global visual
quality reduction.

## Rendering and scene validation

### Empty project

A real visible run produced:

- `vtkWin32OpenGLRenderWindow` / `vtkOpenGLRenderer`
- renderer and render-window size: 1354 × 949
- initialization count: 1
- synchronization count: 1
- pointer observers: 5
- configured background: `(0.062745, 0.074510, 0.086275)` (`#101316`)
- visible grid and axes with no synthetic diagnostic geometry
- no rendering error

Frame All uses the visible grid bounds when an otherwise empty snapshot has no
model bounds, preserving the tested camera math while making the empty-scene
grid useful.

### STL validation

`test_assets\TurboBumper.stl` rendered through the normal application snapshot
path without manual backend imports:

- snapshot: 1 mesh and 1 section plane
- scene synchronization: created 2
- mapper input: 122,209 points and 220,000 polygon cells
- actor visibility: true
- actor opacity: 1.0
- actor and snapshot bounds: finite
- renderer size: 1354 × 949
- synchronization count: 1
- observer count: 5
- camera position, focal point, clipping range, and view angle: finite
- configured background, grid, and axes: visible

### Exact project acceptance

The requested project was located at
`C:\Users\devan\OneDrive\Desktop\openRetop Tests\FrontNoseTest.openretop` and
opened in a real visible Windows run. It restored and displayed:

- `TurboBumper.stl`
- 2 manual curves
- 1 section plane
- the saved model transform

Observed diagnostics:

- snapshot counts: mesh 1, curves 2, surfaces 0, regions 0, section planes 1,
  section results 0
- scene actors created: 4
- renderer actors: 11, including application overlays and axes sub-actors
- renderer view props: 6
- visible world bounds:
  `((-859.4128, -871.3291, -93.7022), (835.3572, 853.7460, 632.9276))`
- camera focal point: `(-12.0278, -8.7915, 269.6127)`
- clipping range: `(4517.0740, 7049.6623)`
- mesh mapper input: 122,209 points / 220,000 cells
- synchronization count: 1
- observer count: 5
- last rendering error: none
- normal main-window close exit code: 0

The scene tree and viewport agreed on the restored mesh, curves, and section
plane. Initial Frame All displayed the transformed complete project.

The repository's complete V3 fixture also rendered one curve, one preview
surface, one section plane, and one section result as four synchronized scene
actors with finite bounds. Its normal main-window close was clean. A synthetic
`app.quit()` while native VTK children were still alive was rejected as a test
method after it demonstrated invalid teardown ordering; acceptance uses normal
window close.

## Diagnostics

`scripts/diagnose_vtk_viewport.py` runs from the repository root.

Visible mode reports Python/platform/package versions and paths, backend import
state, QVTK availability, concrete classes, readiness, dimensions, actor count,
camera state, one temporary script-local sphere, one completed render, and any
captured failure. It exits automatically and does not read or modify projects
or settings.

Offscreen mode reports the same construction/backend information, adds the
temporary actor without rendering, and explicitly reports that native start was
suppressed. It does not attempt unsafe Win32 pixel-format initialization.

VTK 9.6.2's public `SupportsOpenGL()` probe was not retained in the diagnostic
because it left the Win32 context in a state that emitted `wglMakeCurrent`
errors during teardown. A successful visible `Render()` on
`vtkWin32OpenGLRenderWindow` is used as direct, non-disruptive capability
evidence instead.

## Files changed

- `packages/workbench_ui/workbench_ui/viewport.py`
- `packages/workbench_ui/workbench_ui/demo.py`
- `packages/workbench_ui/README.md`
- `src/presentation/qt/viewport.py`
- `src/presentation/qt/main_window.py`
- `src/viewer/actor_factories.py`
- `scripts/diagnose_vtk_viewport.py`
- `tests/test_task82a_viewport_startup.py`
- `docs/v3/tasks/task-82a-viewport-startup-repair.md`
- `docs/v3/STATUS.md`

The generic framework remains independent and imports no openRetop application
or scene modules. No Tk code, direct startup actors, test sphere, persistence
change, geometry-algorithm change, or schema change was introduced.

## Automated verification

Commands used the supported roots:

```powershell
$env:PYTHONPATH = "src;packages/workbench_ui"
```

Results on Windows 10 build 26200:

- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed.
- Required focused suites, offscreen: 54 tests passed; the one real visible
  Windows render test was narrowly skipped as designed.
- `python -m unittest tests.test_task82a_viewport_startup`, visible Windows:
  18 tests passed, no skips, in 1.532 seconds.
- `python scripts/report_architecture_metrics.py --fail-on-new`: passed with 0
  dependency violations, 0 practical cycles, and 0 duplicate action/menu
  labels.
- Complete visible Windows discovery: 502 tests passed, no skips, in 7.481
  seconds.
- `scripts/diagnose_vtk_viewport.py --offscreen`: passed without native
  initialization or render.
- `scripts/diagnose_vtk_viewport.py --duration-ms 400`: completed one visible
  Win32 OpenGL render with no captured failure or teardown error.

Architecture report at verification time:

- 105 production Python files / 32,673 lines
- 54 test Python files / 13,469 lines
- 55 `OpenRetopV3Window` methods
- 0 legacy-window methods

Linux/Xvfb was not run because this repair environment was Windows and the
defect required the real Win32 QVTK/OpenGL path. CI retains offscreen coverage;
the Windows visible evidence above is the acceptance path for this task.

## Windows PowerShell verification

```powershell
.\.venv-v3\Scripts\Activate.ps1
python -m pip install -r requirements.txt
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
python scripts\report_architecture_metrics.py --fail-on-new
python -m unittest discover -s tests -p "test_*.py"
git diff --check
```

If isolated build dependency resolution is unavailable, the equivalent local
editable install is:

```powershell
python -m pip install -e .\packages\workbench_ui --no-build-isolation
```

## Manual Windows acceptance status

1. Configured dark central viewport immediately appears: passed.
2. Viewport does not remain white: passed.
3. No manual `vtkRenderingOpenGL2` import is required: passed.
4. Empty project background, grid, and axes: passed visibly.
5. Opening an STL renders the mesh: passed with `TurboBumper.stl`.
6. `FrontNoseTest.openretop` restores and displays geometry: passed visibly.
7. Scene tree and viewport visible objects agree: passed for the exact project
   and complete fixture.
8. Initial Frame All displays the complete transformed project: passed.
9. Hands-on Frame Selected for both a mesh and curve: pending human sign-off;
   category-aware camera tests pass automatically.
10. Hands-on orbit, pan, and zoom: pending human sign-off; QVTK interaction
    style registration and pointer-observer non-duplication are verified.
11. Live resize does not return to white: pending human sign-off; several real
    renderer dimensions and QVTK resize integration were exercised.
12. Minimize and restore do not return to white: pending human sign-off.
13. No synthetic orange sphere in normal startup: passed; sphere code exists
    only in the standalone diagnostic script.
14. No unhandled traceback on startup or normal close: passed.
15. No hidden successful-startup error log: passed. Deliberately induced
    failures are logged and displayed by diagnostics.

## Remaining limitations

- Human release review should complete items 9-12 above using the exact project.
- Qt offscreen on Windows cannot safely initialize the native Win32 OpenGL
  interactor; the application intentionally keeps that path inert and tests it
  separately from visible rendering.
- The repair was not run under Linux/Xvfb because it would not validate the
  affected Win32 rendering path.
- Driver-specific rendering outside the tested Windows/VTK/PySide versions
  remains part of normal release-candidate coverage.

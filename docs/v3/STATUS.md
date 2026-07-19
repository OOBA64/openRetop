# openRetop V3 migration status

## Result

Tasks 77-82 are complete. The PySide6 V3 workbench is the only supported
desktop shell, the legacy Tk presentation and compatibility viewport have been
physically removed, and the complete automated suite is green. Task 82A repairs
the Windows native VTK startup regression: the concrete OpenGL backend is now
registered explicitly and the first scene synchronizes through one post-show
readiness lifecycle. Task 82B repairs scene visibility, transform and
screen-space orientation overlays, and triangular named-view controls. Task
82C corrects its left-input regression and restores the primary orbit contract:
ordinary left drag reaches QVTK's single TrackballCamera owner, while click
selection and active tool capture remain explicitly arbitrated at a
four-logical-pixel threshold. Task 82D restores the user-visible orientation
gizmo as one fixed-size transparent renderer layer with a readable X/Y/Z actor,
independent camera synchronization, DPI-aware top-left layout, and deterministic
shutdown.
Task 82E replaces Task 82B's seven lettered triangles with one coherent
navigation cluster: a stronger X/Y/Z gizmo, four masked named-view triangles,
two 15-degree camera-roll controls, and a central isometric target with
independent gizmo/control visibility.

## Completed acceptance work

- Task 77: immutable scene snapshots, stable actor cache/synchronization,
  structured scene/mesh/tool picks, camera control, named views, and transformed
  category-aware framing. Qt pointer events now drive manual curves, regions,
  transforms, and scene selection through those contracts.
- Task 78: project/settings repositories, import/proxy/export/CAD services,
  explicit composition root, deterministic compatibility, and complete restore
  of transforms, display/colors, planes/results, curves/manual metadata,
  regions, preview/BREP records, editable features, and scene selection.
- Task 79: independent `workbench_ui` package with action conflicts, menu/
  toolbar schemas, docks/layout recovery, tool lifecycle, hierarchical scene
  tree operations, live/apply inspectors and typed editors, palette, themes,
  settings, VTK host, demo, and package tests.
- Task 80: complete V3 menus/actions, tree, contextual inspector, tool input,
  project lifecycle, preferences, progress/errors, recent projects, dirty/title
  state, BREP rebuild/STEP export, diagnostics, and central workflow routing.
- Task 81: removed `src/app`, Tk host/menu/dialog/browser code,
  `viewer/embedded_viewport.py`, legacy widget-internal tests, compatibility
  imports/re-exports, and all architecture allowlist entries. Replacement V3
  behavior tests cover every registered action and retained workflow family.
- Task 82: final recovery, workflow, fixture, CI, benchmark, packaging, setup,
  user, architecture, parity, and release-candidate evidence.
- Task 82A: explicit modular VTK backend registration, idempotent QVTK startup,
  latest-snapshot deferral, post-ready scene services/observers, configured
  background, grid/axes overlays, camera-after-size ordering, structured
  diagnostics, safe offscreen suppression, and a standalone viewport diagnostic.
- Task 82B: explicit `vtkInteractorStyleTrackballCamera`, a four-logical-pixel
  click/drag router, uninterrupted native navigation during tools, dedicated
  `scene.set_visibility`, non-checkable organizational rows, hidden-until-active
  transform axes/ring, a transparent fixed-size orientation renderer, propagated
  view-control settings, seven triangular named-view controls, fitted
  orthographic named views, and structured scene/overlay prop inventory.
- Task 82C: native unmodified-left orbit through QVTK, deferred one-pick click
  selection after native release, accumulated gesture diagnostics, explicit
  transform/manual-curve/region left ownership, and uninterrupted middle/wheel
  navigation during tools.
- Task 82D: one openRetop-owned orientation-gizmo controller, dedicated
  noninteractive transparent renderer, labeled non-pickable `vtkAxesActor`,
  fixed 96-logical-pixel / 12-pixel-margin layout, independent parallel camera,
  one interaction observer, structured diagnostics, setting/overlay isolation,
  and clean accepted-window shutdown.
- Task 82E: one navigation-cluster lifecycle owner, 104-pixel high-contrast
  X/Y/Z gizmo, four unlettered masked directional triangles, central isometric
  activation, two application-routed 15-degree roll controls, compact
  DPI-aware layout, independent gizmo/control settings, and no Task 82C input
  changes.

## Verification record (2026-07-18, Task 82E)

- Started exactly from Task 82D commit
  `48238454de9008fe934f2b3235f77ef11b7cc260`; `v3-task-82c` remained
  `32f3eb68f2f948e44263b0af7e995eb02ea25b1a`.
- Direct reproduction found persisted `show_axis_gizmo=false` and
  `show_viewcube=true`. The valid layer-1 renderer was disabled by that setting;
  forcing it on measured a modest 61 x 65 physical colored footprint beside
  the old seven controls.
- Real visible Windows acceptance used Python 3.11.9, PySide6 6.11.1, VTK
  9.6.2, `vtkWin32OpenGLRenderWindow`, `vtkOpenGLRenderer`, and DPR 1.25.
- `FrontNoseTest.openretop` visibly restored its mesh, grid, curves, and section
  plane. The final gizmo measured 76 x 72 physical colored pixels with 410 red,
  282 green, 330 blue, and zero white backing pixels.
- Center isometric, all four named-view mappings, both roll actions, selection,
  native left orbit, middle pan, wheel zoom, independent settings, resize,
  maximize, minimize/restore, repeated refresh, and clean close passed with one
  actor, renderer, cluster, and observer.
- Focused visible results: Task 82A 18/18, Task 82B 26/26, Task 82C 15/15,
  Task 82D 13/13, Task 82E 11/11, Task 79 9/9, Task 80 7/7, Task 81 5/5,
  and Task 82 5/5.
- Complete visible Windows discovery: 567 tests passed, no skips, in 21.504
  seconds. Compileall and architecture checks passed; architecture reported no
  dependency violations, practical cycles, or duplicate detectable labels.
- Five inspected real-application screenshots are under
  `artifacts/task-82e/`; detailed implementation, exact timings, commands, and
  limitations are in `tasks/task-82e-navigation-widget.md`.

## Verification record (2026-07-18, Task 82D)

- Starting commit and `v3-task-82c` both resolved to
  `32f3eb68f2f948e44263b0af7e995eb02ea25b1a` before editing.
- Complete discovery on the real visible Windows Qt platform: 556 tests passed,
  no skips, in 15.745 seconds, with no post-run WGL warning.
- Required focused results: Task 82A 18/18 in 1.609 seconds; Task 82B 26/26 in
  3.074 seconds; Task 82C 15/15 in 2.450 seconds; Task 82D 13/13 in 3.043
  seconds; Task 79 9/9 in 0.360 seconds; Task 80 7/7 in 1.459 seconds; Task 81
  5/5 in 0.327 seconds; Task 82 5/5 in 0.004 seconds.
- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed.
- `scripts/report_architecture_metrics.py --fail-on-new`: passed with 108
  production files / 34,002 lines, 57 test files / 15,826 lines, 56
  `OpenRetopV3Window` methods, zero legacy-window methods, zero dependency
  violations, zero practical cycles, and zero duplicate labels.
- Visible environment: Windows 10.0.26200.0, Python 3.11.9, PySide6 6.11.1,
  VTK 9.6.2, `vtkWin32OpenGLRenderWindow`, `vtkOpenGLRenderer`, and DPR 1.25.
- `FrontNoseTest.openretop` visibly restored its model, grid, curves, and section
  plane with one readable labeled top-left gizmo. Its overlay contained red,
  green, and blue pixels with zero white backing pixels; normal startup added no
  synthetic actor.
- Orbit over the gizmo area, pan, zoom, named views, Frame All/Selected,
  selection, checkbox visibility, Move/Rotate and cancel, repeated refresh,
  toggle off/on, horizontal/vertical resize, maximize/restore, and
  minimize/restore all passed with one actor, renderer, and observer.
- A separate empty-project visible Win32 back-buffer check showed configured
  `#101316` background, grid, and labeled gizmo with no rendering error.
- The inspected screenshot is
  `artifacts/task-82d-orientation-gizmo.png`; detailed implementation and exact
  evidence are in `tasks/task-82d-orientation-gizmo.md`.

## Verification record (2026-07-17, Task 82C)

- Complete discovery on a real visible Windows Qt platform: 543 tests passed,
  no skips, in 16.129 seconds.
- Task 82C visible Windows: 15 tests passed with no skips in 2.518 seconds.
- Task 82C offscreen: 14 tests passed and its one narrowly scoped visible
  Win32 test skipped in 2.093 seconds.
- Required focused Tasks 79, 80, 82A, 82B, and 82C: 75 tests passed; the 59
  Qt/VTK tests in Tasks 82A-82C also passed without skips on the visible native
  path.
- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed.
- `scripts/report_architecture_metrics.py --fail-on-new`: passed.
- Architecture: 107 production files / 33,523 lines; 56
  `OpenRetopV3Window` methods; 0 legacy-window methods; 0 guarded UI-import
  violations; 0 practical package/module cycles; 0 detectable duplicate
  action/menu labels.
- Visible Win32 diagnostic: PySide6 6.11.1, VTK 9.6.2,
  `vtkWin32OpenGLRenderWindow`, `vtkInteractorStyleTrackballCamera`, initialized
  interactor, one completed render, no captured error, and clean teardown.
- Exact project acceptance: `FrontNoseTest.openretop` restored and visibly
  rendered its transformed 122,209-point / 220,000-cell mesh, two curves, and
  section plane. Middle/right/modified-left/wheel gestures, Frame All, Frame
  Selected for mesh and curve, every named view, checkbox toggles, tool-mode
  camera coexistence, overlay lifecycle, independent control toggles, and window
  state changes passed; one camera-to-gizmo observer remained and normal close
  was clean.
- Task 82C exact-project acceptance used injected Qt gestures against the shown
  QVTK native child. Horizontal and vertical left drags, including a drag begun
  over the mesh, changed camera direction without a pick, selection, refresh,
  actor-cache rebuild, synchronization, CameraRequest, or release snap. A true
  click selected `model` with one pick; middle pan and wheel zoom worked; ten
  consecutive orbits retained finite camera state and no rendering error.
- Structured prop isolation proved the reported light rectangle belonged to
  restored `mesh:mesh` source geometry, not an axes/section/overlay prop. The
  final idle viewport has no unidentified visible opaque world-origin prop.
- Empty and STL visual passes showed configured `#101316` background, grid,
  axes, actors, and camera framing without manual backend imports or startup
  test geometry.
- Scene sync benchmark (25 iterations): 21,459.2 syncs/second, with actor reuse
  after the first synchronization.
- V3 workflow benchmark (250 curves): composition 0.493 ms, scene snapshot
  11.343 ms, project round-trip 40.551 ms, tree/inspector model refresh
  0.024 ms per iteration on the local environment.
- Standalone `workbench_ui` wheel (0.1.0), offscreen Qt startup/window and demo
  smoke, project fixture migration, corrupt/missing recovery, and diff checks:
  passed.

## Remaining human review items

- Repeat physical-pointer feel, mixed-monitor DPI transitions, and driver-specific
  rendering on release target hardware. The verified environment was Windows
  build 26200, Python 3.11.9, PySide6 6.11.1, and VTK 9.6.2; the real visible
  acceptance injected input through Qt into the native QVTK child.
- Linux/Xvfb was not available for Tasks 82B-82E. Windows offscreen behavior
  remains covered without unsafe native start, and no Linux rendering claim is
  made.
- `FrontNoseTest.openretop` does not contain preview/BREP surfaces, section
  results, or an active region; those visibility families pass focused
  controller/tree tests rather than being reported as manual project checks.
- CadQuery/OCP availability remains environment-dependent; unsupported trim and
  intersection capabilities continue to report disabled rather than pretending
  success.

There is no next numbered architecture-refactor task. The exact next starting
point is human V3 release-candidate review using `RELEASE_CANDIDATE.md`; any
findings should be filed as targeted defects rather than reopening the legacy
migration. Task 82A detail and exact commands are in
`tasks/task-82a-viewport-startup-repair.md`; Task 82B interaction, visibility,
overlay, control, and acceptance evidence is in
`tasks/task-82b-viewport-interaction-controls-repair.md`; Task 82C's repaired
native-orbit route and exact camera evidence are in
`tasks/task-82c-restore-mouse-orbit.md`; Task 82D's fixed orientation renderer,
camera synchronization, visible pixel proof, and screenshot are in
`tasks/task-82d-orientation-gizmo.md`; Task 82E's unified control layout, roll
implementation, setting states, and five reviewed screenshots are in
`tasks/task-82e-navigation-widget.md`.

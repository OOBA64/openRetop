# openRetop V3 migration status

## Result

Tasks 77-82 are complete. The PySide6 V3 workbench is the only supported
desktop shell, the legacy Tk presentation and compatibility viewport have been
physically removed, and the complete automated suite is green. Task 82A repairs
the Windows native VTK startup regression: the concrete OpenGL backend is now
registered explicitly and the first scene synchronizes through one post-show
readiness lifecycle.

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

## Verification record (2026-07-16)

- Complete discovery on a real visible Windows Qt platform: 502 tests passed,
  no skips, in 7.481 seconds.
- Focused Tasks 77-82A offscreen: 54 tests passed with only the narrowly scoped
  visible Windows render smoke skipped.
- Focused Task 82A visible Windows run: 18 tests passed with no skips.
- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed.
- `scripts/report_architecture_metrics.py --fail-on-new`: passed.
- Architecture: 105 production files / 32,673 lines; 55
  `OpenRetopV3Window` methods; 0 legacy-window methods; 0 guarded UI-import
  violations; 0 practical package/module cycles; 0 detectable duplicate
  action/menu labels.
- Visible Win32 diagnostic: PySide6 6.11.1, VTK 9.6.2,
  `vtkWin32OpenGLRenderWindow`, initialized interactor, one completed render,
  no captured error, and clean teardown.
- Exact project acceptance: `FrontNoseTest.openretop` restored and visibly
  rendered its transformed 122,209-point / 220,000-cell mesh, two curves, and
  section plane; synchronization and observer counts were one and five;
  Frame All used finite saved world bounds; normal close exited cleanly.
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

- Complete hands-on Frame Selected (mesh and curve), orbit/pan/zoom, live
  resize, and minimize/restore checks. Startup, empty scene, STL, exact project,
  framing, and normal-close Windows visual checks already passed.
- Repeat driver-specific rendering on release target hardware. The verified
  environment was Windows build 26200, PySide6 6.11.1, and VTK 9.6.2.
- Linux/Xvfb was not run for Task 82A because it cannot validate the affected
  Win32 OpenGL path; CI/offscreen behavior remains covered without native start.
- CadQuery/OCP availability remains environment-dependent; unsupported trim and
  intersection capabilities continue to report disabled rather than pretending
  success.

There is no next numbered architecture-refactor task. The exact next starting
point is human V3 release-candidate review using `RELEASE_CANDIDATE.md`; any
findings should be filed as targeted defects rather than reopening the legacy
migration. Task 82A detail and exact commands are in
`tasks/task-82a-viewport-startup-repair.md`.

# openRetop V3 migration status

## Result

Tasks 77-82 are complete. The PySide6 V3 workbench is the only supported
desktop shell, the legacy Tk presentation and compatibility viewport have been
physically removed, and the complete automated suite is green.

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

## Verification record (2026-07-15)

- Complete discovery: 484 tests passed.
- Focused Tasks 77-82 plus V3 workflow suites: passed.
- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed.
- `scripts/report_architecture_metrics.py --fail-on-new`: passed.
- Architecture: 105 production files / 32,260 lines; 52
  `OpenRetopV3Window` methods; 0 legacy-window methods; 0 guarded UI-import
  violations; 0 practical package/module cycles; 0 detectable duplicate
  action/menu labels.
- Scene sync benchmark (25 iterations): 21,459.2 syncs/second, with actor reuse
  after the first synchronization.
- V3 workflow benchmark (250 curves): composition 0.493 ms, scene snapshot
  11.343 ms, project round-trip 40.551 ms, tree/inspector model refresh
  0.024 ms per iteration on the local environment.
- Standalone `workbench_ui` wheel (0.1.0), offscreen Qt startup/window and demo
  smoke, project fixture migration, corrupt/missing recovery, and diff checks:
  passed.

## Remaining human review items

- Perform the final Windows desktop OpenGL visual pass; Qt offscreen verifies
  behavior but not driver-specific rendering quality.
- Exercise a representative large real-world scan and customer project. The
  repository fixtures intentionally remain small enough for source control.
- CadQuery/OCP availability remains environment-dependent; unsupported trim and
  intersection capabilities continue to report disabled rather than pretending
  success.

There is no next numbered architecture-refactor task. The exact next starting
point is human V3 release-candidate review using `RELEASE_CANDIDATE.md`; any
findings should be filed as targeted defects rather than reopening the legacy
migration.

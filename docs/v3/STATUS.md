# openRetop V3 migration status

## Current task

Task 75 — V3 Architecture Baseline and Application Core

Implementation status: complete. Required full-suite verification is blocked in
the supplied workstation environment; see Verification and blocker below. No
Task 76 controller extraction was started.

## Completed work

- Audited production and test packages covering MainWindow, AppState, the Task 74
  manual-curve controller/session, scene browser, menus, keybindings, undo,
  transforms, mesh/query/projection, sections, curves, regions, surfaces, BREP,
  analysis, project persistence, settings, and viewer infrastructure.
- Established the authoritative V3 layer model: domain, application,
  infrastructure, presentation, and bootstrap, including allowed dependency
  direction and compatibility-boundary rules.
- Recorded the feature, command/action, project-format, dependency, migration,
  and known-regression baselines. The project serializer remains version 1 and
  no project schema or geometry representation changed.
- Added UI-agnostic action definitions, action state resolution, command
  dispatch, structured results, typed events, immutable selection snapshots,
  and an explicit typed dependency container.
- Registered Frame All, Frame Selected, Show All, Toggle Visibility, Undo, and
  Redo as the representative action slice. Existing MainWindow public wrappers
  and menu entry points remain in place as compatibility adapters.
- Kept concrete Tk operations in the legacy presentation adapters and concrete
  VTK viewport work behind result application. No geometry algorithm, actor
  construction path, project serializer, or MeshQueryService implementation was
  moved or rewritten.
- Added an architecture metrics report with text and JSON output, largest-module
  reporting, symbol and MainWindow method counts, package imports, dependency
  violations, practical cycles, and duplicate detectable labels.
- Added an explicit six-entry Tk dependency allowlist. Existing debt is reported;
  only new violations or cycles fail the gate. Computational VTK imports used by
  the accelerated mesh locator are deliberately permitted while rendering and
  actor imports remain prohibited in guarded modules.
- Characterized the framing regression and the future expected behavior without
  changing camera behavior. The camera fix remains reserved for Task 77.

## Architecture snapshot

The final Task 75 metrics report records:

- 70 production Python files and 37,410 physical lines.
- 41 test/support Python files and 21,113 physical lines.
- 214 classes, 2,317 functions/methods, and 1,621 direct class methods.
- 547 OpenRetopWindow methods; src/app/main_window.py remains the largest module
  at 14,703 lines.
- Six allowlisted legacy Tk imports, zero new dependency violations, zero package
  cycles, and zero module cycles.

The report command is:

    python scripts/report_architecture_metrics.py --fail-on-new

## Files created

Documentation:

- docs/v3/ARCHITECTURE.md
- docs/v3/MIGRATION_RULES.md
- docs/v3/FEATURE_INVENTORY.md
- docs/v3/COMMAND_INVENTORY.md
- docs/v3/PROJECT_FORMAT_BASELINE.md
- docs/v3/DEPENDENCY_AUDIT.md
- docs/v3/KNOWN_REGRESSIONS.md
- docs/v3/STATUS.md

Application core:

- src/application/__init__.py
- src/application/actions.py
- src/application/commands.py
- src/application/events.py
- src/application/results.py
- src/application/selection.py
- src/application/dependencies.py

Tooling and tests:

- scripts/report_architecture_metrics.py
- tests/architecture_dependency_baseline.json
- tests/test_architecture.py
- tests/test_application_core.py

## Files modified

- src/app/main_window.py
- src/app/menus.py

No files were moved or removed.

## Verification

Passing checks:

- python -m compileall -q src — passed under the available Python 3.14 runtime.
- Python 3.11 -m compileall -q src — passed under Blender's bundled runtime.
- python -m unittest discover -s tests -p test_application_core.py -v —
  13 tests passed.
- python -m unittest discover -s tests -p test_architecture.py -v —
  10 tests passed.
- python scripts/report_architecture_metrics.py --largest 5 --fail-on-new —
  passed with six allowlisted findings, zero new findings, and zero cycles.
- Representative MainWindow adapter smoke with presentation stubs — Frame All,
  no-selection Frame Selected, no-selection Toggle Visibility, and empty Undo
  completed through the new dispatcher.

Verification and blocker:

- The exact complete-suite command with PYTHONPATH=src was run using the only
  general Python installation. Discovery reached 74 tests and stopped with 36
  import errors because that Python 3.14 installation has no NumPy (and therefore
  cannot load the repository's VTK/CAD dependency chain).
- The checked-in .venv refers to a Python 3.11 executable that is no longer
  installed.
- As a second full discovery pass, Blender's Python 3.11 plus the checked-in
  site-packages supplied NumPy, VTK, CadQuery/OCP, and related dependencies.
  It ran 364 tests: 359 passed and five errored only because that runtime has no
  tkinter. The five affected imports were test_curve_surface_prep,
  test_embedded_viewport_scene, test_main_window_ui, the MainWindow compatibility
  case in test_manual_curve_controller, and test_scene_browser_labels.
- No available interpreter has both tkinter and the scientific/CAD dependencies.
  The complete suite therefore cannot be certified green in this environment.
  No tests were skipped, weakened, rewritten, or bypassed to conceal the blocker.

## Compatibility and risks

- Existing .openretop compatibility is expected to be unchanged: the serializer,
  version discriminator, field names, reconstruction defaults, and load/save
  entry points were not changed. The format baseline documents permissive
  metadata handling and the absence of checked-in real-project fixtures.
- Task 74 manual-curve controller/session ownership and the accelerated
  MeshQueryService path remain intact.
- The six representative actions intentionally still execute bound compatibility
  handlers on MainWindow. This is the Task 75 bridge, not the Task 76 controller
  extraction.
- Only the representative action slice is authoritative in the registry. Legacy
  menus and scene-browser actions outside that slice remain inventoried for
  later migration.
- The dependency allowlist is a ratchet, not an endorsement of the six Tk imports.
  Removing those entries requires moving their presentation responsibilities in
  later tasks.
- The full test result is an environment risk rather than a known product
  assertion failure, but it remains an unsatisfied acceptance check until run by
  an interpreter with the complete dependency set.

## Known remaining issues

- Frame All uses the legacy cached mesh-centric view center/extent, so visible
  derived geometry or restored transformed objects can be clipped or framed
  incorrectly.
- Frame Selected has incomplete behavior for some selection kinds and empty or
  stale scene states.
- Project-load framing can occur before all restored transforms and derived
  objects contribute to final visible bounds.
- MainWindow remains a large mixed-responsibility adapter and the complete legacy
  action catalog is not yet centralized.
- There are no checked-in representative .openretop fixture files for end-to-end
  backward-compatibility loading.

The first three camera items are documented in docs/v3/KNOWN_REGRESSIONS.md and
must remain unchanged until Task 77.

## Acceptance assessment

All requested architecture documents, inventories, project-format baseline,
metrics tooling, dependency tests/baseline, application primitives, typed
contracts, and the six-action representative integration exist. Project format
and Task 74 behavior were not intentionally changed. Focused tests and all
dependency gates pass.

The acceptance statement requiring the complete unittest suite to pass cannot be
satisfied or certified on this workstation because of the incompatible runtime
split described above. Consequently, every implementation and documentation
criterion is satisfied, but not every acceptance criterion can be reported as
satisfied until the external runner completes the full suite in the supported
application environment.

## Exact next-task starting point

Start Task 76 — Extract Remaining Workflow Controllers. Use the Task 75 action,
command, result, event, selection, and dependency contracts to extract
SceneController, SelectionController, VisibilityController, TransformController,
SectionController, the non-manual CurveController, RegionController,
SurfaceController, BrepController, and AnalysisController. Keep MainWindow public
methods as thin compatibility adapters and preserve Task 74 manual-curve and
Task 73 projection behavior. Register the remaining non-file-dialog actions and
centralize their enablement/visibility rules. Project/settings/import/export
remain primarily Task 78, and the framing/camera correction remains Task 77.

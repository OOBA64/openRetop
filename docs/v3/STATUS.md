# openRetop V3 migration status

## Current task

Task 82 - Final verification, optimization, packaging, and release candidate

Verification and packaging are complete for the V3 path. Release acceptance
remains conditional because Task 81's physical legacy-shell deletion gate is
not satisfied by the existing Tk compatibility suite. This is documented
explicitly in `docs/v3/LEGACY_REMOVAL.md` and is not hidden by skips or
weakened tests.

## Completed task history

- Task 77 - scene snapshots, incremental VTK, structured picking, camera and
  framing. Commit `4de640b`; focused suite 11 passed.
- Task 78 - repositories, import/export/CAD boundaries, and composition root.
  Commit `53ee0cd`; focused suite 7 passed.
- Task 79 - independent PySide6 workbench framework and demo. Commit
  `0edbe1f`; focused suite 5 passed.
- Task 80 - V3 Qt shell, central actions, snapshot viewport, project/model
  dialogs, parity matrix, and user guide. Commit `af5e27c`; focused suite 3
  passed.
- Task 81 - V3-only supported entry point and legacy boundary evidence. Commit
  `813693a`; physical Tk-shell deletion remains gated.
- Task 82 - release fixtures, verification record, performance benchmark,
  setup/CI/release documentation, and standalone package verification. The
  final commit is recorded after this review.

## Task 81 remaining gate

- `src/main.py` launches only the V3 Qt entry point and has no Tk import or
  legacy `app.main_window` reference.
- `src/presentation/qt` has no Tk imports and routes VTK work through the
  shared Task 77 snapshot synchronizer/actor adapter.
- Advanced V3 adapters still need complete behavior evidence for every retained
  legacy workflow.
- `src/app/main_window.py` is still approximately 12,694 lines, and the Tk
  menus, dialogs, scene browser, and `src/viewer/embedded_viewport.py` remain
  for the current regression suite. They must be removed after equivalent V3
  behavior tests replace the stale widget-internal tests.
- The six legacy architecture allowlist entries and duplicate menu-label
  findings cannot be removed until those modules are gone.

## Task 82 verification

- Complete discovery: 670 tests; 638 passed, 31 failed, and 1 error. The 32
  new V3-focused tests pass; all failures/errors are in the existing Tk
  `MainWindow` compatibility suite.
- Focused V3 suites (`tests.test_task77_viewport` through
  `tests.test_task82_release`): 32 passed.
- `python -m compileall -q src packages/workbench_ui/workbench_ui`: passed.
- `git diff --check`: passed.
- `scripts/report_architecture_metrics.py --fail-on-new`: passed; 113
  production Python files / 48,081 lines, 519 `OpenRetopWindow` methods, six
  documented legacy UI allowlist imports, and no practical cycles.
- `benchmarks/benchmark_scene_sync.py --iterations 25`: passed; 11,336.8
  snapshot synchronizations per second in the local V3 environment, with
  actor reuse confirmed after the first iteration.
- `pip wheel --no-deps --no-build-isolation packages/workbench_ui`: passed;
  built `openretop_workbench_ui-0.1.0-py3-none-any.whl`.
- Qt offscreen startup/window smoke and fixture/recovery tests: passed.

## Final metrics and limitations

- `src/app/main_window.py` remains 12,694 lines; `src/viewer/embedded_viewport.py`
  and Tk menus/dialogs/scene browser also remain as compatibility code.
- No files were moved or physically removed in Task 81. The six legacy
  architecture allowlist entries and duplicate legacy action labels therefore
  remain.
- Advanced V3 adapters still need complete behavior evidence for manual curves,
  regions, surfaces, BREP/STEP, and all undo/redo paths.
- Only minimal legacy/current `.openretop` fixtures are included; representative
  real-world scan fixtures and Windows desktop OpenGL review remain manual.
- Optional CAD capability reporting is honest about unavailable trim and
  intersection operations. Offscreen Qt tests skip VTK render calls because
  Windows OpenGL is not reliable in the headless platform plugin.

The branch is a reviewable release candidate, not a merge into the base branch.
Final acceptance requires replacing the stale widget-internal Tk tests with V3
behavior tests, deleting the superseded shell and compatibility viewport, and
then rerunning the complete suite green.

# openRetop V3 migration status

## Current task

Task 81 — Reach parity, remove legacy shell, and eliminate compatibility scaffolding

Implementation status: supported-entry and architecture-boundary portions are
complete; physical legacy-shell removal remains blocked by the existing Tk
compatibility suite. This is documented explicitly in
`docs/v3/LEGACY_REMOVAL.md` and is not hidden by skips or weakened tests.

## Completed task history

- Task 77 — scene snapshots, incremental VTK, structured picking, camera and
  framing. Commit `4de640b`; focused suite 11 passed.
- Task 78 — repositories, import/export/CAD boundaries, and composition root.
  Commit `53ee0cd`; focused suite 7 passed.
- Task 79 — independent PySide6 workbench framework and demo. Commit
  `0edbe1f`; focused suite 5 passed.
- Task 80 — V3 Qt shell, central actions, snapshot viewport, project/model
  dialogs, parity matrix, and user guide. Commit `af5e27c`; focused suite 3
  passed.

## Task 81 completed portions

- `src/main.py` launches only the V3 Qt entry point and has no Tk import or
  legacy `app.main_window` reference.
- `src/presentation/qt` has no Tk imports and routes VTK work through the
  shared Task 77 snapshot synchronizer/actor adapter.
- Added `tests.test_task81_legacy_boundary` with three passing assertions for
  supported entry-point, presentation import, and shared-viewport boundaries.
- Added `docs/v3/LEGACY_REMOVAL.md` with the evidence gate for deleting the Tk
  shell and replacing its widget-internal tests.

## Required remaining Task 81 work

- Advanced V3 action/controller adapters still need parity evidence for all
  retained legacy workflows.
- `src/app/main_window.py` is still approximately 12,694 lines, and the Tk
  menus, dialogs, scene browser, and `src/viewer/embedded_viewport.py` remain
  for the current regression suite. They must be removed after equivalent V3
  behavior tests replace the stale widget-internal tests.
- The six legacy architecture allowlist entries and duplicate menu-label
  findings cannot be removed until those modules are gone.

## Verification

- `tests.test_task81_legacy_boundary` — 3 passed.
- Task 77, 78, 79, and 80 focused suites — passed individually.
- Architecture metrics `--fail-on-new` — passed with the documented six legacy
  Tk allowlist entries and no cycles.
- `python -m compileall -q src packages/workbench_ui/workbench_ui` — passed.
- `git diff --check` — passed.

## Exact next-task starting point

Task 82 performs final verification and release-candidate reporting, but cannot
claim final acceptance until the Task 81 physical deletion gate is resolved.
The known full-suite baseline is 617 passed, 31 failed, and 1 error in the
legacy Tk MainWindow tests; the new V3 focused suites are green.

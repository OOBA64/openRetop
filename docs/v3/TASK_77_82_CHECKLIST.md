# openRetop V3 Tasks 77–82 implementation checklist

This checklist is the execution record for the sequential V3 architecture
refactor. Each task is completed only after its focused tests, architecture
checks, `python -m compileall -q src`, `git diff --check`, status update, and
task commit pass.

## Task 77 — Viewport, scene, picking, camera, and framing

- [x] Define immutable scene snapshot/render-item contracts with stable IDs and revisions.
- [x] Build toolkit-neutral scene snapshots from application state.
- [x] Isolate VTK host, actor factories/cache, synchronizer, picking, styles, and camera.
- [x] Implement incremental actor synchronization and structured picking.
- [x] Implement transformed/category-aware Frame All, Frame Selected, and project-load framing.
- [x] Add focused scene, camera, VTK, picking, and framing tests.
- [x] Run and record the existing MainWindow compatibility-suite baseline; the
  failures are isolated to the pre-existing compatibility adapter and carried
  forward as integration debt for the next task.

## Task 78 — Persistence, settings, import/export, CAD adapters, and bootstrap

- [x] Add typed project/settings repositories with migrations, validation, and warnings.
- [x] Preserve legacy project fields and unknown metadata through deterministic round trips.
- [x] Add import, display-proxy, STEP export, and progress/error boundaries.
- [x] Add a public CAD capability adapter without false feature claims.
- [x] Add an explicit composition root and dependency wiring.
- [x] Add boundary tests; legacy MainWindow orchestration remains a compatibility
  adapter until the Qt workflow is complete.

## Task 79 — Reusable standalone PySide6 workbench UI

- [x] Prove PySide6/QMainWindow, Qt offscreen, and VTK embedding support.
- [x] Create independent `packages/workbench_ui` package metadata and public API.
- [x] Implement shell, actions, schemas, panels/layout, tools, selection, inspector,
  scene tree, command palette, themes, and settings.
- [x] Add standalone demo and extension documentation.
- [x] Add zero-openRetop-import and Qt headless framework tests.

## Task 80 — openRetop V3 UI

- [ ] Add the supported V3 bootstrap/entry point while retaining Tk for parity.
- [ ] Wire scene tree, viewport snapshots, inspector, status, palette, dialogs, and progress.
- [ ] Route workflows through the centralized action registry and application controllers.
- [ ] Add the legacy-to-V3 parity matrix and workflow adapter coverage.
- [ ] Add Qt/VTK smoke and project/settings/open/save tests.

## Task 81 — Remove legacy shell and compatibility scaffolding

- [ ] Confirm each retained legacy workflow has V3 parity evidence or a documented replacement.
- [ ] Make V3 the normal entry point and remove superseded Tk presentation code and launch paths.
- [ ] Remove compatibility wrappers/re-exports only after all callers migrate.
- [ ] Reduce architecture allowlists and remove stale tests/imports/dead state.
- [ ] Add a production-code assertion that removed legacy presentation is not referenced.

## Task 82 — Final verification, optimization, packaging, and release candidate

- [ ] Run complete discovery, architecture, compile, startup, packaging, compatibility,
  and headless GUI verification.
- [ ] Add representative legacy/current fixtures and recovery/error coverage.
- [ ] Measure startup, load, scene synchronization, projection, and UI refresh paths.
- [ ] Remove evidenced dead code/stale docs and finalize setup, CI, and release docs.
- [ ] Record final metrics, limitations, risks, and manual review items in STATUS.

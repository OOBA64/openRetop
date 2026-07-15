# V3 release-candidate review

The branch is based on `v3-refactor` and contains distinct commits for Tasks
77–81. Task 82 is the final verification/documentation commit. It is a
reviewable release-candidate branch, not a merge into the base branch.

## Verification gates

- Focused Task 77, 78, 79, 80, 81, and 82 suites are run with the V3 virtual
  environment. Qt tests use `QT_QPA_PLATFORM=offscreen`.
- Compile and architecture checks are run from the repository root.
- The standalone `workbench_ui` wheel is built from its package metadata.
- `benchmark_scene_sync.py` reports synchronization throughput without a
  brittle CI threshold.
- Legacy and V3 minimal `.openretop` fixtures exercise parser migration and
  unknown metadata preservation.

## Manual review before merge

1. Run `python src/main.py` on a Windows desktop with VTK/OpenGL available.
2. Open a representative scan and verify transformed Frame All/Selected,
   project reload framing, manual curves, regions, surfaces, BREP/STEP, and
   undo/redo against the parity matrix.
3. Replace the current widget-internal Tk regression tests with equivalent V3
   behavior tests, then remove the remaining legacy shell and six allowlist
   entries as specified by Task 81.

## Release decision

The V3 core architecture, Qt framework, persistence boundaries, scene/camera
infrastructure, and supported entry point are ready for review. Final release
acceptance remains conditional on the Task 81 physical legacy-shell deletion
gate and a green complete behavior suite.

# V3 release-candidate review

## Automated release gates

1. Install Python 3.11 dependencies from `requirements.txt`.
2. Compile `src` and `packages/workbench_ui/workbench_ui`.
3. Run architecture metrics with `--fail-on-new`.
4. Run complete unittest discovery with
   `PYTHONPATH=src;packages/workbench_ui` and `QT_QPA_PLATFORM=offscreen`.
5. Run scene-sync and V3-workflow benchmarks (informative, no brittle timing
   threshold).
6. Build the standalone `workbench_ui` wheel and run the offscreen startup
   smoke.

The current record is green: 484 tests, zero guarded architecture violations,
zero practical cycles, zero legacy-window methods, and zero detectable
duplicate action/menu labels.

## Human Windows/OpenGL review

1. Launch `python src/main.py` and verify menus, docks, layout recovery,
   preferences, shortcuts, and command palette.
2. Import a representative scan; verify proxy diagnostics, camera navigation,
   named views, Frame All/Selected/Region/Source Curves, and transformed bounds.
3. Save/reopen and confirm transforms, colors, sections/results, curves/manual
   metadata, regions, surfaces/features, selection, and initial framing.
4. Exercise transform/undo, sections, repair/project/rebuild, manual curve
   create/edit/corners/snap/keep-on-mesh, regions/boundaries, preview and
   editable surfaces, deviation, and visibility/isolation.
5. With CAD available, rebuild planar/loft BREP records and export STEP; repeat
   without CAD to confirm honest disabled/error behavior.

## Decision

Automated V3 acceptance is achieved and the repository is ready for human
release-candidate review. The remaining items are platform/driver and
representative-data validation, not legacy-migration blockers.

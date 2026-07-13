# Task 82 — Full-System Verification, Optimization, Packaging, and V3 Release Candidate

# Common execution rules

This task is part of the openRetop V3 architecture refactor.

The repository starting point already includes Task 74: manual-curve controller/session extraction and behavior-preserving stabilization.

Mandatory rules:

- Complete only the numbered task in this file.
- Do not begin the next numbered task.
- Do not commit, push, merge, rebase, reset, tag, or switch branches. The external runner handles Git.
- Preserve current modeling behavior unless this task explicitly changes presentation behavior.
- Preserve backward compatibility for existing `.openretop` project files.
- Do not rewrite geometry algorithms merely because code is being moved.
- Do not delete, weaken, skip, or rewrite tests solely to obtain a passing result.
- Keep UI toolkit imports out of domain and application modules.
- Keep concrete Tk, Qt, VTK actor, dialog, and file-picker operations outside domain controllers.
- Keep VTK actor construction and mutation inside viewport infrastructure/presentation adapters.
- Use the existing public VTK and CadQuery/OCP/OCCT stack.
- Do not add proprietary CAD-kernel dependencies.
- Do not add new modeling features during the refactor.
- Reuse the existing accelerated MeshQueryService; do not reintroduce brute-force projection.
- Keep the application runnable after this task.
- Run focused tests during development.
- Before finishing, run `python -m compileall -q src` and the complete unittest suite with `PYTHONPATH=src`.
- Update `docs/v3/STATUS.md` with completed work, files changed, tests/results, risks, known issues, and the exact next-task starting point.
- Stop and report a blocker rather than bypassing a critical compatibility, test, or architecture requirement.

At completion, report implemented changes, files created/moved/removed, tests/results, compatibility risks, known remaining issues, and whether every acceptance criterion was satisfied.


## Purpose
Stabilize and verify the fully refactored application as a release candidate. Do not add modeling features.

## Required work
1. Run architecture metrics and correct remaining safe violations: cycles, duplicate actions/state, UI imports below presentation, VTK actor operations outside viewport, direct filesystem/dialog operations outside adapters, dead compatibility code.
2. Complete automated workflow coverage for:
   - startup with/without CAD
   - model import/proxy
   - Frame All/Selected and project initial framing
   - save/reopen
   - transforms/undo
   - sections
   - curve processing/project/rebuild
   - manual curve create/edit/corners/snap/Keep Curve On Mesh
   - regions/boundaries
   - previews/mesh-conforming loft
   - editable loft/four-boundary
   - BREP face/loft and STEP
   - preferences/colors/keybindings/layout
   - scene visibility/selection/isolation
   - deviation computation foundation
3. Use representative legacy and V3 project fixtures.
4. Profile startup, project load, scene snapshots, actor sync, mesh-query cache, manual curve editing, preview generation, tree/inspector refresh, large save/load. Remove measurable repeated rebuilds/conversions without semantic changes. Add informative benchmarks without fragile CI thresholds.
5. Add structured recovery/error reporting for corrupt/missing project/mesh, CAD unavailable, export failure, invalid geometry, VTK failure, settings corruption, and layout failure.
6. Define reproducible Windows developer/release setup. Update dependencies, metadata, entry point, version/build instructions, and optional packaging spec if safe.
7. Update CI for compile, architecture, core, Qt offscreen, VTK/headless, project migration, startup smoke, and practical Windows coverage.
8. Finalize README, install/run, architecture, workbench_ui, V3 user, project migration, contribution/testing, known limitations, and roadmap docs.
9. Remove dead code, orphan tests/docs, unused dependencies/settings, stale TODOs/debug prints, and duplicate actions only with evidence.
10. Update STATUS with final metrics and remaining issues.

## Acceptance
V3 launches and core workflows work, tests/CI are complete, architecture rules pass without unjustified violations, framing is correct, legacy projects load without loss, performance is measured/corrected where practical, workbench_ui remains independent, docs are current, and repository is ready for human V3 release-candidate review.

# Task 77 — Viewport, Scene Snapshot, Picking, Camera, and Framing Rework

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
Separate rendering and screen interaction from application state. Replace giant viewport argument plumbing and MainWindow coupling with declarative scene snapshots and focused VTK adapters. Resolve the known framing/project-load camera regression.

## Required work
1. Create toolkit-neutral scene-description types such as SceneSnapshot, MeshRenderItem, CurveRenderItem, SurfaceRenderItem, RegionRenderItem, SectionPlaneRenderItem, ToolPreviewState, SelectionRenderState, DisplayStyleSnapshot, and CameraRequest. Use stable IDs/revisions.
2. Split embedded viewport responsibilities into focused VTK modules: host/widget adapter, scene synchronizer, actor cache/factories, mesh/curve/surface/region/section/tool-preview actors, picking service, camera controller, style conversion. Keep an EmbeddedVTKViewport compatibility facade until Task 81.
3. Implement incremental rendering: create actors on appearance, update geometry only on revision change, update style/visibility separately, remove disappeared actors, reuse unchanged manual/surface geometry, and expose actor-update diagnostics.
4. Create structured pick results for mesh, scene object, manual control point, curve segment, and overbuild handle. Preserve camera navigation in every tool.
5. Create a tested camera controller for frame bounds/all/selected, reset, named orthographic/isometric views, finite camera vectors, clipping range, and degenerate bounds.
6. Fix:
   - Frame All fits visible geometry.
   - Frame Selected fits selected object/group.
   - transformed mesh/curves/regions/previews/BREP frame correctly.
   - opening a model frames after actors exist.
   - opening a project frames restored visible geometry after records/transforms restore.
   - ordinary refresh does not reset camera.
   - world origin is not used unless geometry warrants it.
7. Create a UI-independent scene builder from application state to SceneSnapshot.
8. Add scene-builder, camera math, headless VTK, actor sync, project-load framing, object-category framing, and no-unnecessary-rebuild tests.

## Acceptance
Rendering consumes SceneSnapshot, VTK actor operations are isolated, picking is structured, camera commands and project-load framing work, normal refresh preserves camera, actor updates are incremental, and full tests pass.

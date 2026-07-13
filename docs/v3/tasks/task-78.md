# Task 78 — Persistence, Settings, Import/Export, CAD Adapters, and Bootstrap Boundaries

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
Isolate external systems behind ports/adapters, centralize construction, and make schema compatibility measurable. Remove direct filesystem/dialog/settings/loader/exporter/CAD coupling from controllers and presentation.

## Required work
1. Add ProjectRepository protocol and JSON implementation with deterministic serialization, explicit schema version/migrations, validation, recoverable warnings/errors, mesh-path resolution, unknown metadata preservation, and golden legacy/current fixtures.
2. Preserve all current project data: mesh reference/name/visibility, transforms/origin, display/colors, sections/results, curves/metadata, regions, preview surfaces, BREP, editable loft/four-boundary features, and persisted selection IDs.
3. Add SettingsRepository protocol and JSON implementation with validation, normalization, version migration, and UI-independent models.
4. Add explicit mesh-import, display-proxy, STEP-export, project-open/save, and export-registration services. File dialogs stay presentation-only. Services emit structured progress events.
5. Refine CadQuery/OCP/OCCT behind a public adapter exposing only implemented availability, wire, planar face, loft, tessellation, and STEP capabilities. No proprietary kernel references or false trim/intersection claims.
6. Create a bootstrap/composition root constructing state/store, event publisher, action/command registry, MeshQueryService, CAD backend, repositories, import/export services, controllers, scene builder, and presentation adapter. Avoid hidden singletons/cycles.
7. Move modules toward documented V3 layers only when ownership improves; use temporary compatibility re-exports until Task 81.
8. Add project/settings migration, deterministic round-trip, unknown metadata, missing mesh, in-memory repository, progress event, CAD available/unavailable, bootstrap, and startup tests.

## Acceptance
Persistence/settings/import/export/CAD are behind explicit adapters, legacy projects load without data loss, dialogs are presentation-only, a composition root exists with test fakes, and full tests pass.

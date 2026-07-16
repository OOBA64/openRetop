# V3 known limitations

- CAD/BREP construction and STEP export depend on a working CadQuery/OCP
  installation. Trim and intersection are explicitly unavailable in the
  current public adapter.
- Automated Qt tests use the offscreen platform. Driver-specific OpenGL output,
  DPI behavior, and sustained interactive navigation require a Windows desktop
  visual pass.
- Checked-in legacy/current project fixtures are deliberately small; large
  customer scans and projects remain a release-review input rather than source
  fixtures.
- Runtime CAD objects are not serialized. BREP records load safely with
  `rebuild_required` status and must be rebuilt before STEP export.
- Region selection is connected-normal growth from one seed with a triangle
  cap; paint/add/subtract selection is not part of the retained V3 feature set.
- Existing preview-surface algorithms remain preview meshes, not replacements
  for CAD-kernel BREP generation.

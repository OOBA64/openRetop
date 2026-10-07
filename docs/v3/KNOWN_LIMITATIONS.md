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

## Found during the post-82F rework

- Region selection runs on the display mesh. For scans above ~150k triangles that
  is a decimated proxy, so region triangle indices, and boundaries extracted from
  them, refer to the proxy and not the source mesh. Only one region can be active.
- Tiny-curve diagnostic thresholds (`CURVE_TINY_MIN_*` in `project_data.py`) are in
  raw model units, not converted from millimetres like the other tolerances.
- A section curve with a tolerance tighter than the scan noise cannot meet it; the
  fit stops when more control points stop helping and reports the real error.
- Sharp corners are found by turn angle (50 degrees over an arc-length window). A
  rounded corner with radius below ~20x the fit tolerance is treated as sharp.
- Section sampling and fitting happen on the worker thread, but a single large
  command still holds the GIL in Python loops (manual-curve/surface-preview code).
- mypy passes on new modules; 56 legacy modules are listed under `ignore_errors`
  in `pyproject.toml` (~620 errors) and should be cleaned up one at a time.
- `application/manual_curve_controller.py` (1.7k lines), `brep_controller.py`
  (1.5k) and `presentation/qt/main_window.py` (1.7k) are the largest remaining
  modules.

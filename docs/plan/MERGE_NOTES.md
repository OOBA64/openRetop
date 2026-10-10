# Merge into main: what changes (October 2026)

`main` was at `a0b2c53`; the refactor branch adds 80+ commits on top of it (a
fast-forward, no rewritten history).

| | main before | after the merge |
|---|---|---|
| Shell | Tkinter app (`src/app`) | One PySide6 workbench with Scan / Surface / Solid workspaces, command palette, view cube, adaptive grid |
| Scan handling | Loads meshes | Welded STL load, units chosen at import and stored, grab/rotate with axis locks and typed values, measure, region select |
| Curves | Stored curves, manual curve tool, repair tools | 3D Sketch: curves that run along the scan and can follow body lines, editable points, split/close/reverse; sections and region boundaries become sketch curves |
| Surfaces | Preview and BREP lofts/fills via CadQuery in the UI process | Fit Surface, Loft, Fill, Extend, Trim and sew into solids, run in a separate kernel process (a crash cannot take the window down) |
| Solids | None | Section Sketch (lines and arcs fitted to a scan cut, hand-editable) and Extrude with depth measured on the scan |
| Checking | Point-to-mesh deviation analysis | Compare colours the scan by distance to the model |
| Export | STEP of one BREP surface | STEP or IGES of the selected or visible model, declaring the project unit |
| Projects | v1 JSON | Atomic saves, relative scan paths, schema migrations; old curves come back as sketch curves, old surfaces are reported as not loaded |
| Quality | 40 test files, no packaging | 756 tests, ruff, mypy, architecture checks, CI on Windows and Linux |

Known limits: the 4 tests that need a visible desktop window are skipped in CI;
the parametric feature timeline and constraint solver are planned in
[PARAMETRIC_PLAN.md](PARAMETRIC_PLAN.md), not built yet.

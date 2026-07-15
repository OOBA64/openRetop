# openRetop V3 parity matrix

The V3 shell is action-registry driven. Legacy workflow names remain in the
matrix while migration evidence is accumulated; each row identifies the
controller or adapter that owns the behavior.

| Legacy capability | V3 location | Action/controller boundary | Evidence |
| --- | --- | --- | --- |
| Open model | File > Open Model | `file.open_model` / `MeshImportService` | `test_task80_v3_ui.py` |
| Open/save project | File menu | `ProjectFileService` / `JsonProjectRepository` | `test_task78_boundaries.py` |
| Frame All/Selected | View menu and palette | `view.frame_all`, `view.frame_selected` / Task 77 camera | `test_task77_viewport.py` |
| Scene selection/visibility | Scene tree/context | `SelectionController`, `VisibilityController` | controller and V3 UI tests |
| Transforms | Properties/tool mode | `TransformController` / `ToolModeManager` | controller regression suite |
| Sections/results | Scene tree and inspector | `SectionController` | section controller suite |
| Stored/manual curves | Scene tree and Create/Modify menus | `CurveController`, `ManualCurveController` | curve/controller suites |
| Regions | Scene tree and Modify menu | `RegionController` | region controller suite |
| Preview surfaces | Scene tree and inspector | `SurfaceController` | surface controller suite |
| BREP/STEP | File/Create menus | `BrepController`, `PublicCadAdapter`, `StepExportService` | BREP controller suite |
| Undo/redo | Edit menu and shortcuts | `UndoStack` / central action registry | application core suite |
| Preferences/layout | Properties and shell settings | `JsonSettingsRepository`, `FrameworkSettings` | settings and workbench suites |

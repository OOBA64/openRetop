# openRetop V3 parity matrix

All retained user intent is represented by stable definitions in
`application.actions.CORE_ACTIONS`. `WorkflowService` owns toolkit-neutral
routing; the Qt shell handles only presentation actions, dialogs, camera
requests, pointer translation, and result display.

| Capability | V3 boundary | Evidence |
| --- | --- | --- |
| Startup/CAD capability | `bootstrap.create_application`, `PublicCadAdapter` | Task 78/82, CAD adapter tests |
| Model import/proxy/diagnostics | `MeshImportService`, `DisplayProxyService` | loader/proxy and Task 80 tests |
| New/open/save/recent/dirty/title | `ProjectFileService`, Qt file adapter | Task 78/80/project tests |
| Complete project restore/selection | `project_session.restore_project_state` | Task 78/80 fixture and round-trip tests |
| Preferences/colors/keybindings/layout | settings repository, inspector dialog, framework settings | settings, keybinding, Task 79/80 tests |
| Incremental viewport rendering | `SceneSnapshot`, `SceneSynchronizer`, actor factories/cache | Task 77 and scene-sync benchmark |
| Picking and tool pointer input | `PickingService`, `QtSceneViewport` | Task 77/80 pointer tests |
| Named views and framing | `CameraController`, `CameraRequest` | Task 77/80 camera tests |
| Scene tree selection/rename/delete | selection/scene controllers | scene controller, Task 79/80 tests |
| Visibility/isolate/show all | visibility controller | scene controller/workflow tests |
| Transform/numeric/origin/undo | transform controller, undo stack | transform/workflow tests |
| Section planes/results | section controller | section and workflow tests |
| Curve repair/project/rebuild/validation | curve controller | curve, projection, validation tests |
| Manual create/edit/types/corners/snap | manual-curve controller/session | manual controller/V2 and Task 80 tests |
| Region grow/recompute/boundary | region controller | region, boundary, pointer tests |
| Preview/conforming/network surfaces | surface controller | surface preview/controller tests |
| Editable loft/four-boundary | BREP/surface controllers and feature records | surface feature/controller tests |
| BREP face/loft/rebuild/STEP | BREP controller, CAD adapter, export service | BREP/CAD/export tests |
| Deviation/diagnostics | analysis controller, mesh query service | analysis/mesh-query/workflow tests |
| Undo/redo | controller undo payloads and `UndoStack` | controller/workflow/undo tests |
| All registered commands | action registry + command dispatcher + workflow | `test_v3_workflow_service.py` |

The former Tk shell, menus, preferences, scene browser, viewport facade, and
their private-widget tests were removed after this behavior evidence passed.

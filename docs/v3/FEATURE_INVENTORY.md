# openRetop V3 feature inventory

| Feature family | Authoritative implementation | V3 presentation |
| --- | --- | --- |
| Project lifecycle and recovery | project DTO/I/O/session plus repository/service | File actions, recent files, dirty/title prompts, progress/errors |
| Settings/preferences/layout | settings DTO/I/O/repository and framework settings | typed Preferences dialog, keybindings, colors, dock restore/reset |
| Mesh import/proxy/diagnostics | mesh loader/state/proxy and import/proxy services | Open Model, proxy quality, inspector/diagnostics |
| Scene selection/visibility/delete | selection, visibility, and scene controllers | hierarchical scene tree/context actions |
| Viewport/camera/framing | scene builder/types/synchronizer/actors/picking/camera | QVTK host and structured pointer adapter |
| Mesh and section transforms | transform math/controller and undo payloads | modal pointer tool plus numeric inspector |
| Sections and fitted curves | section controller, geometry sections/curves | Create/Modify actions, tree, inspector |
| Curve repair/project/rebuild | curve controller and curve domain modules | Modify actions and contextual state |
| Manual curves | manual controller/session/storage/sampling | pointer placement/edit, typed options, Enter/Escape lifecycle |
| Regions and boundaries | adjacency, region state/controller, boundary/plane-fit | pointer seed/grow, inspector, boundary actions |
| Preview surfaces | surface controller/state/preview builders | create/rebuild/display/inspector actions |
| Editable surface features | loft/four-boundary feature records/controllers | feature tree nodes and source/rebuild actions |
| BREP and STEP | BREP controller, public CAD adapter, export service | create/rebuild/select/export actions and capability state |
| Deviation analysis | analysis controller and accelerated mesh query | Inspect actions and diagnostics |
| Undo/redo | application undo stack and controller undo payloads | Edit menu, shortcuts, action enablement |

All retained feature families have behavior tests. See `V3_PARITY_MATRIX.md`
for the evidence map and `KNOWN_LIMITATIONS.md` for intentionally unimplemented
capabilities.

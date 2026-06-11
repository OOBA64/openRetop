# Roadmap

## MVP
- Import mesh
- Display mesh
- Extract cross-sections
- Fit splines
- Fit surfaces
- Export CAD

## Project Files
- openRetop now has a project file format.
- Project files use the `.openretop` extension and are stored as human-readable JSON.
- Mesh data is not embedded in project files.
- Project files currently save mesh paths, object transforms, display settings, and section settings only.
- Opening a project now reads metadata and reloads the referenced mesh when `mesh_path` is available; projects without a mesh path still open metadata-only.

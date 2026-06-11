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
- Opening a project currently reads metadata only; loading the referenced mesh and reconstructing the scene will come later.

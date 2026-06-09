# Agent Instructions

This is an early Python prototype for scan-to-BRep reverse engineering.

Rules:
- Do not add new third-party dependencies unless you also add them to requirements.txt.
- Prefer existing dependencies: numpy, scipy, open3d, trimesh, pyvista, geomdl.
- Do not add OpenCascade, CGAL, Qt, CMake, or C++ yet.
- Keep changes small.
- Do not rewrite the project structure.
- Every new script must include a simple command showing how to run it.
- The current goal is: load mesh, display mesh, extract cross-section, fit spline.
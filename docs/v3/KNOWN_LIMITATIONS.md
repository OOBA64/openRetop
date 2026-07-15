# V3 known limitations

- The supported entry point is the PySide6 V3 shell. The superseded Tk
  `src/app/main_window.py`, Tk menus/dialogs, and compatibility viewport are
  still present for the existing legacy regression suite. Their physical
  removal is the remaining Task 81 migration hold point.
- The V3 shell exposes all central action definitions and fully wires framing,
  visibility, undo/redo, named views, model import, project persistence, and
  settings/CAD boundaries. Advanced legacy-specific inspectors and some
  feature dialogs still need parity adapters before the Tk implementation can
  be removed safely.
- The repository has no checked-in representative real-world legacy project
  fixtures; compatibility verification currently uses generated project data
  and legacy parser tests.
- CAD/BREP availability depends on the optional CadQuery/OCP installation.
  Trim and intersection are intentionally reported unavailable.
- Multiple Qt/VTK windows in one Windows offscreen interpreter can emit OpenGL
  initialization warnings. Isolated V3 smoke tests pass in the supported V3
  environment.

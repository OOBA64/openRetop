# openRetop desktop shell

Run it with `openretop` (or `python -m openretop`).

The independent `workbench_ui` framework provides the main window, menus,
workspace tabs, toolbars, docks, scene tree, property inspector, command
palette (`Ctrl+K`), themes and the VTK host. The openRetop presentation supplies
scene records and dispatches stable actions into UI-independent controllers.

- **Workspaces.** *Scan* (align, sections, regions, measure), *Surface* (3D
  Sketch, Fit Surface, Loft, Fill, Extend, Trim, Compare) and *Solid* (Section
  Sketch, Edit Sketch, Extrude). Starting a tool from the menu or palette
  switches to its workspace; the last one used is remembered.
- **File** creates/opens/saves projects, opens STL/OBJ/PLY scans, edits
  preferences, and exports model surfaces and bodies to STEP or IGES in the
  project's unit.
- **View** has grid/axes controls, named views, Frame All, Frame Selected and
  display-proxy quality.
- The **Scene** dock lists the scan, the 3D Sketch, the model, section planes
  and results, and the selected region, with visibility, rename and context
  actions. Clicking in the viewport selects what was hit and nothing else.
- The **Properties** dock is contextual; with nothing selected it shows *Model &
  Next steps*, and while a tool is running it shows that tool's panel.

Tool hints appear on the canvas. Enter confirms and Escape cancels the active
tool; right-button and middle-button navigation stay available inside tools.

Projects keep the scan reference and its transform, display options, section
planes and results, the region, the 3D Sketch, sketches and the model's
surfaces and bodies. Curves saved by the retired curve tools open as 3D Sketch
curves; surfaces from those tools are not loaded, with a warning.

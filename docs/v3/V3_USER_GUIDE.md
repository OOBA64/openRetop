# openRetop V3 desktop shell

Run the only supported shell with `python src/main.py`.

The independent `workbench_ui` framework provides the main window, menus,
toolbars, docks, scene tree, property inspector, command palette, themes, and
VTK host. The openRetop presentation supplies scene records and dispatches
stable actions into UI-independent controllers.

- File creates/opens/saves projects, imports STL/OBJ/PLY, edits preferences,
  and exports a rebuilt selected BREP to STEP.
- View contains grid/axes controls, named views, Frame All, Frame Selected,
  region/source-curve framing, and proxy quality.
- Create and Modify expose section, transform, curve/manual-curve, region,
  preview-surface, editable-feature, and BREP workflows.
- Inspect exposes project/mesh/selection diagnostics and deviation analysis.
- The Scene dock supports multi-selection, visibility, rename, context actions,
  source groups, regions, surfaces, and editable features.
- The Properties dock is contextual and validates values before dispatch.

Tool instructions appear in the status area. Enter applies or finishes active
transform, manual-curve, and region tools; Escape cancels or exits them. Mouse
picks return structured scene/mesh results, and right-button camera navigation
remains available while modeling tools are active.

Projects preserve transforms, display options/colors, section planes/results,
curves and manual metadata, regions, preview/BREP records, editable features,
and stable scene selection. Runtime CAD objects are rebuilt after opening.

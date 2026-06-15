"""Application menu construction for openRetop."""

from __future__ import annotations

from tkinter import Menu


def build_menu_bar(app: object) -> Menu:
    menu_bar = Menu(app.root, tearoff=False)

    app.file_menu = Menu(menu_bar, tearoff=False)
    app.file_menu.add_command(label="New Project", command=app.new_project)
    app.file_menu.add_command(label="Open Project", command=app.open_project)
    app.file_menu.add_command(label="Save Project", command=app.save_project)
    app.file_menu.add_command(label="Save Project As", command=app.save_project_as)
    app.file_menu.add_command(label="Open Model", command=app.open_model)
    app.file_menu.add_command(
        label="Recent Files",
        command=lambda: app._not_implemented("Recent Files"),
    )
    app.file_menu.add_command(label="Exit", command=app._on_exit)
    menu_bar.add_cascade(label="File", menu=app.file_menu)

    app.edit_menu = Menu(menu_bar, tearoff=False)
    app.edit_menu.add_command(label="Undo", command=app.undo)
    app.edit_menu.add_command(label="Redo", command=app.redo)
    app.edit_menu.add_command(label="Rename Selected", command=app.rename_selected)
    app.edit_menu.add_command(label="Delete Selected", command=app._delete_selected_if_safe)
    app.edit_menu.add_command(label="Preferences", command=app.open_preferences)
    menu_bar.add_cascade(label="Edit", menu=app.edit_menu)

    app.view_menu = Menu(menu_bar, tearoff=False)
    app.view_menu.add_command(label="Frame All", command=app.frame_all)
    app.view_menu.add_command(label="Frame Selected", command=app.frame_selected)
    app.view_menu.add_command(label="Reset View", command=app.reset_view)
    app.view_menu.add_command(label="Top View", command=lambda: app.set_named_view("top"))
    app.view_menu.add_command(label="Bottom View", command=lambda: app.set_named_view("bottom"))
    app.view_menu.add_command(label="Front View", command=lambda: app.set_named_view("front"))
    app.view_menu.add_command(label="Back View", command=lambda: app.set_named_view("back"))
    app.view_menu.add_command(label="Left View", command=lambda: app.set_named_view("left"))
    app.view_menu.add_command(label="Right View", command=lambda: app.set_named_view("right"))
    app.view_menu.add_command(
        label="Isometric View",
        command=lambda: app.set_named_view("isometric"),
    )
    app.view_menu.add_checkbutton(
        label="Show Grid",
        variable=app.show_grid,
        command=app._on_view_option_changed,
    )
    app.view_menu.add_checkbutton(
        label="Show Axes",
        variable=app.show_axes,
        command=app._on_view_option_changed,
    )
    app.view_menu.add_checkbutton(
        label="Show Axis Gizmo",
        variable=app.show_axis_gizmo,
        command=app._on_view_option_changed,
    )
    app.view_menu.add_checkbutton(
        label="Show View Controls",
        variable=app.show_view_controls,
        command=app._on_view_option_changed,
    )
    menu_bar.add_cascade(label="View", menu=app.view_menu)

    app.scene_menu = Menu(menu_bar, tearoff=False)
    app.scene_menu.add_command(label="Show All", command=app.show_all_scene_objects)
    app.scene_menu.add_command(label="Hide Selected", command=app.hide_selected_scene_objects)
    app.scene_menu.add_command(label="Show Selected", command=app.show_selected_scene_objects)
    app.scene_menu.add_command(label="Isolate Selected", command=app.hide_unselected_scene_objects)
    app.scene_menu.add_command(
        label="Toggle Selected Visibility",
        command=app.toggle_selected_scene_objects,
    )
    app.scene_menu.add_command(label="Delete Selected", command=app._delete_selected_if_safe)
    app.scene_menu.add_command(label="Frame Selected", command=app.frame_selected)
    menu_bar.add_cascade(label="Scene", menu=app.scene_menu)

    app.sections_menu = Menu(menu_bar, tearoff=False)
    app.sections_menu.add_command(label="Add Section Plane", command=app.add_section_plane)
    app.sections_menu.add_command(
        label="Delete Selected Section Plane",
        command=app.delete_active_section_plane,
    )
    app.sections_menu.add_command(label="Compute Section", command=app.compute_section)
    app.sections_menu.add_command(
        label="Clear Active Section Result",
        command=app.clear_active_section_result,
    )
    app.sections_menu.add_command(
        label="Clear All Section Results",
        command=app.clear_all_section_results,
    )
    menu_bar.add_cascade(label="Sections", menu=app.sections_menu)

    app.curves_menu = Menu(menu_bar, tearoff=False)
    app.curves_menu.add_command(
        label="Create Manual Curve",
        command=app.start_manual_curve_mode,
    )
    app.curves_menu.add_command(
        label="Finish Manual Curve",
        command=app._confirm_manual_curve,
    )
    app.curves_menu.add_command(
        label="Cancel Manual Curve",
        command=lambda: app._cancel_manual_curve_mode(status="Manual curve cancelled"),
    )
    app.curves_menu.add_checkbutton(
        label="Snap to Mesh",
        variable=app.manual_curve_snap_to_mesh,
        command=app._on_manual_curve_snap_to_mesh_changed,
    )
    app.curves_menu.add_command(label="Join Selected Curves", command=app.join_selected_curves)
    app.curves_menu.add_command(
        label="Auto-Close Selected Curve",
        command=app.auto_close_selected_curve,
    )
    app.curves_menu.add_command(
        label="Simplify Selected Curve",
        command=app.simplify_selected_curve,
    )
    app.curves_menu.add_command(
        label="Smooth Selected Curve",
        command=app.smooth_selected_curve,
    )
    app.curves_menu.add_command(label="Select Tiny Curves", command=app.select_tiny_curves)
    app.curves_menu.add_command(label="Hide Tiny Curves", command=app.hide_tiny_curves)
    app.curves_menu.add_command(label="Delete Tiny Curves", command=app.delete_tiny_curves)
    app.curves_menu.add_command(label="Delete Selected Curve", command=app.delete_selected_curve)
    menu_bar.add_cascade(label="Curves", menu=app.curves_menu)

    app.surfaces_menu = Menu(menu_bar, tearoff=False)
    app.surfaces_menu.add_command(
        label="Fill Closed Curve",
        command=app.fill_closed_curve,
    )
    app.surfaces_menu.add_command(
        label="Loft Between Two Curves",
        command=app.loft_between_two_curves,
    )
    app.surfaces_menu.add_command(
        label="Select Source Curves",
        command=app.select_source_curves_for_active_surface,
    )
    app.surfaces_menu.add_command(
        label="Isolate Source Curves",
        command=app.isolate_source_curves_for_active_surface,
    )
    app.surfaces_menu.add_command(
        label="Show Source Curves",
        command=app.show_source_curves_for_active_surface,
    )
    app.surfaces_menu.add_command(
        label="Frame Source Curves",
        command=app.frame_source_curves_for_active_surface,
    )
    app.surfaces_menu.add_command(
        label="Toggle Surface Visibility",
        command=app.toggle_active_surface_visibility,
    )
    app.surfaces_menu.add_command(label="Delete Selected Surface", command=app.delete_selected_surface)
    menu_bar.add_cascade(label="Surfaces", menu=app.surfaces_menu)

    app.tools_menu = Menu(menu_bar, tearoff=False)
    app.tools_menu.add_command(label="Select Model", command=app.select_model)
    app.tools_menu.add_command(label="Select Section Plane", command=app.select_section_plane)
    app.tools_menu.add_command(label="Move", command=app.start_move_transform)
    app.tools_menu.add_command(label="Rotate", command=app.start_rotate_transform)
    app.tools_menu.add_command(label="Manual Curve", command=app.start_manual_curve_mode)
    app.tools_menu.add_command(label="Region Select", command=app.start_region_select_mode)
    menu_bar.add_cascade(label="Tools", menu=app.tools_menu)

    app.help_menu = Menu(menu_bar, tearoff=False)
    app.help_menu.add_command(label="About", command=app._about_placeholder)
    app.help_menu.add_command(label="Hotkeys", command=lambda: app._not_implemented("Hotkeys"))
    menu_bar.add_cascade(label="Help", menu=app.help_menu)

    app.root.configure(menu=menu_bar)
    return menu_bar

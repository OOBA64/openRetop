# V3 Command and Action Inventory

This is the Task 75 baseline of user intent, invocation surfaces, and command
contracts. It distinguishes three things that were previously easy to conflate:

- an **action** is stable presentation-independent user intent, with label,
  shortcut, enablement, visibility, and check-state metadata;
- a **command** is a request dispatched to a handler using explicit
  dependencies and returning a structured result; and
- a **legacy entry point** is a current `OpenRetopWindow` method/callback that
  still performs coordination directly.

Only the six representative actions in the next section are registered in Task
75. Every other callable behavior remains supported but is explicitly marked
legacy-only. Names in the legacy catalog are not silently promoted to stable V3
IDs; later tasks must choose and test those IDs when the owning workflow moves.

## Authoritative Task 75 registry

All six definitions are created by `create_core_action_registry()` in
`application/actions.py`. Every action is visible under the current
`ActionContext`, all are non-checkable, and their `metadata` records the legacy
handler plus `migration_task: 75`.

| Stable action ID | Command/handler ID | Label / category | Default shortcut | Enabled when | Compatibility wrapper | Current result/effect |
|---|---|---|---|---|---|---|
| `view.frame_all` | `viewport.frame_all` | Frame All / View | none | `always` | `frame_all()` | Success status `View framed`; emits a `FRAME_ALL` viewport request. |
| `view.frame_selected` | `viewport.frame_selected` | Frame Selected / View | `F` | `has_scene_selection` | `frame_selected()` | Expands group selection. Regions use region framing; mesh requests frame-all; other available geometry emits finite `FRAME_BOUNDS` tagged `target=selection`. Empty/unavailable geometry is a successful no-op with status. |
| `scene.show_all` | `scene.show_all` | Show All / Scene | `Alt+H` | `has_scene_objects` | `show_all_scene_objects()` | Makes every persistent visibility target visible, records the existing visibility undo command, synchronizes scene/UI, and marks dirty only when persistent state changed. |
| `scene.toggle_visibility` | `scene.toggle_visibility` | Toggle Visibility / Scene | `H` | `has_scene_selection` | `toggle_selected_scene_objects()` | Expands selected group IDs, toggles each target, records the existing visibility undo command, synchronizes scene/UI, and marks dirty for persistent changes. Empty selection is a successful no-op. |
| `edit.undo` | `history.undo` | Undo / Edit | `Ctrl+Z` | `can_undo` | `undo()` | Calls the injected `UndoPort`; a performed undo synchronizes scene state, reports `changed=True`, `dirty=True`, and requests action-state refresh. Empty history reports `Nothing to undo`. |
| `edit.redo` | `history.redo` | Redo / Edit | `Ctrl+Y` | `can_redo` | `redo()` | Calls the injected `UndoPort`; a performed redo synchronizes scene state, reports `changed=True`, `dirty=True`, and requests action-state refresh. Empty history reports `Nothing to redo`. |

The registry definitions are authoritative for these labels and shortcuts. Menus
obtain the representative labels from the registry; wrappers exist so current
menus, keybindings, tests, and external callers retain their public call shape.

## `ActionDefinition` contract

An action definition is immutable and contains:

| Field | Contract |
|---|---|
| `id` | Stable lower-case identifier matching `^[a-z][a-z0-9_.-]*$`; unique within a registry. |
| `label` | Non-empty user-facing label. Labels need not be globally unique. |
| `description` | Non-empty description of user intent, not widget mechanics. |
| `category` | Non-empty presentation grouping. |
| `shortcut` | Canonical display shortcut or `None`. Settings may currently override legacy routing separately. |
| `command_id` | Stable lower-case dispatcher key using the same ID grammar. |
| `enabled_when` | Non-empty tuple of named `ActionCondition` values; all must hold. |
| `visible_when` | Non-empty tuple of named `ActionCondition` values; all must hold. |
| `checkable` | Whether the presentation may expose a checked state. |
| `checked_when` | Optional named condition; invalid unless `checkable=True`. |
| `metadata` | Read-only copy of extension metadata; must not carry widgets, actors, or callbacks. |

Task 75 defines the conditions `always`, `has_scene_objects`,
`has_scene_selection`, `can_undo`, and `can_redo`. `ActionRegistry` preserves
registration order and rejects duplicate IDs. `ActionDefinition.resolve()`
returns a presentation-neutral `ActionState(enabled, visible, checked)`.

## Command dispatch contract

`CommandRequest` carries a stable `command_id`, optional originating `action_id`,
and an immutable payload mapping. `CommandDispatcher` is instance-scoped and
rejects duplicate handlers. A handler receives the command plus the typed
`ApplicationDependencies` container:

| Dependency | Port |
|---|---|
| `events` | Concrete typed `EventPublisher`. |
| `selection` | `SelectionProvider.snapshot() -> SelectionSnapshot`. |
| `undo` | `UndoPort` with `can_undo`, `can_redo`, `undo()`, and `redo()`. |

The container has named fields and no string lookup, mutation API, singleton, or
global registration mechanism. It is composition, not a service locator.

For a registered command, dispatch publishes `CommandEvent(STARTED)`, invokes
the handler, then publishes `CommandEvent(COMPLETED)` with success/errors. An
unknown command returns a structured failure and publishes completion.
`CommandRejected` becomes a structured failure. Unexpected exceptions publish a
failed completion event and are re-raised; they are not hidden as successful
results. Non-`CommandResult` handler returns are rejected.

## Structured result contract

Every command handler returns `CommandResult` with:

- `success`, human-readable `status`, `warnings`, and `errors`;
- `changed` and project `dirty` flags;
- zero or more viewport and UI requests;
- an optional `UndoPayload` (`name`, `undo()`, `redo()`); and
- read-only metadata.

A successful result cannot contain errors. Bounds requests require finite 3D
minimum and maximum values. The request vocabulary at this baseline is:

| Request family | Kinds | Presentation adapter behavior |
|---|---|---|
| Viewport | `REFRESH`, `FRAME_ALL`, `FRAME_BOUNDS`, `RENDER` | Refresh scene, frame model, frame finite bounds (falling back to model framing only for an older viewport adapter), or request a render. |
| UI | `REFRESH_ACTIONS`, `REFRESH_SCENE_BROWSER`, `SYNC_WORKFLOW` | Recompute menu/action state, rebuild browser presentation, or synchronize workflow controls. |

`OpenRetopWindow._apply_command_result()` is the current Tk/VTK compatibility
adapter. It pushes an optional undo payload, fulfills requests, sets dirty state,
updates status text, and publishes a `StatusEvent`. The representative
visibility handlers still push their existing callback undo entries internally;
this is preserved behavior, not the target shape for newly extracted commands.

## Event and selection contracts used by commands

The typed publisher supports `StateChangedEvent`, `SelectionChangedEvent`,
`SceneChangedEvent`, `DirtyChangedEvent`, `CommandEvent`,
`ActiveToolChangedEvent`, and `StatusEvent`. Delivery is synchronous, ordered by
subscription, type-aware (base-event subscribers receive derived events), and
cancellable through an idempotent `Subscription`.

`SelectionSnapshot` is immutable, deduplicates ordered IDs in `from_ids()`,
requires a primary ID to be in the selection, and can classify mesh, section
plane/result, curve, surface, region, or generic scene-node items. The Task 75
window adapter currently snapshots scene-node IDs from the scene browser plus
legacy active selection.

## Keyboard routing baseline

These settings are persisted in `AppKeybindSettings`; the defaults below are
current behavior, not a new global shortcut service.

| Settings field | Default | Routed legacy intent | Registry status |
|---|---|---|---|
| `undo` | `Ctrl+Z` | `undo()` | Registered as `edit.undo`. |
| `redo` | `Ctrl+Y` | `redo()`; `Ctrl+Shift+Z` is also accepted as a hard-coded alias | Registered as `edit.redo`. |
| `rename_selected` | `F2` | `rename_selected()` | Legacy-only. |
| `toggle_visibility` | `H` | `toggle_selected_scene_objects()` | Registered as `scene.toggle_visibility`. |
| `isolate_selected` | `Shift+H` | `hide_unselected_scene_objects()` | Legacy-only. |
| `show_all` | `Alt+H` | `show_all_scene_objects()` | Registered as `scene.show_all`. |
| `frame_selected` | `F` | `frame_selected()` | Registered as `view.frame_selected`. |
| `move` | `G` | `start_move_transform()` | Legacy-only. |
| `rotate` | `R` | `start_rotate_transform()` | Legacy-only. |
| `confirm_transform` | `Enter` | Commit active transform, or clear pending transform mode | Legacy-only. |
| `cancel_transform` | `Esc` | Restore/cancel active transform, or clear pending transform mode | Legacy-only. |
| `delete_selected` | `Delete` | `_delete_selected_if_safe()` | Legacy-only. |

Context takes precedence over the general map. While a manual curve is active,
`Backspace`, `C`, `Enter`, and `Esc` route to manual-curve submode behavior and
other application shortcuts are suppressed. During region selection, `Esc`
cancels that tool. During transform interaction, `X`, `Y`, and `Z` toggle world
axis constraints; `N` toggles section-plane-normal movement when applicable.
Navigation mouse gestures remain viewport input, not application actions.

## Legacy command catalog

The following tables inventory callable user behavior not yet represented by an
`ActionDefinition`. "Contextual" means current availability is computed by
widget/menu state and guard clauses in `OpenRetopWindow`, not by a reusable
application-layer condition.

### File, project, settings, and shell

| User intent / current label | Legacy entry point | Invocation surfaces | Availability / side effects |
|---|---|---|---|
| New Project | `new_project()` | File menu, Scene sidebar | Always; prompts for dirty project, clears scene/history, creates untitled state. |
| Open Project | `open_project()` | File menu | Always; file picker, dirty prompt, tolerant project restore, optional mesh reload. |
| Save Project | `save_project()` | File menu, Scene sidebar | Always; writes current path or delegates to save-as. |
| Save Project As | `save_project_as()` | File menu, Scene sidebar | Always; file picker and project serialization. |
| Open Model | `open_model()` / `load_model()` | File menu, Scene sidebar | Disabled during load; model file picker, staged import/proxy/scene setup, clears incompatible state/history. |
| Delete mesh/model | `delete_mesh()` | Model context, generic Delete routing | Requires mesh and confirmation; removes source-dependent scene data. |
| Preferences | `open_preferences()` | Edit menu | Always; concrete Tk dialog and settings validation/apply. |
| Exit | `_on_exit()` | File menu, window close protocol | Dirty prompt, saves app settings, stops viewport, destroys root. |
| About | `_about_placeholder()` | Help menu | Presentation-only informational dialog. |
| Recent Files | `_not_implemented("Recent Files")` | Disabled File item | Placeholder; no command behavior. |
| Hotkeys | `_not_implemented("Hotkeys")` | Help menu | Placeholder; no reference dialog. |
| Switch workbench | `_set_active_workbench()` | Workbench buttons and automatic selection routing | Presentation navigation among Scene/Transform/Sections/Curves/Surfaces/Manual RE/Analysis; must not dirty the project. |

### Scene selection, visibility, naming, and deletion

| User intent / current label | Legacy entry point | Invocation surfaces | Availability / side effects |
|---|---|---|---|
| Select Model | `select_model()` | Scene/Tools controls, scene browser | Requires loaded mesh. |
| Select Section Plane | `select_section_plane()` / `select_section_planes()` | Scene/Tools/section controls, browser | Requires one or more plane IDs; updates collection and context. |
| Select result/curve/surface/region | `select_section_result(s)()`, `select_curve(s)()`, `select_surface(s)()`, `select_region()` | Scene browser and viewport | Contextual family selection with active/primary item. |
| Clear Selection | `clear_selection()` | Context buttons and empty selection routes | Clears selection and transform session, not model records. |
| Rename Selected | `rename_selected()` plus family name callbacks | Edit/legacy Scene menu, `F2`, name fields | Exactly one renameable persistent node; pushes rename undo and dirties. Parent/group nodes are rejected. |
| Delete Selected | `_delete_selected_if_safe()` / `delete_selected_scene_objects()` | Edit/legacy Scene menu, `Delete`, context controls | Contextual; expands parents/dependencies, confirms mesh separately, pushes deletion undo where supported. |
| Hide Selected | `hide_selected_scene_objects()` | Legacy Scene menu/context | Contextual visibility targets; undoable, dirty for persistent targets. |
| Show Selected | `show_selected_scene_objects()` | Legacy Scene menu/context | Contextual visibility targets; undoable, dirty for persistent targets. |
| Isolate Selected | `hide_unselected_scene_objects()` | Legacy Scene menu, `Shift+H` | Requires selection; hides other scene targets, undoable. |
| Toggle Visibility | `toggle_selected_scene_objects()` | Legacy Scene menu, browser, `H` | Registered representative action `scene.toggle_visibility`. |
| Show All | `show_all_scene_objects()` | Legacy Scene menu, `Alt+H` | Registered representative action `scene.show_all`. |
| Direct family visibility edit | `_on_mesh_visibility_changed()`, `_on_section_plane_visibility_changed()`, `_on_section_result_visibility_changed()`, `_on_curve_visibility_changed()`, `_on_surface_visibility_changed()` | Context checkbuttons | Contextual state edit; legacy synchronization and dirty/undo behavior are family-specific. |

### View and presentation

| User intent / current label | Legacy entry point | Invocation surfaces | Availability / side effects |
|---|---|---|---|
| Frame All | `frame_all()` | View menu, Scene sidebar | Registered representative action `view.frame_all`; known unreliable framing is reserved for Task 77. |
| Frame Selected | `frame_selected()` | View/legacy Scene menu, contexts, `F` | Registered representative action `view.frame_selected`; contextual bounds. |
| Frame selected region | `frame_selected_region()` | Region context | Requires visible active region; uses region vertex bounds. |
| Frame source curves | `frame_source_curves_for_active_surface()` | Surface context/legacy menu | Requires active surface and available source curve geometry. |
| Reset View | `reset_view()` (`reset_camera()` compatibility path) | View menu, Scene sidebar | Resets camera using existing viewport behavior; does not alter model transform. |
| Named camera view | `set_named_view(name)` | View menu and view-control shell | Top, Bottom, Front, Back, Left, Right, Isometric; camera only. |
| Show Grid / Axes / Axis Gizmo / View Controls | `_on_view_option_changed()` | View menu and Scene controls | Presentation preferences/current project display; refreshes viewport/UI. |
| Show ViewCube | `_sync_viewcube_shell_visibility()` via display state | View-control shell/preferences | Presentation-only visibility. |
| Show Normals | `_on_view_option_changed()` | Scene display control/preferences | Requires mesh for visible normal geometry. |
| Mesh display proxy quality | `_on_proxy_quality_changed()` | Scene control | Rebuilds display mesh, preserves full-resolution source. |
| Surface opacity | `_on_surface_opacity_changed()` | Surface context slider | Persistent surface metadata/display edit. |
| Surface wireframe overlay | `_on_surface_wireframe_changed()` | Surface context checkbutton | Persistent surface metadata/display edit. |

### Transforms and origins

| User intent / current label | Legacy entry point | Invocation surfaces | Availability / side effects |
|---|---|---|---|
| Move | `start_move_transform()` | Tools/Transform controls, `G` | Requires eligible selected mesh or single section plane; begins modal transform. |
| Rotate | `start_rotate_transform()` | Tools/Transform controls, `R` | Requires eligible selected mesh or single section plane; begins modal transform. |
| Confirm transform | `_handle_shortcut("Enter")` / `_end_active_transform(commit=True)` | Configured Enter shortcut | Commits changed transform, synchronizes scene, creates undo/dirty state. |
| Cancel transform | `_handle_shortcut("Esc")` / `_end_active_transform(commit=False)` | Configured Esc shortcut | Restores captured start state and clears modal transform. |
| Axis constraint | `_set_transform_axis_constraint()` | `X`, `Y`, `Z`; `N` for section normal | Modal/contextual; toggles constraint without persistent change by itself. |
| Numeric transform edit | `_on_object_transform_changed()` / `_apply_object_transform()` | Transform entries | Mesh location/rotation/scale/origin; validates input and updates display/query revision. |
| Set Origin to Geometry | `set_origin_to_geometry()` | Transform context | Changes origin while preserving geometry placement. |
| Move Origin to World Origin | `move_origin_to_world_origin()` | Transform context | Changes origin/location while preserving geometry placement. |
| Center Geometry on Origin | `center_geometry_on_origin()` | Transform context | Moves geometry relative to the current origin. |
| Reset Object Transform | `reset_object_transform()` | Transform context | Restores identity-style transform state. |

### Sections

| User intent / current label | Legacy entry point | Invocation surfaces | Availability / side effects |
|---|---|---|---|
| Add Section Plane | `add_section_plane()` | Sections context/legacy menu | Requires mesh workflow context; creates a uniquely named active plane and updates browser. |
| Delete Selected Section Plane | `delete_active_section_plane()` | Sections context/legacy menu, generic Delete | Requires one active plane; removes its results and downstream curves/surfaces, then ensures a default plane when needed. |
| Select Model / Section Plane | `select_model()`, `select_section_plane()` | Sections context | Navigation between source mesh and active plane. |
| Set plane axis | `_on_section_axis_changed()` | X/Y/Z combobox | Resets the active plane to axis-aligned origin/normal semantics and clears stale generated geometry for that plane. |
| Set plane offset | `_on_offset_slider_changed()`, `_on_offset_input_changed()`, `_set_section_offset()` | Slider/text entry | Validated contextual edit; updates plane preview and invalidates stale results. |
| Set plane visibility | `_on_section_plane_visibility_changed()` | Plane context | Persistent visibility edit. |
| Rename plane | `_on_section_plane_name_changed()` | Plane name field | Validated persistent rename; undoable. |
| Compute Section | `compute_section()` | Sections context/legacy menu | Requires mesh and active plane; staged extraction/fitting, stores independent result and curves, updates scene, dirties project. |
| Clear active result | `clear_active_section_result()` (`clear_section()` compatibility wrapper) | Sections context/legacy menu | Requires active/stored result; removes its downstream curves/surfaces. |
| Clear all section results | `clear_all_section_results()` | Sections context/legacy menu | Removes every stored result plus downstream curves/surfaces, preserving planes. |
| Result visibility/name | `_on_section_result_visibility_changed()`, `_on_section_result_name_changed()` | Result context | Persistent contextual edits. |

### Stored curves and curve preparation

| User intent / current label | Legacy entry point | Invocation surfaces | Availability / side effects |
|---|---|---|---|
| Join Selected Curves | `join_selected_curves()` | Curves context/legacy menu | Requires compatible open curves within repair tolerance; creates a new repaired curve and preserves originals. |
| Auto-Close Selected Curve | `auto_close_selected_curve()` | Curves context/legacy menu | Requires one open curve with a small enough endpoint gap; creates a new repaired closed curve. |
| Simplify Selected Curve | `simplify_selected_curve()` | Curves context/legacy menu | Requires one curve; creates a reduced derived record and preserves lineage/original. |
| Smooth Selected Curve | `smooth_selected_curve()` | Curves context/legacy menu | Requires one curve; creates a smoothed derived record and preserves lineage/original. |
| Project Selected Curve to Mesh | `project_selected_curve_to_mesh()` | Curves/Manual RE contexts, legacy menu | Requires mesh and one eligible curve; uses shared `MeshQueryService`, creates a projected derived curve with metrics. |
| Rebuild Selected Curve | `rebuild_selected_curve()` | Curves/Manual RE contexts, legacy menu | Requires one curve and valid target/sample controls; creates a rebuilt derived curve. |
| Validate Selected Curve | `validate_selected_curve()` | Curves context | Reports fill readiness without changing geometry. |
| Validate Selected Curves for Loft | `validate_selected_curves_for_loft()` | Curves context | Requires loft selection; reports combined readiness and mismatch warnings. |
| Convert Selected Curve to Smooth | `convert_selected_curve_to_smooth_guide()` | Manual RE context/legacy menu | Requires eligible stored curve; creates an editable smooth-guide derived record. |
| Reduce/Simplify Selected Guide Curve | `reduce_simplify_selected_guide_curve()` | Manual RE context/legacy menu | Requires eligible guide curve; simplifies control data while retaining corner semantics/lineage. |
| Hide Selected Curves | `hide_selected_curves()` | Curves context/legacy menu | Requires selected curves; persistent visibility edit. |
| Hide Unselected Curves | `hide_unselected_curves()` | Curves context/legacy menu | Requires curve selection; isolates selected curve records. |
| Show All Curves | `show_all_curves()` | Curves context/legacy menu | Makes all curves visible; distinct from registered scene-wide Show All. |
| Select Tiny Curves | `select_tiny_curves()` | Curves context/legacy menu | Selects curves matching stored diagnostic thresholds. |
| Hide Tiny Curves | `hide_tiny_curves()` | Curves context/legacy menu | Hides diagnostic tiny fragments. |
| Delete Tiny Curves | `delete_tiny_curves()` | Curves context/legacy menu | Removes tiny curves and dependent surfaces, with existing undo behavior. |
| Delete Selected Curve | `delete_selected_curve()` | Curves context/legacy menu, generic Delete | Removes selected curve records and dependent surfaces/features as currently coordinated. |
| Rename/visibility direct edits | `_on_curve_name_changed()`, `_on_curve_visibility_changed()` | Curve context | Validated persistent edits; rename/visibility history behavior is preserved. |

### Manual-curve workflow

These entry points are intentionally thin Task 74 compatibility wrappers around
`ManualCurveController` plus UI/viewport/undo adapters. Their behavior must not
be reimplemented as parallel window state.

| User intent / current label | Legacy entry point | Current controller/session transition |
|---|---|---|
| Create Manual Curve | `start_manual_curve_mode()` | Begins a new session in `draw_add_points` on the active plane or world XY fallback. |
| Edit Manual Curve | `start_manual_curve_edit_mode()` | Loads one editable curve and enters `edit_select`. |
| Finish / Done | `_finish_manual_curve_action()`, `done_manual_curve_editing()` | New curve validates/builds and enters edit mode; editing completion exits cleanly. `Enter` routes here by context. |
| Apply Edits | `apply_manual_curve_edits()` | Builds an updated stored curve, preserves lineage/metadata, coordinates undo and dependent feature dirty/rebuild state. |
| Cancel workflow | `_cancel_manual_curve_mode()`, `cancel_manual_curve_edit()` | Discards transient work after the existing confirmation rules and exits. |
| Remove Last Point | `_remove_last_manual_curve_point()` | Drawing-mode removal; `Backspace` uses the same contextual behavior. |
| Toggle Closed | `_toggle_manual_curve_closed()` | Opens/closes when point-count invariants permit; `C` uses the same route. |
| Add Point mode | `activate_manual_curve_add_point()` | Explicitly enters `explicit_add_point` while editing. |
| Insert Point mode | `activate_manual_curve_insert_point()` | Explicitly enters `explicit_insert_point` while editing. |
| Delete Selected Point | `delete_selected_manual_curve_point()` | Removes selected control point while enforcing minimum/invariant rules. |
| Set Smooth / Corner / Toggle Point Type | `set_selected_manual_curve_point_smooth()`, `set_selected_manual_curve_point_corner()`, `toggle_selected_manual_curve_point_type()` | Updates explicit point type/source and invalidates display cache. |
| Auto Detect Corners | `auto_detect_manual_curve_corners()` | Detects angle corners while preserving manual overrides. |
| Clear Auto Corners | `clear_auto_detected_manual_curve_corners()` | Clears only automatically detected corners. |
| Smooth Selected Span | `smooth_selected_manual_curve_span()` | Adjusts selected control span through existing controller helper. |
| Straighten Selected Span | `straighten_selected_manual_curve_span()` | Straightens selected control span through existing controller helper. |
| Curve method/sample/smoothness/corner threshold | `_on_manual_curve_type_changed()`, `_on_manual_curve_sample_count_changed()`, `_on_manual_curve_smoothness_changed()`, `_on_manual_curve_corner_threshold_changed()` | Reconfigures authoritative session and invalidates cached display geometry. |
| Snap to Mesh / Keep Curve On Mesh | `_on_manual_curve_snap_to_mesh_changed()`, `_on_manual_curve_keep_on_mesh_changed()` | Updates session options; picks/projection use the per-window accelerated query service. |
| Placement plane | `_on_manual_curve_placement_changed()`, `_configure_manual_curve_placement_plane()` | Chooses active section plane or supported fallback without embedding picker/UI operations in the controller. |
| Toggle Advanced Controls | `toggle_advanced_curve_controls()` | Presentation-only panel disclosure; no modeling change. |

Pointer actions (place, select, begin/move/end drag, insert, and preview) are
resolved by viewport/presentation adapters and routed to the controller. Right,
middle, wheel, navigation-left, and shift-left navigation events remain camera
input and are not application commands.

### Regions

| User intent / current label | Legacy entry point | Invocation surfaces | Availability / side effects |
|---|---|---|---|
| Region Select | `start_region_select_mode()` | Manual RE/Tools controls | Requires mesh; exits conflicting manual/transform workflows and begins pick mode. |
| Pick seed region | `_handle_region_select_pointer_event()` / `_select_region_at_screen_point()` | Viewport left click | Click-only (not drag); grows connected faces with current threshold/cap and sets one active region. |
| Recompute Region | `recompute_region_selection()` | Region context | Requires active region, valid seed, threshold, and max cap. |
| Configure threshold/max | threshold/max callbacks and `configure_region_threshold()`, `configure_region_max_triangle_count()` | Slider/text controls | Validates/clamps controls; recomputation remains an explicit action. |
| Clear Region | `clear_region_selection()` | Region context/context menu | Clears active region selection. |
| Hide Region / Show Region | `hide_region_selection()`, `show_region_selection()` | Region context/context menu | Toggles transient region overlay visibility. |
| Delete Region | `delete_region_selection()` | Region context/context menu/generic Delete | Removes the active region record. |
| Frame Region | `frame_selected_region()` | Region selection/browser route | Requires active visible region geometry. |
| Done / Cancel Region Select | `_exit_region_select_mode()` | Region context/context menu, `Esc` | Ends tool; cancellation status differs, model data otherwise preserved per current behavior. |
| Rename Region | `_on_region_name_changed()` | Region name field | Updates active region name/browser label. |
| Extract Region Boundary | `extract_region_boundary()` | Region/Curves contexts, legacy menu | Requires mesh and active region; creates one or more editable boundary curves with source lineage. |
| Select Boundary Curves | `select_boundary_curves_for_active_region()` | Region context | Selects stored curves linked to the active region. |
| Convert Boundary to Hybrid Guide Curve | `convert_boundary_to_hybrid_guide_curve()` | Region/Curves contexts, legacy menu | Creates editable derived guide curve while preserving the boundary record. |
| Create BREP Face From Selected Region | `create_brep_face_from_selected_region()` | Region/Surfaces contexts, legacy menu | Fits/project boundary to a plane, builds a planar CAD face when valid, and stores lineage/diagnostics. |
| Toggle Region Details | `toggle_region_details()` | Manual RE region panel | Presentation-only panel disclosure. |

### Preview surfaces, BREP, and editable features

| User intent / current label | Legacy entry point | Invocation surfaces | Availability / side effects |
|---|---|---|---|
| Create Surface From Curves | `create_surface_from_curves()` | Compatibility/test entry point | Dispatches by selected curve count to existing fill/loft preview behavior; not separately exposed in the main menu. |
| Fill Closed Curve | `fill_closed_curve()` | Curves and Surfaces legacy menus, Surfaces context | Requires exactly one closed/readiness-valid curve; creates preview record and stores warnings. |
| Loft Between Two Curves | `loft_between_two_curves()` | Curves and Surfaces legacy menus, Surfaces context | Requires exactly two ready curves; creates two-curve preview and stores mismatch diagnostics. |
| Create Mesh-Conforming Loft Preview | `create_mesh_conforming_loft_preview()` | Surfaces context/legacy menu | Requires two curves and source mesh; projects through shared `MeshQueryService`; produces preview only, not BREP. |
| Create Boundary Patch | `create_boundary_patch_from_curve()` | Surfaces context/legacy menu | Requires one closed curve; creates triangulated preview with planarity diagnostics. |
| Create Four-Curve Patch | `create_four_curve_patch()` | Surfaces context/legacy menu | Requires exactly four suitable curves; creates preview plus editable four-boundary feature linkage. |
| Create Curve Network Patch | `create_curve_network_patch()` | Surfaces context/legacy menu | Requires at least three suitable curves; creates strip preview and spacing diagnostics. |
| Create BREP Face From Closed Curve | `create_brep_face_from_closed_curve()` | Surfaces context/legacy menu | Requires one closed valid curve and available public CAD backend; stores BREP record/runtime object. |
| Create BREP Loft From Two Curves | `create_brep_loft_from_two_curves()` | Surfaces context/legacy menu | Requires two valid compatible curves and CAD backend; stores BREP record/runtime object. |
| Create Editable BREP Loft From Curves | `create_editable_brep_loft_from_curves()` | Surfaces context/legacy menu | Builds/stores editable loft feature, preview/BREP links, options, status, and source order. |
| Rebuild Selected BREP Surface | `rebuild_selected_brep_surface()` | BREP surface context/legacy menu | Rebuilds planar/loft/region BREP from stored lineage and updates runtime object/diagnostics. |
| Export Selected BREP Surface to STEP | `export_selected_brep_surface_to_step()` | BREP surface context/legacy menu | Requires one selected BREP and runtime CAD object; file picker remains UI code. |
| Delete Selected Surface | `delete_selected_surface()` | Surface/BREP/loft contexts and legacy menu | Removes selected preview/BREP records and linked editable feature/runtime cache as applicable; undoable where currently covered. |
| Toggle Surface Visibility | `toggle_active_surface_visibility()` / `_on_surface_visibility_changed()` | Legacy menu and context checkbutton | Requires active preview/BREP surface; persistent and undoable through current adapters. |
| Rename Surface | `_on_surface_name_changed()` | Surface name field | Persistent rename, current undo/browser synchronization. |
| Select Source Curves | `select_source_curves_for_active_surface()` | Surface context/legacy menu | Selects available linked source curves and reports missing IDs. |
| Isolate Source Curves | `isolate_source_curves_for_active_surface()` | Surface context/legacy menu | Hides other curves while showing linked sources. |
| Show Source Curves | `show_source_curves_for_active_surface()` | Surface context/legacy menu | Shows all available linked sources. |
| Frame Source Curves | `frame_source_curves_for_active_surface()` | Surface context/legacy menu | Frames combined available source geometry. |
| Rebuild Loft | `rebuild_selected_loft_feature()` | Editable loft context/legacy menu | Rebuilds from persisted options/source order and clears/updates dirty/build diagnostics. |
| Edit First Source Curve | `edit_first_source_curve_for_active_loft()` | Editable loft context | Selects/enters manual edit for the first eligible source curve. |
| Reverse Source Curve Direction | `reverse_selected_loft_source_curve_direction()` | Editable loft context | Reverses selected source geometry and rebuilds/marks dependent state through existing coordination. |
| Move Source Curve Up / Down | `move_selected_loft_source_curve_up()`, `move_selected_loft_source_curve_down()` | Editable loft context | Reorders selected source ID within locked feature order and triggers rebuild state. |
| Duplicate Loft Feature | `duplicate_selected_loft_feature()` | Editable loft context | Copies options/links into a new unique feature and builds through current workflow. |
| Delete Loft Feature | `delete_selected_loft_feature()` | Editable loft context | Removes feature and its linked generated records as currently coordinated. |
| Loft option/name edits | `_on_loft_feature_options_changed()` and name-entry callback | Editable loft context | Persistent option update; may rebuild or mark dirty according to `rebuild_on_source_edit`. |
| Rebuild Four-Boundary Patch Feature | `rebuild_selected_four_boundary_patch_feature()` | Legacy Surfaces menu | Requires intact source curves; refreshes generated preview/BREP linkage and build status. |

### History

| User intent | Entry point | Baseline behavior |
|---|---|---|
| Undo | `undo()` | Registered `edit.undo`; runs one named callback command and moves it to redo. |
| Redo | `redo()` | Registered `edit.redo`; reruns one named callback command and moves it to undo. |
| Push history | `_push_undo_command()` | Adds command, clears redo, refreshes menu enablement. Commands are not serialized. |
| Clear history | `_clear_undo_stack()` | Used on new project/model lifecycle boundaries. |

Current undo integration is behaviorally covered for empty history, curve/name
edits, visibility, dependent deletion/restoration, manual-curve creation/editing,
and preview/BREP creation. A migration must preserve both record state and the
post-history scene/browser/workflow synchronization; merely restoring a domain
object is insufficient.

## Enablement and visibility baseline

For the six registered actions, `ActionContext` is the sole contract:

- Frame All is always enabled.
- Frame Selected and Toggle Visibility require a scene selection.
- Show All requires at least one scene visibility object.
- Undo/Redo require corresponding history availability.
- All six are visible and unchecked.

Legacy menu and widget enablement remains distributed across
`_update_menu_availability()`, `_set_menu_labels_state()`,
`_set_selection_buttons_enabled()`, workflow synchronization, and guard clauses
inside handlers. Later migrations must encode the actual preconditions; they
must not simply register every legacy method as always-enabled.

Common precondition dimensions observed in the audit are: mesh loaded; exact or
minimum selection count; homogeneous selection family; active plane/result/
curve/surface/region; curve closure/type/readiness; source lineage available;
CAD backend/runtime object available; current tool/submode; valid numeric input;
history availability; and whether a long-running load/compute is active.

## Duplicate labels and multiple invocation surfaces

Duplicate text is not a duplicate action by itself. The metrics report should
flag it for human review; this baseline explains the intentional cases.

| Label/pattern | Current locations | Interpretation |
|---|---|---|
| Frame Selected | View menu, legacy Scene menu, object/curve/source/region contexts, shortcut | Usually the same general intent, but region/source helpers have specialized target resolution. The registered general action is `view.frame_selected`. |
| Rename Selected | Edit menu and legacy Scene menu | Same legacy handler. |
| Delete Selected | Edit menu and legacy Scene menu; family-specific Delete buttons | General handler expands dependencies; family buttons may use narrower wrappers. |
| Fill Closed Curve | Curves and Surfaces legacy menus plus Surfaces context | Same modeling handler exposed from two workflow locations. |
| Loft Between Two Curves | Curves and Surfaces legacy menus plus Surfaces context | Same modeling handler exposed from two workflow locations. |
| Create BREP Face From Closed Curve | Surfaces legacy menu and multiple surface contexts | Same handler; contexts differ only in placement. |
| Delete Selected Surface | Preview, BREP, editable loft contexts and legacy Surfaces menu | Same broad handler resolves the active record family. |
| Select Section Plane / Select Model | Scene, Sections, and Tools surfaces | Same selection/navigation intent repeated for workflow convenience. |
| Show All versus Show All Curves | Scene-wide registry action and curve-only legacy action | Different scopes and therefore must remain different action IDs when the curve action is migrated. |
| Toggle Visibility versus Toggle Surface Visibility | Scene selection registry action and active-surface helper | Overlapping presentation labels but different target resolution; later migration should converge only if contracts become identical. |

## Non-command APIs and out-of-scope behavior

Pure geometry/state functions such as section intersection, curve sampling,
closest-point query, preview mesh generation, CAD building, and collection
mutation are not user actions. They are invoked by commands/controllers and must
not acquire shortcuts, dialogs, Tk objects, or VTK actors.

Task 75 intentionally does not register every legacy entry point, replace Tk
menus, introduce a generic callback service locator, change shortcuts, or fix
camera behavior. `Recent Files` and the Hotkeys help dialog remain placeholders.
No command IDs are reserved here for unimplemented modeling features.

## Requirements for adding the next action

When a later numbered task migrates a legacy action, it must:

1. choose one stable action ID and one stable command ID, document their scope,
   and reject duplicate registration;
2. encode real enablement/visibility/check-state conditions without reading Tk
   variables in the application package;
3. use typed payload and explicit dependencies instead of capturing the whole
   window or consulting global services;
4. return status, warnings/errors, changed/dirty state, viewport/UI requests,
   and undo data explicitly;
5. keep file pickers, confirmations, dialogs, widget updates, and actor mutation
   in presentation/infrastructure adapters;
6. preserve legacy wrappers and current shortcut/menu behavior until all callers
   are migrated and tested; and
7. add focused contract tests plus the existing workflow regression tests before
   deleting any old coordination path.

# V3 command and action inventory

`application.actions.CORE_ACTIONS` is the authoritative inventory. Definitions
have stable action and command IDs, label/description/category/shortcut data,
typed enablement/visibility/checked conditions, and read-only metadata.

The registry covers these namespaces:

- `edit`: undo/redo;
- `scene`: family selection, clear, rename, delete, show/hide/toggle/isolate,
  source-curve operations;
- `view`: display toggles, proxy quality, named views, reset and all framing;
- `transform`: move/rotate, axis constraints, numeric/origin/reset, apply/cancel;
- `section`: plane lifecycle, axis/offset, compute/result lifecycle;
- `curve`: join/close/simplify/smooth/project/rebuild/validate/convert and tiny
  fragment operations;
- `manual_curve`: create/edit/finish/apply/cancel, point/submode/type/corner and
  snap/sampling options;
- `region`: start/finish/grow configuration, recompute, visibility, boundary and
  guide conversion;
- `surface`: preview, conforming, network/four-boundary, editable loft, BREP,
  display/source/rebuild/duplicate/delete operations;
- `analysis`: refresh and mesh deviation.

File/project/preferences/export/about/recent actions are presentation adapters
because they own dialogs and window lifecycle. Camera-only actions become
`CameraRequest` values in the Qt presentation. Every core command ID is
registered in `CommandDispatcher` and routed by `WorkflowService`; unknown or
invalid state returns a structured failure rather than a successful placeholder.

`test_application_core.py` validates action/command contracts and
`test_v3_workflow_service.py` iterates the complete registry to prevent missing
handlers or workflow adapters.

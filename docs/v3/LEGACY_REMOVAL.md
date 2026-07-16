# Task 81 legacy-shell removal record

The removal gate is satisfied.

- Every retained action ID is registered with `WorkflowService` and
  `CommandDispatcher`; `test_v3_workflow_service.py` checks the full registry.
- Behavior-focused Qt/controller/project/viewport tests replace the removed Tk
  widget-internal and compatibility-facade tests.
- `src/app`, Tk menus/preferences/scene browser/host code, and
  `src/viewer/embedded_viewport.py` are absent.
- Production has no `app.*` or `tkinter` imports.
- The architecture UI-import allowlist is empty, and practical package/module
  cycle checks pass.
- `src/main.py` launches only `presentation.qt.main_window.run_v3_app`.

The old shell is not a fallback or supported compatibility mode. Project-file
compatibility is preserved at the repository and restore boundaries instead.

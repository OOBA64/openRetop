# Task 81 legacy-shell removal gate

The supported entry point is V3 (`src/main.py` imports only
`presentation.qt.main_window`). V3 presentation has no Tk imports and its
viewport consumes the shared `SceneSnapshot`/`SceneSynchronizer` path.

The physical deletion gate is intentionally explicit:

1. Every retained row in `V3_PARITY_MATRIX.md` must have a V3 behavior test.
2. The legacy `test_main_window_ui.py` and embedded-viewport tests must be
   replaced by equivalent V3 workflow tests, not silently skipped.
3. Only after those tests pass may `src/app/main_window.py`, Tk panels/menus/
   dialogs, and `src/viewer/embedded_viewport.py` be removed and the six
   existing presentation allowlist entries deleted.

Current evidence satisfies the supported-entry and boundary portions. The
physical deletion gate is not yet satisfied: the current complete suite still
has 31 legacy compatibility failures and one direct-private-helper error, so
removing the shell now would destroy test coverage rather than complete the
migration.

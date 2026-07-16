# V3 dependency audit

Final Tasks 77-82 audit (2026-07-15):

- 105 production Python files / 32,260 lines.
- 52 methods on the supported `OpenRetopV3Window`; 0 legacy-window methods.
- 0 guarded Tk/Qt/VTK-rendering imports below the presentation boundary.
- 0 allowlisted UI imports.
- 0 practical package cycles and 0 practical module cycles.
- 0 detectable duplicate action/menu labels.
- `packages/workbench_ui` imports neither `app` nor `application`.
- Production imports neither `app.*` nor `tkinter`.
- Actor creation/mutation is isolated under viewport infrastructure; application
  controllers consume toolkit-neutral scene/pick/result values.

The largest production modules are controller/domain implementations rather
than one shell: manual-curve controller (1,672 lines), BREP controller (1,497),
manual-curve algorithms (1,493), surface previews (1,372), and the Qt shell
(1,405). This is a deliberate separation of cohesive workflows, not a hidden
compatibility facade.

Run `python scripts/report_architecture_metrics.py --fail-on-new` for the live
report. The checked baseline in `tests/architecture_dependency_baseline.json`
contains no debt entries.

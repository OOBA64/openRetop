# Usability runs: the real window, driven like a person

These scripts open the real openRetop window and use it the way a user does: workspace tabs,
toolbar and panel buttons are clicked as widgets, the 3D view gets real mouse press / move /
release and wheel events, keys are real key events, the units question and confirmations are
answered by clicking their buttons. (Windows' own file dialogs cannot be scripted; the scripts
answer them with a path and log what the dialog asked.)

They print what the user would see after every step (status line, tool hint, panel text) and
save screenshots of the window and of the 3D view. They are audits, not unit tests: read the
log and the pictures.

```bash
set QT_QPA_PLATFORM=
set PYTHONPATH=src;packages/workbench_ui
python scripts/usability/s1_basics.py out/s1
python scripts/usability/s5_real_scans.py out/s5 .
```

| Script | What a user does |
|---|---|
| `s1_basics.py` | first launch, Open Scan + units, orbit / pan / zoom / view keys, pick, Move with a typed value, section, region, measure, save and reopen |
| `s2_surface_bracket.py` | fit every face of the bracket by clicking it, Trim into a solid, Compare, Export STEP |
| `s3_solid_housing.py` | Section Sketch + Extrude from the scan, History edit, a 3D Sketch drawn and dimensioned with mouse and panel, region extrude |
| `s4_curves_menus.py` | a closed Surface Sketch loop, Face From Curves, Loft, and what the menus offer |
| `s5_real_scans.py` | the oil pan and the TurboBumper from `test_assets/` |
| `s6_general.py` | command palette searches, Preferences, Delete, undo / redo chain, Help |
| `trim_overhang.py` | fit a plane, cut its overhang with a Cut Line, drop it, Apply |
| `resize_arrows.py` | drag a side arrow, a corner arrow, click an arrow and type a distance |

`human.py` waits with a real Qt event loop: `QTest.qWait` starved the worker thread, which made
a 1-second scan load look like a hang.

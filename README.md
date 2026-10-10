# openRetop

openRetop is a scan-to-CAD desktop application. It turns STL/OBJ/PLY scans
into surfaces and solids you can export to STEP or IGES, in the scan's own
units.

```
scan -> curves on the scan / fitted surfaces -> trimmed, sewn surfaces -> solid -> STEP
scan -> section sketch (lines and arcs) -> extrude -> solid -> STEP
```

## Install and run

Python 3.11 or newer on Windows, Linux or macOS.

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# Linux / macOS:  source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

openretop            # or: python -m openretop
```

CadQuery / OpenCASCADE (the CAD kernel) is pinned in `pyproject.toml`; it is a
large download. It runs in a separate worker process, so a kernel crash cannot
take the window down.

## Working with a model

**Open Scan** (`Ctrl+O`) and choose its length unit (mm, cm, m or in). The unit
is stored in the project, drives default tolerances and is declared in exported
files. *Edit > Set Model Units...* relabels it. The tools are grouped in three
workspaces:

- **Scan**: align the scan (G / R, typed values, axis locks), cut sections,
  select regions, measure.
- **Surface**: **Surface Sketch** curves that run along the scan and can follow its
  body lines (sections and region boundaries become sketch curves too);
  **Fit Surface** to a brushed area; **Loft**, **Fill**, **Extend**, **Trim**
  (sews into a solid when closed); **Compare** colours the scan by its distance
  to the model.
- **Solid**: **3D Sketch** draws on a plane through the scan (its cut shown
  to draw over): lines, rectangles, circles and arcs held by constraints and
  dimensions, Fusion-style (blue until fully defined). **Section Sketch** fits
  lines and arcs to a cut through the scan, editable by hand. **Extrude** a
  sketch (or regions of it, picked by clicking) with its depth measured on the
  scan. The **History** in the scene tree records sketches and extrudes:
  change a dimension or a depth and the part rebuilds.

**Export Model** writes the selected (or all visible) surfaces and bodies.
Long operations run off the UI thread; the window stays responsive.

Projects are `.openretop` JSON files, written atomically, with the mesh path
stored relative to the project file. Older files are upgraded on open (version 1
projects have no recorded unit, so millimetres are assumed and you are warned;
curves from the retired curve tools open as Surface Sketch curves).

The PySide6 workbench is the only supported shell. See the
[user guide](docs/v3/V3_USER_GUIDE.md), [architecture](docs/v3/ARCHITECTURE.md)
and [developer setup](docs/v3/SETUP.md). The reusable UI framework lives in
`packages/workbench_ui/` and is installed together with the app.

## Command-line mesh diagnostics

```bash
python -m openretop.mesh.import_mesh path/to/model.stl
python -m openretop.mesh.import_mesh path/to/model.stl --section-axis Z --section-offset 0
```

## Development

Set `QT_QPA_PLATFORM=offscreen` for headless runs (`export QT_QPA_PLATFORM=offscreen`
on Linux/macOS, `$env:QT_QPA_PLATFORM = "offscreen"` in PowerShell).

```bash
ruff check .
mypy
python scripts/report_architecture_metrics.py --fail-on-new
python -m unittest discover -s tests -p "test_*.py"
python benchmarks/benchmark_v3_workflows.py --iterations 25 --curves 250
```

Large test meshes belong in `test_assets/` (git-ignored). Do not commit scan
files, secrets or credentials.

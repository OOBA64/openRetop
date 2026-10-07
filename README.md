# openRetop

openRetop is a guided scan-to-CAD desktop application. It turns STL/OBJ/PLY
triangle meshes into sections, editable curves, regions, lofted/patched
surfaces and optional CAD-kernel B-rep/STEP output.

```
mesh scan -> sections -> B-spline curves -> regions -> lofted NURBS surfaces -> STEP
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

CadQuery (the CAD kernel) is pinned in `pyproject.toml`; it is a large
download. Without a working install the app still imports meshes, cuts
sections and edits curves, but B-rep surfaces and STEP export are unavailable.

## Working with a model

1. **Open Model** (`Ctrl+O`) and choose the mesh's length unit (mm, cm, m or
   in). The unit is stored in the project, drives default tolerances, and is
   declared in exported STEP files. *Edit > Set Model Units...* relabels it.
2. Add section planes and **Compute Section**. Each closed or open section
   becomes a curve fitted with a tolerance-driven B-spline (default 0.05 % of
   the model size); sharp corners stay sharp.
3. Create a **BREP Loft** between curves (or a face from a closed curve) and
   **Export STEP**.

Opening a model, computing sections and building B-reps run on a worker thread;
the window stays responsive and rejects other edits until the task finishes.

Projects are `.openretop` JSON files, written atomically, with the mesh path
stored relative to the project file. Older files are upgraded on open (version 1
projects have no recorded unit, so millimetres are assumed and you are warned).

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

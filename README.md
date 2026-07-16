# openRetop V3

openRetop is a guided scan-to-CAD desktop application for turning STL/OBJ/PLY
triangle meshes into sections, editable curves, preview surfaces, and optional
CAD-kernel BREP/STEP output.

## Install and run

Use Python 3.11 on Windows or Linux:

```powershell
python -m venv .venv-v3
.\.venv-v3\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/main.py
```

The PySide6 V3 workbench is the only supported desktop shell. The Scene dock
controls selection and visibility, the Properties dock edits the active object,
and the command palette exposes the same action registry as menus and
shortcuts. See the [V3 user guide](docs/v3/V3_USER_GUIDE.md) and
[developer setup](docs/v3/SETUP.md).

The reusable standalone workbench framework lives in
`packages/workbench_ui/`:

```powershell
$env:PYTHONPATH = "packages/workbench_ui"
python -m workbench_ui.demo
```

## Command-line mesh diagnostics

```powershell
python src/mesh/import_mesh.py path\to\model.stl --no-viewer
python src/mesh/import_mesh.py path\to\model.stl --no-viewer --section-axis Z --section-offset 0
```

## Verification and benchmarks

```powershell
$env:PYTHONPATH = "src;packages/workbench_ui"
$env:QT_QPA_PLATFORM = "offscreen"
python -m compileall -q src packages/workbench_ui/workbench_ui
python scripts/report_architecture_metrics.py --fail-on-new
python -m unittest discover -s tests -p "test_*.py"
python benchmarks/benchmark_mesh_queries.py --quick
python benchmarks/benchmark_scene_sync.py --iterations 25
python benchmarks/benchmark_v3_workflows.py --iterations 25 --curves 250
```

CI runs the full suite under Linux/Xvfb and focused V3 coverage on Windows.
Do not commit secrets, credentials, or large scan data files.

# V3 developer and release setup

Use Python 3.11 and install the supported environment:

```powershell
python -m venv .venv-v3
.\.venv-v3\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the supported Qt shell and independent framework demo:

```powershell
python src/main.py
$env:PYTHONPATH = "packages/workbench_ui"
python -m workbench_ui.demo
```

Run release verification from the repository root:

```powershell
$env:PYTHONPATH = "src;packages/workbench_ui"
$env:QT_QPA_PLATFORM = "offscreen"
python -m compileall -q src packages/workbench_ui/workbench_ui
python scripts/report_architecture_metrics.py --fail-on-new
python -m unittest discover -s tests -p "test_*.py"
python benchmarks/benchmark_scene_sync.py --iterations 25
python benchmarks/benchmark_v3_workflows.py --iterations 25 --curves 250
python -m pip wheel --no-deps --no-build-isolation packages/workbench_ui
```

Linux CI installs Xvfb and Mesa libraries. Windows automated tests use Qt
offscreen. The final visual review requires a valid OpenGL-capable Windows
desktop and should cover camera navigation, rendered styling, manual tools, and
BREP/STEP with the optional CAD backend installed.

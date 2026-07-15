# V3 developer and release setup

Use Python 3.11 and install the supported environment:

```powershell
python -m venv .venv-v3
.\.venv-v3\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run the supported Qt shell:

```powershell
python src/main.py
```

Run the independent framework demo:

```powershell
$env:PYTHONPATH = "packages/workbench_ui"
python -m workbench_ui.demo
```

Verification commands:

```powershell
$env:PYTHONPATH = "src;packages/workbench_ui"
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest tests.test_task77_viewport tests.test_task78_boundaries tests.test_task79_workbench_ui tests.test_task80_v3_ui tests.test_task81_legacy_boundary
python -m compileall -q src packages/workbench_ui/workbench_ui
python scripts/report_architecture_metrics.py --fail-on-new
python benchmarks/benchmark_scene_sync.py --iterations 25
```

On Linux CI, install Xvfb and Mesa libraries before running the complete Qt/VTK
suite. On Windows, VTK smoke tests require a valid OpenGL-capable desktop; Qt
offscreen is suitable for non-rendering framework tests.

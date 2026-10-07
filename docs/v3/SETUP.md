# V3 developer and release setup

Use Python 3.11 or newer and install the app in editable mode with the dev tools
(Windows: `.venv\Scripts\activate`; Linux/macOS: `source .venv/bin/activate`):

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the supported Qt shell and the independent framework demo:

```bash
openretop              # same as: python -m openretop
python -m workbench_ui.demo
```

Run release verification from the repository root (set `QT_QPA_PLATFORM=offscreen`
first: `export QT_QPA_PLATFORM=offscreen` or `$env:QT_QPA_PLATFORM = "offscreen"`):

```bash
ruff check .
mypy
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

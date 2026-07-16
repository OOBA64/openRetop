#!/usr/bin/env python3
"""Report the openRetop V3 architecture baseline using only the standard library."""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = REPOSITORY_ROOT / "tests" / "architecture_dependency_baseline.json"

DOMAIN_AND_APPLICATION_PACKAGES = {
    "analysis",
    "app",  # Legacy mixed package; known presentation imports are baselined.
    "application",
    "curves",
    "geometry",
    "mesh",
    "regions",
    "sections",
    "surfaces",
}
PROTECTED_INFRASTRUCTURE_PACKAGES = {"project", "settings", "cad_kernel"}
PROTECTED_MESH_QUERY_MODULES = {
    "mesh/query_service.py",
    "mesh/spatial_index.py",
}
UI_MODULE_PREFIXES = (
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "wx",
    "kivy",
    "pyvista",
    "vtk",
    "vtkmodules.all",
)
VTK_PRESENTATION_PREFIXES = (
    "vtkmodules.vtkGUISupport",
    "vtkmodules.vtkInteraction",
    "vtkmodules.vtkRendering",
    "vtkmodules.vtkViews",
)
MENU_METHODS = {"add_command", "add_checkbutton", "add_radiobutton"}


@dataclass(frozen=True)
class ModuleMetric:
    path: str
    lines: int
    classes: int
    functions: int
    methods: int


@dataclass(frozen=True)
class DependencyViolation:
    rule: str
    path: str
    imported_module: str
    line: int

    @property
    def baseline_key(self) -> tuple[str, str]:
        return (self.path, self.imported_module)


@dataclass(frozen=True)
class DuplicateLabel:
    label: str
    count: int
    locations: tuple[str, ...]


def python_files(root: Path, relative_root: str) -> list[Path]:
    directory = root / relative_root
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _read_tree(path: Path) -> tuple[str, ast.Module]:
    text = path.read_text(encoding="utf-8")
    return text, ast.parse(text, filename=str(path))


def collect_module_metrics(
    root: Path = REPOSITORY_ROOT,
    roots: Sequence[str] = ("src", "tests"),
) -> list[ModuleMetric]:
    metrics: list[ModuleMetric] = []
    for relative_root in roots:
        for path in python_files(root, relative_root):
            text, tree = _read_tree(path)
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            methods = sum(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                for class_node in classes
                for item in class_node.body
            )
            metrics.append(
                ModuleMetric(
                    path=path.relative_to(root).as_posix(),
                    lines=len(text.splitlines()),
                    classes=len(classes),
                    functions=len(functions),
                    methods=methods,
                )
            )
    return metrics


def main_window_method_count(root: Path = REPOSITORY_ROOT) -> int:
    path = root / "src" / "presentation" / "qt" / "main_window.py"
    _text, tree = _read_tree(path)
    window = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "OpenRetopV3Window"
        ),
        None,
    )
    if window is None:
        return 0
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in window.body
    )


def legacy_main_window_method_count(root: Path = REPOSITORY_ROOT) -> int:
    path = root / "src" / "app" / "main_window.py"
    if not path.exists():
        return 0
    _text, tree = _read_tree(path)
    window = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "OpenRetopWindow"
        ),
        None,
    )
    return 0 if window is None else sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in window.body
    )


def _module_name(path: Path, src_root: Path) -> str:
    relative = path.relative_to(src_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_modules(tree: ast.AST) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, node.lineno


def _resolved_graph_imports(
    tree: ast.AST,
    *,
    source_module: str,
    source_is_package: bool,
    known_modules: set[str],
) -> Iterator[str]:
    """Resolve practical absolute and relative imports to known source modules."""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
            continue
        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level:
            package_parts = source_module.split(".")
            if not source_is_package:
                package_parts = package_parts[:-1]
            parents_to_remove = node.level - 1
            if parents_to_remove > len(package_parts):
                continue
            if parents_to_remove:
                package_parts = package_parts[:-parents_to_remove]
            if node.module:
                package_parts.extend(node.module.split("."))
            base_module = ".".join(package_parts)
        else:
            base_module = node.module or ""

        known_candidates = [
            f"{base_module}.{alias.name}" if base_module else alias.name
            for alias in node.names
            if alias.name != "*"
        ]
        known_candidates = [
            candidate for candidate in known_candidates if candidate in known_modules
        ]
        if known_candidates:
            yield from known_candidates
        elif base_module:
            yield base_module


def collect_import_graph(
    root: Path = REPOSITORY_ROOT,
) -> tuple[dict[str, set[str]], Counter[tuple[str, str]]]:
    src_root = root / "src"
    paths = python_files(root, "src")
    module_by_path = {path: _module_name(path, src_root) for path in paths}
    known_modules = {name for name in module_by_path.values() if name}
    known_packages = {
        name.split(".", 1)[0]
        for name in known_modules
    }
    module_graph: dict[str, set[str]] = {
        name: set() for name in known_modules
    }
    package_edges: Counter[tuple[str, str]] = Counter()

    for path, source_module in module_by_path.items():
        if not source_module:
            continue
        _text, tree = _read_tree(path)
        source_package = source_module.split(".", 1)[0]
        for imported_module in _resolved_graph_imports(
            tree,
            source_module=source_module,
            source_is_package=path.name == "__init__.py",
            known_modules=known_modules,
        ):
            target_package = imported_module.split(".", 1)[0]
            if target_package not in known_packages:
                continue
            package_edges[(source_package, target_package)] += 1
            if imported_module in known_modules:
                module_graph[source_module].add(imported_module)
            elif target_package in known_modules:
                module_graph[source_module].add(target_package)
    return module_graph, package_edges


def _strongly_connected_components(
    graph: Mapping[str, set[str]],
) -> list[tuple[str, ...]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in graph:
                continue
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == node:
                break
        if len(component) > 1:
            components.append(tuple(sorted(component)))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(components)


def practical_cycles(
    root: Path = REPOSITORY_ROOT,
) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
    module_graph, package_edges = collect_import_graph(root)
    package_graph: dict[str, set[str]] = defaultdict(set)
    for source, target in package_edges:
        package_graph[source].add(target)
        package_graph.setdefault(target, set())
    return (
        _strongly_connected_components(package_graph),
        _strongly_connected_components(module_graph),
    )


def _matches_module_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _is_ui_import(module: str) -> bool:
    if any(_matches_module_prefix(module, prefix) for prefix in UI_MODULE_PREFIXES):
        return True
    return any(module.startswith(prefix) for prefix in VTK_PRESENTATION_PREFIXES)


def dependency_violations(
    root: Path = REPOSITORY_ROOT,
) -> list[DependencyViolation]:
    src_root = root / "src"
    violations: list[DependencyViolation] = []
    for path in python_files(root, "src"):
        relative = path.relative_to(src_root)
        relative_name = relative.as_posix()
        package = relative.parts[0]
        protected = (
            package in PROTECTED_INFRASTRUCTURE_PACKAGES
            or relative_name in PROTECTED_MESH_QUERY_MODULES
        )
        controlled = package in DOMAIN_AND_APPLICATION_PACKAGES
        if not protected and not controlled:
            continue
        _text, tree = _read_tree(path)
        for imported_module, line in _imported_modules(tree):
            if not _is_ui_import(imported_module):
                continue
            rule = (
                "ui_import_in_protected_infrastructure"
                if protected
                else "ui_import_in_domain_or_application"
            )
            violations.append(
                DependencyViolation(
                    rule=rule,
                    path=relative_name,
                    imported_module=imported_module,
                    line=line,
                )
            )
    return sorted(
        violations,
        key=lambda item: (item.path, item.imported_module, item.line),
    )


def duplicate_action_labels(
    root: Path = REPOSITORY_ROOT,
) -> list[DuplicateLabel]:
    locations: dict[str, list[str]] = defaultdict(list)
    for path in python_files(root, "src"):
        _text, tree = _read_tree(path)
        relative = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            method_name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else ""
            )
            if method_name not in MENU_METHODS | {"ActionDefinition"}:
                continue
            label_node = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "label"),
                None,
            )
            if isinstance(label_node, ast.Constant) and isinstance(label_node.value, str):
                label = label_node.value.strip()
                if label:
                    locations[label].append(f"{relative}:{node.lineno}")
    return sorted(
        (
            DuplicateLabel(label, len(items), tuple(items))
            for label, items in locations.items()
            if len(items) > 1
        ),
        key=lambda item: (-item.count, item.label.casefold()),
    )


def load_dependency_baseline(
    path: Path = DEFAULT_BASELINE,
) -> dict[str, object]:
    if not path.exists():
        return {"ui_imports": [], "package_cycles": [], "module_cycles": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Architecture baseline must be a JSON object.")
    return value


def baseline_ui_counter(baseline: Mapping[str, object]) -> Counter[tuple[str, str]]:
    counter: Counter[tuple[str, str]] = Counter()
    raw_items = baseline.get("ui_imports", [])
    if not isinstance(raw_items, list):
        raise ValueError("Architecture baseline ui_imports must be a list.")
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("Each ui_imports baseline entry must be an object.")
        path = str(item.get("path", ""))
        module = str(item.get("module", ""))
        count_value = item.get("count", 1)
        if not path or not module or not isinstance(count_value, int) or count_value < 1:
            raise ValueError("Invalid ui_imports baseline entry.")
        counter[(path, module)] += count_value
    return counter


def _cycle_set(baseline: Mapping[str, object], key: str) -> set[tuple[str, ...]]:
    raw_cycles = baseline.get(key, [])
    if not isinstance(raw_cycles, list):
        raise ValueError(f"Architecture baseline {key} must be a list.")
    cycles: set[tuple[str, ...]] = set()
    for raw_cycle in raw_cycles:
        if not isinstance(raw_cycle, list) or not all(
            isinstance(item, str) for item in raw_cycle
        ):
            raise ValueError(f"Invalid {key} baseline entry.")
        cycles.add(tuple(sorted(raw_cycle)))
    return cycles


def unexpected_architecture_findings(
    root: Path = REPOSITORY_ROOT,
    baseline_path: Path = DEFAULT_BASELINE,
) -> dict[str, object]:
    baseline = load_dependency_baseline(baseline_path)
    actual_violations = dependency_violations(root)
    actual_counter = Counter(item.baseline_key for item in actual_violations)
    unexpected_ui = actual_counter - baseline_ui_counter(baseline)
    package_cycles, module_cycles = practical_cycles(root)
    unexpected_package_cycles = set(package_cycles) - _cycle_set(
        baseline, "package_cycles"
    )
    unexpected_module_cycles = set(module_cycles) - _cycle_set(
        baseline, "module_cycles"
    )
    return {
        "ui_imports": unexpected_ui,
        "package_cycles": unexpected_package_cycles,
        "module_cycles": unexpected_module_cycles,
    }


def build_report(
    root: Path = REPOSITORY_ROOT,
    baseline_path: Path = DEFAULT_BASELINE,
    largest_limit: int = 15,
) -> dict[str, object]:
    metrics = collect_module_metrics(root)
    src_metrics = [item for item in metrics if item.path.startswith("src/")]
    test_metrics = [item for item in metrics if item.path.startswith("tests/")]
    module_graph, package_edges = collect_import_graph(root)
    del module_graph
    package_cycles, module_cycles = practical_cycles(root)
    violations = dependency_violations(root)
    baseline = load_dependency_baseline(baseline_path)
    allowed_counter = baseline_ui_counter(baseline)
    seen_counter: Counter[tuple[str, str]] = Counter()
    violation_rows: list[dict[str, object]] = []
    for violation in violations:
        seen_counter[violation.baseline_key] += 1
        row = asdict(violation)
        row["baseline_status"] = (
            "allowed"
            if seen_counter[violation.baseline_key]
            <= allowed_counter[violation.baseline_key]
            else "new"
        )
        violation_rows.append(row)

    return {
        "python": {
            "src_files": len(src_metrics),
            "src_lines": sum(item.lines for item in src_metrics),
            "test_files": len(test_metrics),
            "test_lines": sum(item.lines for item in test_metrics),
            "classes": sum(item.classes for item in metrics),
            "functions": sum(item.functions for item in metrics),
            "methods": sum(item.methods for item in metrics),
            "main_window_methods": main_window_method_count(root),
            "legacy_main_window_methods": legacy_main_window_method_count(root),
        },
        "largest_modules": [
            asdict(item)
            for item in sorted(metrics, key=lambda item: item.lines, reverse=True)[
                :largest_limit
            ]
        ],
        "major_package_imports": [
            {"source": source, "target": target, "count": count}
            for (source, target), count in sorted(package_edges.items())
            if source != target
        ],
        "dependency_violations": violation_rows,
        "package_cycles": package_cycles,
        "module_cycles": module_cycles,
        "duplicate_action_labels": [
            asdict(item) for item in duplicate_action_labels(root)
        ],
    }


def format_report(report: Mapping[str, object]) -> str:
    python = report["python"]
    assert isinstance(python, dict)
    lines = [
        "openRetop V3 architecture metrics",
        "=" * 35,
        (
            f"Production: {python['src_files']} Python files, "
            f"{python['src_lines']} lines"
        ),
        f"Tests:      {python['test_files']} Python files, {python['test_lines']} lines",
        (
            f"Symbols:    {python['classes']} classes, "
            f"{python['functions']} functions/methods "
            f"({python['methods']} direct class methods)"
        ),
        f"OpenRetopV3Window methods: {python['main_window_methods']}",
        f"Legacy OpenRetopWindow methods: {python['legacy_main_window_methods']}",
        "",
        "Largest modules",
    ]
    for item in report["largest_modules"]:
        lines.append(
            f"  {item['lines']:>6}  {item['path']} "
            f"(classes={item['classes']}, functions={item['functions']})"
        )

    lines.extend(["", "Major package imports"])
    for edge in report["major_package_imports"]:
        lines.append(
            f"  {edge['source']} -> {edge['target']}: {edge['count']}"
        )

    lines.extend(["", "Dependency violations"])
    violations = report["dependency_violations"]
    if not violations:
        lines.append("  none")
    for item in violations:
        lines.append(
            f"  [{item['baseline_status']}] {item['rule']}: "
            f"{item['path']}:{item['line']} imports {item['imported_module']}"
        )

    lines.extend(["", "Practical cycles"])
    if not report["package_cycles"] and not report["module_cycles"]:
        lines.append("  none")
    for cycle in report["package_cycles"]:
        lines.append(f"  package: {' -> '.join(cycle)}")
    for cycle in report["module_cycles"]:
        lines.append(f"  module: {' -> '.join(cycle)}")

    lines.extend(["", "Duplicate detectable action/menu labels"])
    duplicates = report["duplicate_action_labels"]
    if not duplicates:
        lines.append("  none")
    for item in duplicates:
        lines.append(
            f"  {item['label']!r}: {item['count']} "
            f"({', '.join(item['locations'])})"
        )
    return "\n".join(lines)


def _has_unexpected(findings: Mapping[str, object]) -> bool:
    return any(bool(value) for value in findings.values())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--largest", type=int, default=15)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--fail-on-new", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    baseline = args.baseline.resolve()
    report = build_report(root, baseline, max(1, int(args.largest)))
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    if args.fail_on_new and _has_unexpected(
        unexpected_architecture_findings(root, baseline)
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

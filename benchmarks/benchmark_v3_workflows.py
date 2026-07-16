"""Informative V3 startup/state/persistence/UI-model benchmark (no CI threshold)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "packages" / "workbench_ui"))

from application.state import AppState
from bootstrap import create_application
from curves.curve_state import CurveCollection, StoredCurve
from project.project_io import project_from_dict, project_to_dict
from project.project_state import project_from_app_state
from viewer.scene_builder import SceneBuilder
from workbench_ui import FieldDefinition, PropertyInspectorModel, SceneNode, SceneTreeModel


def _curves(count: int) -> CurveCollection:
    records: list[StoredCurve] = []
    base = np.column_stack(
        (
            np.linspace(0.0, 1.0, 24),
            np.sin(np.linspace(0.0, np.pi, 24)),
            np.zeros(24),
        )
    )
    for index in range(count):
        points = base + np.asarray([0.0, 0.0, index * 0.01])
        records.append(
            StoredCurve(
                id=f"curve-{index}",
                name=f"Curve {index}",
                section_result_id="",
                plane_id="",
                original_points=points.copy(),
                fitted_points=points,
                mean_error=0.0,
                max_error=0.0,
                is_closed=False,
            )
        )
    return CurveCollection(curves=records)


def _time(iterations: int, operation) -> tuple[float, object]:
    started = perf_counter()
    value: object = None
    for _ in range(iterations):
        value = operation()
    return perf_counter() - started, value


def run(iterations: int, curve_count: int) -> None:
    startup_seconds, composition = _time(iterations, create_application)
    state = AppState(curve_collection=_curves(curve_count))
    builder = SceneBuilder()
    snapshot_seconds, snapshot = _time(iterations, lambda: builder.build(state))
    project = project_from_app_state(
        mesh_object=None,
        proxy_quality="Medium",
        show_grid=True,
        show_axes=True,
        show_normals=False,
        section_axis="Z",
        section_offset=0.0,
        show_section_plane=False,
        curve_collection=state.curve_collection,
    )
    persistence_seconds, data = _time(
        iterations, lambda: project_from_dict(project_to_dict(project))
    )
    nodes = [SceneNode("root", "Scene", renameable=False)] + [
        SceneNode(item.id, item.name, parent_id="root")
        for item in state.curve_collection.curves
    ]
    tree = SceneTreeModel()
    fields = [
        FieldDefinition(f"field-{index}", f"Field {index}", index, "number")
        for index in range(max(curve_count // 4, 1))
    ]
    inspector = PropertyInspectorModel()
    ui_model_seconds, _ = _time(
        iterations, lambda: (tree.replace(nodes), inspector.replace(fields))
    )
    print(f"iterations={iterations} curves={curve_count}")
    print(f"composition startup: {startup_seconds / iterations * 1000:.3f} ms/op")
    print(f"scene snapshot:      {snapshot_seconds / iterations * 1000:.3f} ms/op")
    print(f"project round-trip:  {persistence_seconds / iterations * 1000:.3f} ms/op")
    print(f"tree/inspector:      {ui_model_seconds / iterations * 1000:.3f} ms/op")
    print(f"snapshot items:      {len(snapshot.render_items())}")
    print(f"project curves:      {len(data.curves)}")
    print(f"CAD backend:         {composition.cad.capabilities.backend_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--curves", type=int, default=250)
    args = parser.parse_args()
    run(max(args.iterations, 1), max(args.curves, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

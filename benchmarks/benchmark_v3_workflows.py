"""Informative V3 startup/state/persistence/UI-model benchmark (no CI threshold)."""

from __future__ import annotations

import argparse
from time import perf_counter

import numpy as np

from openretop.application.state import AppState
from openretop.bootstrap import create_application
from openretop.modeling.persistence import PROJECT_KEY, model_from_dict, model_to_dict
from openretop.project.project_io import project_from_dict, project_to_dict
from openretop.project.project_state import project_from_app_state
from openretop.viewer.modeling_scene import ModelingSceneInput
from openretop.viewer.scene_builder import SceneBuilder
from workbench_ui import FieldDefinition, PropertyInspectorModel, SceneNode, SceneTreeModel


def _state_with_curves(count: int) -> AppState:
    """A project with ``count`` 3D Sketch curves (the kind sections and the sketch tool make)."""

    state = AppState()
    base = np.column_stack(
        (
            np.linspace(0.0, 1.0, 24),
            np.sin(np.linspace(0.0, np.pi, 24)),
            np.zeros(24),
        )
    )
    for index in range(count):
        state.model.sketch.add_polyline_curve(base + np.asarray([0.0, 0.0, index * 0.01]), name=f"Curve {index}")
    return state


def _time(iterations: int, operation) -> tuple[float, object]:
    started = perf_counter()
    value: object = None
    for _ in range(iterations):
        value = operation()
    return perf_counter() - started, value


def run(iterations: int, curve_count: int) -> None:
    startup_seconds, composition = _time(iterations, create_application)
    composition.modeling_controller.shutdown()
    state = _state_with_curves(curve_count)
    curves = state.model.sketch.curves
    modeling = ModelingSceneInput(sketch_curves=tuple((curve.id, curve.polyline, False) for curve in curves))
    builder = SceneBuilder()
    snapshot_seconds, snapshot = _time(iterations, lambda: builder.build(state, modeling=modeling))
    project = project_from_app_state(
        mesh_object=None,
        proxy_quality="Medium",
        show_grid=True,
        show_axes=True,
        show_normals=False,
        section_axis="Z",
        section_offset=0.0,
        show_section_plane=False,
    )
    project.metadata[PROJECT_KEY] = model_to_dict(state.model)

    def round_trip():
        data = project_from_dict(project_to_dict(project))
        return model_from_dict(data.metadata.get(PROJECT_KEY))[0]

    persistence_seconds, restored = _time(iterations, round_trip)
    nodes = [SceneNode("root", "Scene", renameable=False)] + [
        SceneNode(f"sketch:{curve.id}", curve.name, parent_id="root") for curve in curves
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
    print(f"project curves:      {len(restored.sketch.curves)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--curves", type=int, default=250)
    args = parser.parse_args()
    run(max(args.iterations, 1), max(args.curves, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

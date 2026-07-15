"""Informative scene-synchronization benchmark; no CI timing threshold."""

from __future__ import annotations

from dataclasses import replace
import argparse
import json
from time import perf_counter

import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer

from viewer.actor_factories import VTKActorAdapter
from viewer.scene_synchronizer import SceneSynchronizer
from viewer.scene_types import CurveRenderItem, SceneSnapshot


def run(iterations: int) -> dict[str, float | int]:
    points = np.column_stack(
        (
            np.linspace(0.0, 100.0, 2000),
            np.sin(np.linspace(0.0, 40.0, 2000)),
            np.zeros(2000),
        )
    )
    item = CurveRenderItem(id="benchmark-curve", revision=1, points=points)
    snapshot = SceneSnapshot(revision=1, curves=(item,))
    synchronizer = SceneSynchronizer(VTKActorAdapter(vtkRenderer()))
    started = perf_counter()
    first = synchronizer.synchronize(snapshot)
    for index in range(max(0, iterations - 1)):
        synchronizer.synchronize(replace(snapshot, revision=index + 2))
    elapsed = perf_counter() - started
    return {
        "iterations": iterations,
        "seconds": elapsed,
        "iterations_per_second": iterations / elapsed if elapsed else 0.0,
        "first_created": first.created,
        "last_reused": synchronizer.last_diagnostics.reused,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=25)
    args = parser.parse_args()
    print(json.dumps(run(max(1, args.iterations)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Audit 2: the Surface workflow on the bracket - fit each face by clicking it, trim into a
solid, compare, export STEP."""

import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent))
from human import Human, answer_dialog, log, stand_in_file_dialogs  # noqa: E402

from openretop.benchmarks import make_part, scan_from_part  # noqa: E402

out = Path(sys.argv[1])
part = make_part("bracket")
scan = scan_from_part(part, noise_sigma=0.02, seed=1, edge_length=1.0)
import trimesh  # noqa: E402

stl = out.parent / "human_bracket.stl"
trimesh.Trimesh(np.asarray(scan.vertices), np.asarray(scan.triangles)).export(stl)

h = Human(out)
w = h.window
stand_in_file_dialogs(open_path=stl)
answer_dialog(choice="mm")
h.click_toolbar("Open Scan")
h.idle()
h.say("opened")

vertices, triangles = np.asarray(scan.vertices), np.asarray(scan.triangles)
centers = vertices[triangles].mean(axis=1)
normals = np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
normals /= np.linalg.norm(normals, axis=1)[:, None] + 1e-12
VIEWS = {  # named view key -> direction from the part toward the camera
    Qt.Key_1: (0, -1, 0), Qt.Key_2: (0, 1, 0), Qt.Key_3: (-1, 0, 0), Qt.Key_4: (1, 0, 0), Qt.Key_5: (0, 0, 1), Qt.Key_6: (0, 0, -1),
}
from scipy.spatial import cKDTree  # noqa: E402


def seed_of(face: int) -> int:
    inside = scan.face_labels == face
    distance, _ = cKDTree(centers[~inside]).query(centers[inside])
    return int(np.flatnonzero(inside)[int(np.argmax(distance))])


log(f"bracket faces: {len(part.face_types)} {list(part.face_types)}")
h.tab("Surface")
h.click_toolbar("Fit Surface")
log(f"  panel title {w.surfacing_panel.title.text()!r}; hint {h.hint()!r}")
results = []
order = sorted(range(len(part.face_types)), key=lambda f: -int(np.sum(scan.face_labels == f)))
for face in order:
    seed = seed_of(face)
    normal = normals[seed]
    # as a user orbits until the face is in view: look at it along its normal
    cam = w.viewport.renderer.GetActiveCamera()
    point = centers[seed]
    distance = max(cam.GetDistance(), 150.0)
    cam.SetFocalPoint(*point)
    cam.SetPosition(*(point + normal * distance))
    up = np.array([0.0, 0.0, 1.0]) if abs(normal[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    cam.SetViewUp(*up)
    w.viewport.renderer.ResetCameraClippingRange()
    w.viewport.render_window.Render()
    h.wait(100)
    spot = h.screen_of(centers[seed])
    if spot is None:
        results.append((face, part.face_types[face], "off screen"))
        continue
    h.click(*spot)
    selected = h.composition.modeling_controller.selection()
    count = 0 if selected is None else selected.count
    truth = 0.0 if not count else float(np.mean(scan.face_labels[selected.mask] == face))
    t = time.perf_counter()
    created = h.click_panel("Create")
    status = h.status()
    results.append((face, part.face_types[face], f"{count} tris ({truth:.0%} right) -> {status[:90]} [{time.perf_counter()-t:.1f}s]"))
    h.click_panel("Clear") if h.panel_button("Clear") else None
for row in results:
    log(f"  face {row[0]} {row[1]}: {row[2]}")
model = h.composition.state.model
log(f"  surfaces: {len(model.entities)}")
h.key(Qt.Key_7, "", Qt.ControlModifier)
h.shot("fitted")
h.click_panel("Done")

log("== Trim (automatic) and Apply (sew)")
t = time.perf_counter()
h.click_toolbar("Trim")
h.click_panel("Split Surfaces")
h.say(f"split [{time.perf_counter()-t:.1f}s]")
h.shot("pieces")
t = time.perf_counter()
h.click_panel("Apply")
h.say(f"applied [{time.perf_counter()-t:.1f}s]")
bodies = [e for e in model.entities if e.is_body]
log(f"  bodies: {[(b.name, b.kind, round(b.stats.get('volume', 0), 1), b.stats.get('solid')) for b in bodies]}; true volume {part.truth.get('volume') if hasattr(part, 'truth') and isinstance(part.truth, dict) else '?'}")
h.click_panel("Done")
h.shot("solid")

log("== Compare")
h.click_toolbar("Compare")
h.click_panel("Compute")
h.say("compare")
log(f"  compare text: {w.surfacing_panel.compare_info.text()!r}")
h.shot("compare")
h.click_panel("Done")

log("== Export STEP")
step = out / "bracket.step"
stand_in_file_dialogs(save_path=step)
h.click_toolbar("Export")
h.say("export")
log(f"  file: {step.exists() and step.stat().st_size} bytes")
h.close()
log("done")

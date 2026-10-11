"""Align to World on a tilted bracket scan: Align, click the top, a side, the boss hole, Apply;
how square is it, and does Ctrl+Z put it back?"""

import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent))
from human import Human, answer_dialog, log, stand_in_file_dialogs  # noqa: E402

from openretop.application.transform_math import rotation_matrix  # noqa: E402
from openretop.benchmarks import make_part, scan_from_part  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
part = make_part("bracket")
scan = scan_from_part(part, noise_sigma=0.02, seed=1, edge_length=1.0)
tilt = rotation_matrix(np.array([17.0, -23.0, 31.0]))
shift = np.array([12.0, -40.0, 7.5])
vertices = np.asarray(scan.vertices) @ tilt.T + shift
triangles = np.asarray(scan.triangles)
import trimesh  # noqa: E402

stl = out.parent / "human_bracket_tilted.stl"
trimesh.Trimesh(vertices, triangles, process=False).export(stl)

h = Human(out)
w = h.window
stand_in_file_dialogs(open_path=stl)
answer_dialog(choice="mm")
h.click_toolbar("Open Scan")
h.idle()
h.say("opened")

centers = vertices[triangles].mean(axis=1)
normals = np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
normals /= np.linalg.norm(normals, axis=1)[:, None] + 1e-12
corner, edge1, edge2 = vertices[triangles[:, 0]], vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]]


def first_hit(origin: np.ndarray, direction: np.ndarray) -> int:
    p = np.cross(direction, edge2)
    det = np.einsum("ij,ij->i", edge1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = origin - corner
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, edge1)
    v = (q @ direction) * inv
    t = np.einsum("ij,ij->i", edge2, q) * inv
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)
    return int(np.flatnonzero(hit)[np.argmin(t[hit])]) if hit.any() else -1


def look_and_click(face: int) -> None:
    """As a user orbits until the face shows (into a hole at an angle), then clicks it."""

    from scipy.spatial import cKDTree

    inside = np.flatnonzero(scan.face_labels == face)
    distance, _ = cKDTree(centers[scan.face_labels != face]).query(centers[inside])
    for seed in inside[np.argsort(-distance)[:30]]:
        normal = normals[seed]
        for direction in [normal] + [d / np.linalg.norm(d) for d in (normal + 1.2 * axis for axis in np.vstack([np.identity(3), -np.identity(3)]))]:
            if direction @ normal < 0.25:
                continue
            hit = first_hit(centers[seed] + direction * 300.0, -direction)
            if hit >= 0 and scan.face_labels[hit] == face:
                cam = w.viewport.renderer.GetActiveCamera()
                cam.SetFocalPoint(*centers[seed])
                cam.SetPosition(*(centers[seed] + direction * 160.0))
                cam.SetViewUp(*(np.array([0.0, 0.0, 1.0]) if abs(direction[2]) < 0.9 else np.array([0.0, 1.0, 0.0])))
                w.viewport.renderer.ResetCameraClippingRange()
                w.viewport.render_window.Render()
                h.wait(100)
                spot = h.screen_of(centers[seed])
                if spot is not None:
                    h.click(*spot)
                    return
    log(f"  !! could not see face {face}")


h.tab("Scan")
h.click_toolbar("Align")
log(f"  panel {w.surfacing_panel.title.text()!r}; hint {h.hint()!r}")
for face, what in ((1, "top"), (5, "front side"), (12, "boss hole")):
    look_and_click(face)
    h.say(f"click the {what}")
    panel = w.surfacing_panel
    log(f"  rows: {[label.text() for label in panel.align_labels]} targets {[combo.currentText() for combo in panel.align_targets]}")
    log(f"  {panel.align_summary.text()!r}")
h.key(Qt.Key_1, "", Qt.ControlModifier)
h.shot("picked")
h.click_panel("Apply")
h.say("applied")
net = w.composition.transform_controller.current_object_matrix()[:3, :3] @ tilt  # part frame -> world
errors = []
for normal in (np.array([0.0, 0.0, 1.0]), np.array([0.0, -1.0, 0.0])):
    turned = net @ normal
    errors.append(float(np.degrees(np.arccos(np.clip(np.max(np.abs(turned)), -1, 1)))))
log(f"  top / side off the world axes by {errors[0]:.4f} / {errors[1]:.4f} deg (acceptance 0.05)")
h.key(Qt.Key_1, "", Qt.ControlModifier)
h.shot("front_after")
h.key(Qt.Key_7, "", Qt.ControlModifier)
h.shot("top_after")
h.key(Qt.Key_Z, "z", Qt.ControlModifier)
h.say("Ctrl+Z")
back = w.composition.state.mesh_object
log(f"  after undo: rotation {np.round(back.rotation, 6).tolist()} location {np.round(back.location, 6).tolist()}")
h.close()
log("done")

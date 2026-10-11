"""Audit 2: the Surface workflow on the bracket - fit each face by clicking it, trim into a
solid, compare, export STEP."""

import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

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


corner, edge1, edge2 = vertices[triangles[:, 0]], vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]]


def first_hit(origin: np.ndarray, direction: np.ndarray) -> int:
    """The scan triangle a ray meets first (-1: none): Moller-Trumbore over all triangles."""

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
    if not hit.any():
        return -1
    candidates = np.flatnonzero(hit)
    return int(candidates[np.argmin(t[candidates])])


def view_of(face: int) -> tuple[int, np.ndarray]:
    """A spot on the face and a direction to look at it from where nothing is in the way, as a
    user orbits until the face shows (inside a hole: looking in at an angle, not through the
    opposite wall). Tries the face's deepest triangles along its normal, then tilted views."""

    inside = np.flatnonzero(scan.face_labels == face)
    distance, _ = cKDTree(centers[scan.face_labels != face]).query(centers[inside])
    seeds = inside[np.argsort(-distance)[:40]]
    axes = [np.array(axis, dtype=float) for axis in VIEWS.values()]
    for seed in seeds:
        normal = normals[seed]
        candidates = [normal] + [d / np.linalg.norm(d) for d in (normal + 1.2 * axis for axis in axes) if np.linalg.norm(d) > 1e-6]
        candidates = [d for d in candidates if d @ normal > 0.25]
        for direction in candidates:
            hit = first_hit(centers[seed] + direction * 300.0, -direction)
            if hit >= 0 and scan.face_labels[hit] == face:
                return int(seed), direction
    return int(seeds[0]), normals[seeds[0]]


def brush_across(face: int) -> None:
    """What the message says to do for a narrow face: Brush, a brush narrower than the face
    (typed into Brush size), and paint along it."""

    h.click_panel("Brush")
    field = w.surfacing_panel.brush
    QTest.mouseDClick(field.lineEdit(), Qt.LeftButton)
    QTest.keyClick(field.lineEdit(), Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(field.lineEdit(), "0.8")
    QTest.keyClick(field.lineEdit(), Qt.Key_Return)
    h.idle()
    points = vertices[np.unique(triangles[scan.face_labels == face])]
    middle = points.mean(axis=0)
    _, _, axes_ = np.linalg.svd(points - middle)
    span = (points - middle) @ axes_[0]
    start = h.screen_of(middle + axes_[0] * np.quantile(span, 0.1))
    end = h.screen_of(middle + axes_[0] * np.quantile(span, 0.9))
    if start is not None and end is not None:
        h.drag(start, end, steps=16)


log(f"bracket faces: {len(part.face_types)} {list(part.face_types)}")
h.tab("Surface")
h.click_toolbar("Fit Surface")
log(f"  panel title {w.surfacing_panel.title.text()!r}; hint {h.hint()!r}")
results = []
order = sorted(range(len(part.face_types)), key=lambda f: -int(np.sum(scan.face_labels == f)))
for face in order:
    seed, normal = view_of(face)
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
    if "too small" in status:
        h.click_panel("Clear") if h.panel_button("Clear") else None
        brush_across(face)
        selected = h.composition.modeling_controller.selection()
        count = 0 if selected is None else selected.count
        truth = 0.0 if not count else float(np.mean(scan.face_labels[selected.mask] == face))
        h.click_panel("Create")
        status = "brushed: " + h.status()
        h.click_panel("Smart")
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

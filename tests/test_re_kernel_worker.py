"""S-03: kernel operations run in a worker process; crashes and hangs never reach the app."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.cad_kernel.worker import KernelWorker


def _saddle_points(count: int = 30) -> tuple[np.ndarray, np.ndarray]:
    x, y = np.meshgrid(np.linspace(-10, 10, count), np.linspace(-10, 10, count), indexing="ij")
    points = np.c_[x.ravel(), y.ravel(), ((x**2 - y**2) / 40.0).ravel()]
    index = np.arange(count * count).reshape(count, count)
    a, b, c, d = index[:-1, :-1].ravel(), index[:-1, 1:].ravel(), index[1:, :-1].ravel(), index[1:, 1:].ravel()
    return points, np.r_[np.c_[a, c, d], np.c_[a, d, b]]


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class WorkerProcessTests(unittest.TestCase):
    """One real worker process for the class: starting one costs a second or two."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.worker = KernelWorker(timeout=60.0)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.worker.shutdown()

    def test_a_job_runs_in_the_worker_and_returns_plain_data(self) -> None:
        points, triangles = _saddle_points()
        reply = self.worker.call("fit_surface", points, triangles, kind="freeform", control_u=6, control_v=6)
        self.assertTrue(reply.ok, reply.error)
        self.assertEqual(reply.value["kind"], "freeform")
        self.assertIsInstance(reply.value["brep"], bytes)
        self.assertGreater(len(reply.value["triangles"]), 0)
        self.assertLess(reply.value["rms"], 0.01)
        self.assertTrue(self.worker.alive)

    def test_a_job_error_is_reported_and_the_worker_stays_up(self) -> None:
        reply = self.worker.call("fit_surface", np.zeros((3, 3)))
        self.assertFalse(reply.ok)
        self.assertIn("larger area", reply.error)
        self.assertFalse(reply.crashed)
        self.assertTrue(self.worker.call("selftest_sleep", 0.0).ok)

    def test_a_crash_is_contained_and_the_next_job_works(self) -> None:
        before = self.worker.restarts
        reply = self.worker.call("selftest_crash")
        self.assertFalse(reply.ok)
        self.assertTrue(reply.crashed)
        self.assertIn("crashed", reply.error)
        again = self.worker.call("selftest_sleep", 0.01)
        self.assertTrue(again.ok)
        self.assertGreater(self.worker.restarts, before)

    def test_a_hang_is_stopped_at_the_timeout(self) -> None:
        reply = self.worker.call("selftest_sleep", 30.0, timeout=1.0)
        self.assertFalse(reply.ok)
        self.assertTrue(reply.timed_out)
        self.assertLess(reply.seconds, 10.0)
        self.assertTrue(self.worker.call("selftest_sleep", 0.0).ok)

    def test_unknown_jobs_are_refused(self) -> None:
        reply = self.worker.call("surface_result")  # a helper, not a job
        self.assertFalse(reply.ok)
        self.assertIn("unknown kernel job", reply.error)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class InlineJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.worker = KernelWorker(inline=True)

    def test_fit_surface_auto_finds_a_plane(self) -> None:
        rng = np.random.default_rng(0)
        points = np.c_[rng.uniform(-10, 10, (400, 2)), rng.normal(0, 0.01, 400)]
        reply = self.worker.call("fit_surface", points, kind="auto")
        self.assertTrue(reply.ok, reply.error)
        self.assertEqual(reply.value["kind"], "plane")
        self.assertEqual(len(reply.value["point_distances"]), 400)

    def test_extend_trim_sew_and_export(self) -> None:
        # two planes meeting at a right angle, each fitted oversize: trim keeps the L
        rng = np.random.default_rng(1)
        floor = np.c_[rng.uniform(0, 20, (500, 2)), np.zeros(500)]
        wall = np.c_[np.zeros(500), rng.uniform(0, 20, 500), rng.uniform(0, 20, 500)]
        fits = [self.worker.call("fit_surface", data, kind="plane", expand=0.1) for data in (floor, wall)]
        self.assertTrue(all(fit.ok for fit in fits))
        longer = self.worker.call("extend", fits[0].value["brep"], 2.0)
        self.assertGreater(longer.value["area"], fits[0].value["area"])
        scan = np.vstack([floor, wall])
        normals = np.vstack([np.tile([0, 0, 1.0], (500, 1)), np.tile([1.0, 0, 0], (500, 1))])
        trimmed = self.worker.call("trim", [fit.value["brep"] for fit in fits], scan, normals, tolerance=0.1)
        self.assertTrue(trimmed.ok, trimmed.error)
        kept = [piece for piece in trimmed.value["pieces"] if piece["keep"]]
        self.assertEqual(len(kept), 2)
        sewn = self.worker.call("sew", [piece["brep"] for piece in kept])
        self.assertTrue(sewn.ok, sewn.error)
        self.assertEqual(sewn.value["kind"], "shell")
        self.assertGreater(sewn.value["free_edges"], 0)
        with tempfile.TemporaryDirectory() as directory:
            for file_format in ("step", "iges"):
                path = str(Path(directory) / f"model.{file_format}")
                written = self.worker.call("export", [sewn.value["brep"]], path, file_format=file_format)
                self.assertTrue(written.ok, written.error)
                self.assertEqual(written.value["faces_back"], written.value["faces"])
                self.assertAlmostEqual(written.value["area_back"], written.value["area"], delta=0.01 * written.value["area"])

    def test_deviation_is_signed(self) -> None:
        points = np.array([[1.0, 1.0, 0.0], [2.0, 3.0, 0.0], [5.0, 5.0, 0.0], [3.0, 3.0, 0.0]])
        rng = np.random.default_rng(2)
        cloud = np.c_[rng.uniform(0, 10, (300, 2)), np.zeros(300)]
        plane = self.worker.call("fit_surface", cloud, kind="plane").value
        distances = self.worker.call("deviation", [plane["brep"]], points + [0, 0, 0.3]).value
        np.testing.assert_allclose(np.abs(distances), 0.3, atol=1e-4)
        self.assertEqual(len(set(np.sign(distances))), 1)


if __name__ == "__main__":
    unittest.main()

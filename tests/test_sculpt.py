import unittest

import numpy as np

from plandscape.fauna import sculpt
from plandscape.fauna.agents import FAUNA
from plandscape.fauna.bodies import body, rig
from plandscape.fauna.sculpt import Sculpt


def edge_counts(m):
    I = m.indices
    e = np.sort(np.concatenate([I[:, [0, 1]], I[:, [1, 2]], I[:, [2, 0]]]), 1)
    _, c = np.unique(e, axis=0, return_counts=True)
    return c


def volume(m):
    P, I = m.positions.astype(float), m.indices
    return np.einsum("ij,ij->i", P[I[:, 0]], np.cross(P[I[:, 1]], P[I[:, 2]])).sum() / 6


class Sculpting(unittest.TestCase):
    def test_sdf_of_primitives(self):
        s = Sculpt().ellipsoid((0, 0, 0), (1.0, 1.0, 1.0), (1, 0, 0))
        d = s.field(np.array([[2.0, 0, 0], [0, 0, 0.5]]))
        self.assertAlmostEqual(d[0], 1.0, places=6)          # exact for a sphere
        self.assertAlmostEqual(d[1], -0.5, places=6)
        c = Sculpt().cone((0, 0, 0), (0, 0, 1), 0.2, 0.1, (1, 0, 0))
        self.assertAlmostEqual(float(c.field(np.array([[0.5, 0, 0.0]]))[0]), 0.3, places=6)

    def test_smooth_union_blends_shape_and_colour(self):
        s = Sculpt().ellipsoid((-0.5, 0, 0), (0.6, 0.6, 0.6), (1, 0, 0), k=0.3)
        s.ellipsoid((0.5, 0, 0), (0.6, 0.6, 0.6), (0, 0, 1), k=0.3)
        d, c = s.field(np.array([[0.0, 0, 0.0]]), colour=True)
        self.assertLess(d[0], -0.1 - 0.3 / 4 + 0.2)          # deeper than a hard union at the seam
        self.assertAlmostEqual(c[0, 0], c[0, 2], places=6)   # half red, half blue in the middle

    def test_mesh_is_watertight_oriented_and_on_budget(self):
        s = Sculpt().ellipsoid((0, 0, 1), (0.6, 0.25, 0.3), (0.6, 0.4, 0.25), k=0.1)
        s.cone((0.5, 0, 1.1), (0.8, 0, 1.5), 0.12, 0.08, (0.6, 0.4, 0.25), k=0.08)
        m = s.mesh(target=4000)
        c = edge_counts(m)
        self.assertTrue(np.all(c % 2 == 0) and (c == 2).mean() > 0.999)   # closed: no holes; rare 4-face pinches
        self.assertGreater(volume(m), 0)
        self.assertTrue(0.5 * 4000 * sculpt.DETAIL < m.n_tris < 1.6 * 4000 * sculpt.DETAIL, m.n_tris)
        self.assertLess(np.abs(np.linalg.norm(m.nrm, axis=1) - 1).max(), 1e-4)
        self.assertLess(np.abs(s.field(m.positions.astype(float))).max(), 2e-3)   # vertices sit on the surface


class Bodies(unittest.TestCase):
    def test_every_species_rig(self):
        for k, spec in FAUNA.items():
            r = rig(k, spec.rgb)
            want = {"hop": 0, "biped": 2, "quad": 4}[r["kind"]]
            self.assertEqual(len(r["legs"]), want, k)
            for lg in r["legs"]:
                self.assertAlmostEqual(lg["l1"] + lg["l2"], r["hip"] / 0.95, places=5)
            self.assertTrue(np.all(edge_counts(r["torso"]) % 2 == 0), k)   # closed parts, no boundary edges
            b = body(k, spec.rgb)
            self.assertLess(b.n_tris, 12000, k)
            self.assertAlmostEqual(float(b.positions[:, 2].min()), 0.0, delta=0.03 + 0.02 * r["hip"])   # feet on the ground

    def test_scale_keeps_normals(self):
        a, b = rig("white_tailed_deer", (0.5, 0.4, 0.3)), rig("white_tailed_deer", (0.5, 0.4, 0.3), scale=1.1)
        self.assertTrue(np.allclose(b["torso"].positions, a["torso"].positions * 1.1, atol=1e-5))
        self.assertTrue(np.allclose(b["torso"].nrm, a["torso"].nrm))
        self.assertAlmostEqual(b["hip"], a["hip"] * 1.1)


if __name__ == "__main__":
    unittest.main()

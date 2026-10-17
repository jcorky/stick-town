"""Sex and season variants, arms, swept tubes, coat attributes and shared-geometry tints (TECHNIQUES §37)."""
import json
import os
import unittest

import numpy as np

from plandscape.fauna import anatomy as A
from plandscape.fauna import coat, gait
from plandscape.fauna.agents import FAUNA
from plandscape.fauna.bodies import body, rig
from plandscape.fauna.sculpt import tube

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = json.load(open(os.path.join(ROOT, "catalog", "fauna_sources.json")))["species"]
DEER = FAUNA["white_tailed_deer"].rgb


def sat(rgb):
    rgb = np.asarray(rgb)
    return (rgb.max(-1) - rgb.min(-1)) / np.maximum(rgb.max(-1), 1e-6)


class Variants(unittest.TestCase):
    def test_antlers_follow_the_mdc_calendar(self):
        doe = rig("white_tailed_deer", DEER, sex="f")["neck"]["mesh"].positions[:, 2].max()
        tops = {s: rig("white_tailed_deer", DEER, sex="m", season=s)["neck"]["mesh"].positions[:, 2].max()
                for s in ("spring", "summer", "fall", "winter")}
        self.assertGreater(tops["summer"], doe + 0.25)       # a full rack in velvet by summer (growth Apr–Aug)
        self.assertGreater(tops["fall"], doe + 0.25)
        self.assertLess(tops["spring"], doe + 0.1)           # April: buds only
        src = SRC["white_tailed_deer"]["antlers"]["value"]
        self.assertTrue(src["grow"].startswith("April") and src["shed"].startswith("February"))
        self.assertEqual((A.ANTLER["summer"], A.ANTLER["fall"]), ("velvet", "hard"))

    def test_velvet_is_fur_and_hard_antler_is_bare(self):
        for season, kind in (("summer", 1), ("fall", 0)):
            h = rig("white_tailed_deer", DEER, sex="m", season=season)["neck"]["mesh"]
            top = h.positions[:, 2] > 0.62                    # above the ears: antler only
            k = h.attrs["_COAT"][top, 0] // 32
            self.assertTrue((k == kind).all(), (season, np.bincount(k)))

    def test_leg_fur_runs_down_the_limb(self):
        r = rig("white_tailed_deer", DEER)
        self.assertTrue((r["torso"].attrs["_COAT"][:, 0] // 32 <= 1).all())
        for part in ("thigh", "shank"):
            k = r["legs"][0][part].attrs["_COAT"][:, 0] // 32
            self.assertTrue((k[k > 0] == coat.KIND["fur_z"]).all(), part)   # hooves stay bare
            self.assertGreater(float((k == coat.KIND["fur_z"]).mean()), 0.5, part)

    def test_winter_coat_is_greyer(self):
        def mean_sat(season):
            t = rig("white_tailed_deer", DEER, season=season)["torso"]
            up = t.nrm[:, 2] > 0.5                            # the back, not the white belly
            return float(sat(t.colors[up]).mean())
        self.assertLess(mean_sat("winter"), mean_sat("summer") * 0.8)

    def test_sex_sizes_keep_withers_in_the_sourced_range(self):
        lo, hi = SRC["white_tailed_deer"]["shoulder"]["value"]
        for sex in ("f", "m"):
            r = rig("white_tailed_deer", DEER, sex=sex)
            P, sx = r["torso"].positions, r["legs"][0]["hip"][0]
            w = float(P[np.abs(P[:, 0] - sx) < 0.05, 2].max()) * r["size"]
            self.assertTrue(lo <= w <= hi, (sex, w))
        m = SRC["white_tailed_deer"]["mass_by_sex"]["value"]
        ratio = (np.mean(m["m"]) / np.mean(m["f"])) ** (1 / 3)
        self.assertAlmostEqual(A.SEX_SIZE["white_tailed_deer"]["m"] / A.SEX_SIZE["white_tailed_deer"]["f"], ratio, 1)

    def test_hen_is_beardless_grey_headed_and_smaller(self):
        tk = FAUNA["wild_turkey"].rgb
        g, h = rig("wild_turkey", tk, sex="m"), rig("wild_turkey", tk, sex="f")
        self.assertLess(h["size"], g["size"])
        self.assertLess(h["torso"].n_tris, g["torso"].n_tris)   # no beard
        top = lambda r: r["neck"]["mesh"].colors[r["neck"]["mesh"].positions[:, 2] > 0.2]
        self.assertLess(sat(top(h)).mean(), sat(top(g)).mean())    # grey head, not red and blue
        irid = lambda r: r["torso"].attrs["_COAT"][:, 3].mean()
        self.assertGreater(irid(g), 2 * irid(h))

    def test_people_are_sourced_statures_with_swinging_arms(self):
        for sex in ("m", "f"):
            r = rig("human", (0.3, 0.4, 0.5), sex=sex)
            crown = float(r["torso"].positions[:, 2].max())
            self.assertLess(abs(crown - A.HUMAN_MODEL), 0.03)
            src = SRC["human"]["stature" if sex == "m" else "stature_female"]["value"]
            self.assertAlmostEqual(crown * r["size"], src, delta=0.04)
            self.assertEqual(len(r["arms"]), 2)
            self.assertEqual([a["side"] for a in r["arms"]], [1.0, -1.0])
        hips = np.c_[np.sin(np.linspace(0, 6, 50)), -np.sin(np.linspace(0, 6, 50))] * 0.3
        left, right = gait.arm_swing(hips, (0.0, 0.0))
        self.assertGreater(np.corrcoef(left, hips[:, 1])[0, 1], 0.99)    # left arm with the right leg
        self.assertLess(np.corrcoef(left, hips[:, 0])[0, 1], -0.99)

    def test_tube_is_closed_and_outward(self):
        m = tube([(0, 0, 0), (0, 0.1, 0.3), (0.1, 0.2, 0.5)], [0.02, 0.015, 0.004], (1, 1, 1), sides=6, per=3, tip=2)
        I = m.indices
        e = np.sort(np.concatenate([I[:, [0, 1]], I[:, [1, 2]], I[:, [2, 0]]]), 1)
        self.assertTrue((np.unique(e, axis=0, return_counts=True)[1] == 2).all())
        self.assertGreater(float((np.sum(m.geometric_normals() * m.nrm, 1) > 0).mean()), 0.95)

    def test_bird_legs_come_out_of_the_body(self):
        for k in ("wild_turkey", "great_blue_heron"):
            r = rig(k, FAUNA[k].rgb, sex="m")
            P = r["torso"].positions
            for lg in r["legs"]:   # the belly reaches below the hip joint, so the thigh's top is buried
                x, y, z = lg["hip"]
                near = (np.abs(P[:, 0] - x) < 0.04) & (np.abs(P[:, 1] - y) < 0.04)
                self.assertLess(float(P[near, 2].min()), z, k)

    def test_ears_are_closed_shells_hollow_forward(self):
        from plandscape.fauna.sculpt import leaf
        for shape in ("oval", "pointed"):
            m = leaf(0.16, 0.09, 0.012, shape=shape)
            I = m.indices
            e = np.sort(np.concatenate([I[:, [0, 1]], I[:, [1, 2]], I[:, [2, 0]]]), 1)
            self.assertTrue((np.unique(e, axis=0, return_counts=True)[1] % 2 == 0).all())
            mid = (np.abs(m.positions[:, 1]) < 0.01) & (m.positions[:, 2] > 0.04) & (m.positions[:, 2] < 0.12)
            front = mid & (m.positions[:, 0] > np.median(m.positions[mid, 0]))
            self.assertGreater(float(m.nrm[front, 0].mean()), 0.5)       # the hollow faces +x
            self.assertLess(float(m.positions[:, 0].max()), 1e-6)         # cupped: no part bulges forward

    def test_every_body_has_a_complete_coat(self):
        for k, sp in FAUNA.items():
            b = body(k, sp.rgb, 1.0, "m")
            C = b.attrs["_COAT"]
            self.assertEqual(len(C), len(b.positions))
            self.assertTrue(C.any(1).all(), k)                                  # nothing left unset
            dark = (b.colors @ np.array([0.3, 0.59, 0.11])) < coat.DARK_LUM
            self.assertTrue((C[dark, 0] == 0).all(), k)                         # eyes, noses, hooves bare

    def test_tints_share_geometry(self):
        from plandscape.export.gltf import GLB
        from plandscape.mesh import Mesh
        g = GLB()
        m = Mesh(np.eye(3, dtype=np.float32), np.ones((3, 3), np.float32), np.array([[0, 1, 2]], np.uint32))
        a = g.mesh(m, "a", g.material("x"))
        b = g.variant(a, "b", g.material("y", factor=0.7))
        pa, pb = g.meshes[a]["primitives"][0], g.meshes[b]["primitives"][0]
        self.assertEqual(pa["attributes"], pb["attributes"])
        self.assertNotEqual(pa["material"], pb["material"])
        self.assertEqual(g.materials[pb["material"]]["pbrMetallicRoughness"]["baseColorFactor"][:3], [0.7] * 3)


if __name__ == "__main__":
    unittest.main()

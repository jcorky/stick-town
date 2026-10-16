import json
import os
import shutil
import subprocess
import unittest

import numpy as np

from plandscape.export.gltf import GLB
from plandscape.flora.tree import generate_tree
from plandscape.mesh import Mesh
from plandscape.scene.planner import plan
from plandscape.wind import Wind, constants, sway
from plandscape.wind.attrs import pack, tree_attributes, unpack
from plandscape.wind.field import BEAUFORT, SIGMA_U, SIGMA_V
from plandscape.wind.response import drag, drag_slope, mechanics, transfer

ROOT = os.path.join(os.path.dirname(__file__), "..")


class WindField(unittest.TestCase):
    def test_beaufort_from_noaa_knots(self):
        self.assertAlmostEqual(BEAUFORT[3], 0.5144 * 8.5, places=2)
        self.assertTrue(all(BEAUFORT[k] < BEAUFORT[k + 1] for k in range(12)))

    def test_variance_matches_measured_intensity(self):
        w = Wind(force=5, canopy_h=20, seed=1)
        Ur = w.Uh * np.log((22 - w.d) / w.z0) / np.log((20 - w.d) / w.z0)
        su = np.sqrt((w.comps["au"] ** 2).sum() / 2) * Ur
        sv = np.sqrt((w.comps["av"] ** 2).sum() / 2) * Ur
        self.assertAlmostEqual(su / w.ustar, SIGMA_U["forest"], places=3)
        self.assertAlmostEqual(sv / su, SIGMA_V, places=3)

    def test_profile(self):
        w = Wind(force=4, canopy_h=20)
        self.assertAlmostEqual(float(w.mean_speed(10.0, 0.0)), w.U10, places=6)   # open country at 10 m
        self.assertAlmostEqual(float(w.mean_speed(20.0, 1.0)), w.Uh, places=6)    # canopy top
        z = np.array([2.0, 8.0, 14.0, 19.9])
        self.assertTrue(np.all(np.diff(w.mean_speed(z, 1.0)) > 0))
        self.assertLess(float(w.mean_speed(0.3, 1.0)), float(w.mean_speed(0.3, 0.0)))  # sheltered under trees

    def test_frozen_turbulence_travels_downwind(self):
        w = Wind(force=4, from_deg=270, canopy_h=20, seed=2)   # from the west: air moves east
        t = np.linspace(0, 120, 2401)
        a, _ = w.gust(0.0, 0.0, t)
        b, _ = w.gust(30.0, 0.0, t + 30.0 / w.Uc)
        self.assertLess(np.abs(a - b).max(), 1e-9)

    def test_davenport_coherence_on_average(self):
        f, eta, Uc, C = 0.2, 6.0, 3.0, constants()["DAVENPORT_CY"]
        g = C / (2 * np.pi)
        c = g * np.tan(np.pi * (np.random.default_rng(0).uniform(0, 1, 200000) - 0.5))
        coh = np.cos(2 * np.pi * f * c / Uc * eta).mean()
        self.assertAlmostEqual(coh, np.exp(-C * f * eta / Uc), places=2)

    def test_js_mirror_agrees(self):
        if not shutil.which("node"):
            self.skipTest("node not installed")
        w = Wind(force=4, from_deg=225, canopy_h=20, seed=7)
        j = dict(w.to_json(), constants=constants())
        pts = [(3.0, -40.0, 1.5), (120.0, 64.0, 37.25), (-5.0, 9.0, 600.0)]
        js = (f"const W = require('./viewer/wind.js'); W.init({json.dumps(j)});"
              f"console.log(JSON.stringify({json.dumps(pts)}.map(([x,y,t]) => W.gust(x,y,t).concat(W.at(x,y,12,t,0.5)))));")
        out = json.loads(subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True, text=True, check=True).stdout)
        for (x, y, t), o in zip(pts, out):
            self.assertLess(np.abs(np.r_[w.gust(x, y, t), w.at(x, y, 12, t, 0.5)] - o).max(), 1e-9)

    def test_constants_are_sourced_or_design(self):
        src = json.load(open(os.path.join(ROOT, "catalog", "wind_sources.json"), encoding="utf-8"))["constants"]
        for k in list(constants()) + ["WOOD", "LEAF_FRACTION", "ZETA_LEAFY", "ZETA_BARE", "CD_20", "SIGMA_U"]:
            if k in ("U_REF", "D_MAX", "L_MAX", "F1_MAX", "F2_MAX"):  # quantisation and reference choices
                continue
            e = src[k]
            self.assertTrue(e.get("design") or (e["url"].startswith("https://") and e["quote"]), k)


class TreeResponse(unittest.TestCase):
    def test_transfer_function(self):
        g, psi = transfer([1e-4, 0.5], 0.5, 0.086)
        self.assertAlmostEqual(g[0], 1.0, places=6)
        self.assertAlmostEqual(g[1], 1 / (2 * 0.086), places=6)
        self.assertAlmostEqual(psi[1], np.pi / 2, places=6)

    def test_drag_streamlines_smoothly(self):
        self.assertAlmostEqual(float(drag(20.0, 1.0) / (0.5 * 1.2 * 400)), 0.185, places=6)  # Vollsinger at 20 m/s
        U = np.geomspace(0.1, 30, 2000)
        b = drag_slope(U)
        self.assertTrue(np.all(np.diff(b) < 0) and b[0] < 2 and b[-1] > 1)
        num = np.gradient(np.log(drag(U, 1.0)), np.log(U))
        self.assertLess(np.abs(num[2:-2] - b[2:-2]).max(), 1e-3)

    def test_frequencies_and_leaf_effect(self):
        ratios = []
        for k in ("white_oak", "loblolly_pine", "tulip_poplar", "flowering_dogwood", "water_oak"):
            tm = generate_tree(k, seed=(0, 1), detail="low")
            tw, nd = mechanics(tm)
            self.assertTrue(0.15 < tw.f0 < 2.0, (k, tw.f0))
            self.assertTrue(0 < tw.Q_ref < 1.5, (k, tw.Q_ref))
            limbs = nd["limb"] >= 0
            self.assertTrue(np.all(nd["f1"][limbs] > 0))
            if tm.species.deciduous:
                bare, _ = mechanics(generate_tree(k, seed=(0, 1), detail="low", season="winter"), "winter")
                self.assertLess(bare.zeta, tw.zeta)
                ratios.append(bare.f0 / tw.f0)
        self.assertTrue(1.06 < np.mean(ratios) < 1.30, ratios)  # Jackson et al. 2019: 1.18 ± 0.12

    def test_attributes_round_trip(self):
        n = 50
        r = np.random.default_rng(0)
        ax = r.normal(size=(n, 3))
        ax /= np.linalg.norm(ax, axis=1, keepdims=True)
        v = dict(phi=r.uniform(0, 1, n), d1=r.uniform(0, 0.9, n), d2=r.uniform(0, 0.5, n), lever=r.uniform(0, 0.5, n),
                 axis=ax, ph1=r.uniform(0, 1, n), f1=r.uniform(0.2, 7, n), f2=r.uniform(0.4, 15, n),
                 ph2=r.uniform(0, 1, n), phl=r.uniform(0, 1, n))
        u = unpack(pack(**v))
        for k in v:
            tol = 0.02 if k in ("axis", "ph1") else 0.035 if k in ("f1", "f2") else 0.01
            self.assertLess(np.abs(u[k] - v[k]).max(), tol, k)

    def test_sway_grows_with_force_and_base_stays(self):
        tm = generate_tree("white_oak", seed=(0, 1), detail="low")
        tw, at = tree_attributes(tm)
        A = unpack(at["bark"])
        P = tm.bark.positions.astype(float)
        inst = dict(x=5.0, y=5.0, yaw=0.4, scale=1.0, f0=tw.f0, zeta=tw.zeta, Q=tw.Q_ref, shelter=1.0)
        amp = []
        for F in (2, 5, 8):
            w = Wind(force=F, canopy_h=tw.H, seed=0)
            d = np.stack([sway.displace(w, inst, P, A, tm.bark.normals(), t) for t in (3.0, 7.0, 11.0)])
            base = P[:, 2] < 0.3
            self.assertLess(np.abs(d[:, base]).max(), 1e-3)
            amp.append(np.abs(d).max())
        self.assertTrue(amp[0] < amp[1] < amp[2], amp)


class WindScene(unittest.TestCase):
    def test_planner_reads_wind(self):
        p = plan("a windy fall morning in a hardwood hollow")
        self.assertEqual((p.wind_force, p.wind_from), (6.0, 45.0))
        p = plan("calm bayou at dusk with a north wind")
        self.assertEqual((p.wind_force, p.wind_from), (1.0, 0.0))
        self.assertEqual(plan("gale from the southwest").wind_from, 225.0)

    def test_glb_carries_custom_attributes(self):
        import struct
        import tempfile
        m = Mesh(np.array([[0, 0, 0], [1, 0, 0], [0, 1, 1]], np.float32), np.ones((3, 3), np.float32),
                 np.array([[0, 1, 2]], np.uint32))
        m.attrs = {"_WIND0": np.full((3, 4), 200, np.uint8), "_WIND1": np.full((3, 4), -5, np.int8)}
        g = GLB()
        g.node("x", g.mesh(m, "x", g.material("m")))
        with tempfile.TemporaryDirectory() as d:
            path = g.save(os.path.join(d, "a.glb"))
            b = open(path, "rb").read()
        n = struct.unpack("<I", b[12:16])[0]
        doc = json.loads(b[20:20 + n])
        at = doc["meshes"][0]["primitives"][0]["attributes"]
        self.assertEqual(doc["accessors"][at["_WIND0"]]["componentType"], 5121)
        self.assertEqual(doc["accessors"][at["_WIND1"]]["componentType"], 5120)
        self.assertTrue(doc["accessors"][at["_WIND1"]]["normalized"])


if __name__ == "__main__":
    unittest.main()

import json
import os
import shutil
import subprocess
import unittest

import numpy as np

from plandscape.fauna import perception as P

ROOT = os.path.join(os.path.dirname(__file__), "..")


class Senses(unittest.TestCase):
    def test_sight_falls_with_distance_cover_and_stillness(self):
        a = P.sight("white_tailed_deer", 20, 0.0, P.WALK)
        self.assertGreater(a, P.sight("white_tailed_deer", 60, 0.0, P.WALK))
        self.assertGreater(a, P.sight("white_tailed_deer", 20, 0.0, P.WALK, cover_tau=1.0))
        self.assertGreater(a, P.sight("white_tailed_deer", 20, 0.0, 0.0, "crouch"))
        self.assertGreater(a, P.sight("white_tailed_deer", 20, np.pi, P.WALK))          # behind it
        self.assertGreater(P.sight("wild_turkey", 60, 0.0, P.WALK), P.sight("white_tailed_deer", 60, 0.0, P.WALK))
        self.assertLess(P.sight("armadillo", 10, 0.0, P.WALK), 0.05)                     # "very poor eyesight"
        self.assertGreater(P.sight("white_tailed_deer", 40, 0.0, P.WALK, intensity=0.2),
                           P.sight("wild_turkey", 40, 0.0, P.WALK, intensity=0.2) / 3.5)  # twilight eyes

    def test_spreading_and_wind_masking(self):
        self.assertAlmostEqual(P.level(80, 2) - P.level(80, 4), 20 * np.log10(2), places=9)  # 6 dB per doubling
        self.assertAlmostEqual(P.wind_noise(5.1), 55.2, places=6)
        L = P.STEP_DB["walk"] + P.GROUND_DB["litter"]
        calm = [P.hearing("white_tailed_deer", L, d, 0, 0.3) for d in (10, 25)]
        windy = [P.hearing("white_tailed_deer", L, d, 0, 3.0) for d in (10, 25)]
        self.assertTrue(calm[1] > 0.5 and windy[0] == 0.0)   # when the wind blows you can move

    def test_plume_only_downwind_and_spreads(self):
        self.assertEqual(P.smell("white_tailed_deer", -30, 0, 2), 0.0)
        self.assertAlmostEqual(P.smell("white_tailed_deer", 100, 0, 2), P.SMELL_MAX)
        self.assertLess(P.smell("white_tailed_deer", 100, 40, 2), 0.05)
        sy, sz = P.sigmas(1000)
        self.assertAlmostEqual(sy - P.SOURCE_SIGMA, 0.08 * 1000 / np.sqrt(1.1), places=9)   # Briggs class D
        self.assertAlmostEqual(sz - P.SOURCE_SIGMA, 0.06 * 1000 / np.sqrt(2.5), places=9)
        self.assertEqual(P.smell("great_blue_heron", 20, 0, 2), 0.0)

    def test_fid_speed_directness_experience(self):
        base = P.fid("white_tailed_deer", P.WALK, 1.0)
        self.assertAlmostEqual(base, P.SENSES["white_tailed_deer"]["fid"])
        self.assertGreater(P.fid("white_tailed_deer", 3.5, 1.0), base)
        self.assertLess(P.fid("white_tailed_deer", P.WALK, 0.0), base)
        self.assertLess(P.fid("white_tailed_deer", P.WALK, 1.0, habit=1.0), base)
        self.assertGreater(P.fid("white_tailed_deer", P.WALK, 1.0, sens=1.0), base)
        self.assertAlmostEqual(P.SENSES["gray_squirrel"]["fid"], 9.2)   # Eason et al. 2019

    def test_mind_alert_flee_calm_and_learning(self):
        m = P.Mind("white_tailed_deer")
        for _ in range(30):
            m.step(0.1, 0.5, 60, 45)
        self.assertEqual(m.state, "alert")
        m.step(0.1, 0.5, 40, 45)
        self.assertEqual(m.state, "flee")
        for _ in range(1200):
            m.step(0.1, 0.0, 200, 45)
        self.assertEqual(m.state, "calm")
        q = P.Mind("white_tailed_deer")
        for _ in range(30):
            q.step(0.1, 0.4, 100, 45)
        for _ in range(600):
            q.step(0.1, 0.0, 100, 45)
        self.assertGreater(q.habit, 0)          # a look that came to nothing
        q.startle(1.0)
        self.assertGreater(q.sens, 0)
        h0 = q.habit
        q.fed()
        self.assertGreater(q.habit, h0)

    def test_scent_alone_alerts_but_does_not_stampede(self):
        m = P.Mind("white_tailed_deer")
        for _ in range(600):
            m.step(0.1, P.smell("white_tailed_deer", 120, 0, 2), 120, 45)
        self.assertEqual(m.state, "alert")

    def test_js_mirror_agrees(self):
        if not shutil.which("node"):
            self.skipTest("node not installed")
        cases = [["sight", "white_tailed_deer", 33.0, 0.4, 1.0, "crouch", 0.5, 0.7],
                 ["hearing", "wild_turkey", 61.0, 18.0, 9.0, 1.3],
                 ["smell", "coyote", 80.0, 6.0, 2.2],
                 ["fid", "great_blue_heron", 2.0, 0.6, 0.3, 0.9],
                 ["windNoise", 1.7], ["twoBone", 0.1, -0.8, 0.45, 0.45, 1], ["footPath", 0.7, 0.65, 0.5, 0.9, 0.12]]
        js = (f"const L = require('./viewer/life.js'); L.init({json.dumps(P.to_json())});"
              f"console.log(JSON.stringify({json.dumps(cases)}.map(([f, ...a]) => L[f](...a))));")
        out = json.loads(subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True, text=True, check=True).stdout)
        from plandscape.fauna import gait
        py = [P.sight("white_tailed_deer", 33.0, 0.4, 1.0, "crouch", 0.5, 0.7),
              P.hearing("wild_turkey", 61.0, 18.0, 9.0, 1.3), P.smell("coyote", 80.0, 6.0, 2.2),
              P.fid("great_blue_heron", 2.0, 0.6, 0.3, 0.9), P.wind_noise(1.7),
              list(gait.two_bone(0.1, -0.8, 0.45, 0.45, 1)), [float(v) for v in gait.foot_path(0.7, 0.65, 0.5, 0.9, 0.12)]]
        self.assertLess(np.abs(np.hstack([np.ravel(v) for v in py]) - np.hstack([np.ravel(v) for v in out])).max(), 1e-9)
        # the Mind state machine too
        steps = [[0.1, 0.5, 60, 45]] * 30 + [[0.1, 0.5, 40, 45]] + [[0.1, 0.0, 200, 45]] * 900
        js = (f"const L = require('./viewer/life.js'); L.init({json.dumps(P.to_json())}); const m = new L.Mind('white_tailed_deer');"
              f"const s = {json.dumps(steps)}.map(([a, b, c, d]) => {{ m.step(a, b, c, d); return [m.alarm, m.state]; }});"
              "console.log(JSON.stringify(s));")
        out = json.loads(subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True, text=True, check=True).stdout)
        m = P.Mind("white_tailed_deer")
        for (a, b, c, d), (al, st) in zip(steps, out):
            m.step(a, b, c, d)
            self.assertAlmostEqual(m.alarm, al, places=9)
            self.assertEqual(m.state, st)

    def test_values_are_sourced_or_design(self):
        with open(os.path.join(ROOT, "catalog", "perception_sources.json"), encoding="utf-8") as f:
            src = json.load(f)
        for sp in P.SENSES:
            e = src["fid"][sp]
            self.assertTrue(e.get("design") or (e["url"].startswith("https://") and e["quote"]), sp)
        for group in ("approach", "alarm", "senses", "sound", "plume", "habituation", "food", "people"):
            for k, e in src[group].items():
                self.assertTrue(e.get("design") or (e["url"].startswith("https://") and e["quote"]), (group, k))


class WorldExport(unittest.TestCase):
    def test_world_bin_round_trip(self):
        import tempfile
        from plandscape.scene.compose import write_world
        from plandscape.terrain.heightfield import Heightfield
        z = np.random.default_rng(0).normal(size=(5, 7)).astype(np.float32)
        hf = Heightfield(z=z, res=1.0, origin=(2.0, 3.0))
        lay = {"canopy": np.linspace(0, 1, 35).reshape(5, 7)}
        with tempfile.TemporaryDirectory() as d:
            meta = write_world(os.path.join(d, "w.bin"), hf, lay)
            with open(os.path.join(d, "w.bin"), "rb") as f:
                b = f.read()
        zz = np.frombuffer(b, np.float32, 35, meta["layers"]["z"]["offset"]).reshape(5, 7)
        cc = np.frombuffer(b, np.uint8, 35, meta["layers"]["canopy"]["offset"]).reshape(5, 7) / 255
        self.assertTrue(np.array_equal(zz, z))
        self.assertLess(np.abs(cc - lay["canopy"]).max(), 1 / 255)
        self.assertEqual(meta["shape"], [5, 7])


if __name__ == "__main__":
    unittest.main()

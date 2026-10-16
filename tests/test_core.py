import os
import shutil
import tempfile
import unittest

import numpy as np

from plandscape.assets.store import AssetStore, tree_codec
from plandscape.export.validate import validate_glb
from plandscape.fauna.agents import World, run, spawn
from plandscape.flora.species import SPECIES
from plandscape.flora.tree import generate_tree
from plandscape.paths.desire import obstacle_cost, simulate
from plandscape.scene.compose import compose
from plandscape.scene.planner import plan
from plandscape.sources.harvest import detect_license
from plandscape.terrain.heightfield import PROVINCES, generate_tile


class SpeciesSources(unittest.TestCase):
    def test_verified_species_agree_with_their_sources(self):
        import json
        root = os.path.join(os.path.dirname(__file__), "..")
        src = json.load(open(os.path.join(root, "catalog", "species_sources.json"), encoding="utf-8"))["species"]
        for k, sp in SPECIES.items():
            if not sp.verified:
                continue
            s = src[k]
            for f in ("height", "dbh", "leaf_size", "habit"):
                self.assertTrue(s[f]["url"].startswith("https://") and s[f]["quote"], (k, f))
            for f in ("height", "dbh"):
                lo, hi = s[f]["value"]
                v = getattr(sp, f)
                self.assertTrue(lo - 1e-6 <= v[0] <= v[1] <= hi + 1e-6, (k, f, v, (lo, hi)))
            lo, hi = s["leaf_size"]["value"]
            self.assertTrue(lo - 1e-6 <= sp.leaf_size <= hi + 1e-6, (k, sp.leaf_size, (lo, hi)))
            self.assertEqual(sp.deciduous, "deciduous" in s["habit"]["value"], k)


class Gaits(unittest.TestCase):
    def test_stride_gait_and_phase_keys(self):
        from plandscape.fauna import gait
        h = 0.95  # deer hip height
        self.assertAlmostEqual(float(gait.stride(1.0, h)), 2.3 * h * (1.0 / (9.81 * h)) ** 0.3, places=6)
        self.assertEqual([gait.gait_name(float(gait.froude(v, h))) for v in (1.0, 3.0, 8.0)], ["walk", "trot", "gallop"])
        # 20 s at rest, then 20 s walking east at 1 m/s, then rest again
        t = np.arange(0, 60, 0.25)
        x = np.clip(t - 20, 0, 20)
        tk, ang, names = gait.leg_angles(t, np.c_[x, 0 * x], h, "quad")
        lam = float(gait.stride(1.0, h))
        strides = 20 / lam
        self.assertLess(abs(len(tk) - gait.KEYS_PER_STRIDE * strides), 12)  # keys follow distance, not time
        rest = (tk < 19.9) | (tk > 40.1)
        self.assertTrue(np.allclose(ang[rest], 0))  # legs hang still at rest
        moving = ang[(tk > 21) & (tk < 39)]
        self.assertGreater(np.abs(moving).max(), np.radians(10))
        # lateral-sequence walk: left fore leads left hind by a quarter stride
        self.assertLess(np.corrcoef(moving[:, 0], moving[:, 2])[0, 1], 0.5)

    def test_rig_matches_body(self):
        from plandscape.fauna.bodies import body, rig
        for k in ("white_tailed_deer", "wild_turkey", "human", "gray_squirrel"):
            r = rig(k, (0.5, 0.4, 0.3))
            b = body(k, (0.5, 0.4, 0.3))
            self.assertEqual(b.n_tris, r["torso"].n_tris + sum(m.n_tris for m, _ in r["legs"]))
            self.assertAlmostEqual(float(b.positions[:, 2].min()), 0.0 if r["legs"] else float(b.positions[:, 2].min()))
            for m, hip in r["legs"]:  # hip at the leg's origin, foot on the ground
                self.assertAlmostEqual(float(m.positions[:, 2].max()), 0.0, places=5)
                self.assertAlmostEqual(float(m.positions[:, 2].min()) + hip[2], 0.0, places=5)


class Determinism(unittest.TestCase):
    def test_terrain_same_seed_same_world(self):
        a = generate_tile(64, 1.0, "piedmont", 7)
        b = generate_tile(64, 1.0, "piedmont", 7)
        c = generate_tile(64, 1.0, "piedmont", 8)
        np.testing.assert_array_equal(a.z, b.z)
        self.assertFalse(np.allclose(a.z, c.z))

    def test_tree_same_seed_same_tree(self):
        a = generate_tree("water_oak", seed=3)
        b = generate_tree("water_oak", seed=3)
        c = generate_tree("water_oak", seed=4)
        np.testing.assert_array_equal(a.bark.positions, b.bark.positions)
        np.testing.assert_array_equal(a.foliage.colors, b.foliage.colors)
        self.assertNotEqual(a.bark.positions.shape, c.bark.positions.shape)


class Generators(unittest.TestCase):
    def test_every_species_builds(self):
        for k in SPECIES:
            for season in ("summer", "winter"):
                # dry site so evergreen Spanish moss (correctly kept in winter) doesn't count as leaves
                t = generate_tree(k, seed=1, season=season, moisture=0.1)
                self.assertGreater(t.bark.n_tris, 0, k)
                self.assertTrue(np.isfinite(t.bark.positions).all(), k)
                if season == "winter" and SPECIES[k].deciduous and SPECIES[k].leaf != "palm":
                    self.assertLess(t.foliage.n_tris, 2000, f"{k} should be bare in winter")

    def test_every_province_builds(self):
        for p in PROVINCES:
            hf = generate_tile(48, 1.0, p, 2)
            self.assertTrue(np.isfinite(hf.z).all(), p)
            self.assertEqual(hf.layers["moisture"].shape, hf.z.shape)

    def test_desire_paths_emerge(self):
        hf = generate_tile(64, 1.0, "piedmont", 3, creek=False)
        f, _ = simulate(hf, [(5, 5, 1), (58, 10, 1), (30, 58, 1)], n_trips=96, seed=1, cost=obstacle_cost(hf))
        self.assertGreater(int((f.G > 0.3).sum()), 20)


class Fauna(unittest.TestCase):
    def test_animals_stay_in_world_and_vary_behaviour(self):
        hf = generate_tile(64, 1.0, "piedmont", 5)
        f, _ = simulate(hf, [(5, 5, 1), (58, 58, 1)], n_trips=24, seed=1)
        z = np.zeros_like(hf.z)
        w = World(hf, f, obstacle_cost(hf), z + 0.4, z + 0.5, z + 0.2, np.array([[30.0, 30.0, 15.0, 0.3]]))
        ags = spawn(w, {"white_tailed_deer": 3, "gray_squirrel": 2, "human": 1}, seed=2)
        run(w, ags, seconds=60, dt=0.25)
        for a in ags:
            xy = np.array([(l[1], l[2]) for l in a.log])
            self.assertTrue((xy >= 0).all() and (xy <= 64).all())
        states = {l[5] for a in ags for l in a.log}
        self.assertGreaterEqual(len(states), 3)


class Planner(unittest.TestCase):
    def test_places_and_counts(self):
        p = plan("Monte Sano cove, a dogtrot, two deer and a turkey flock at dusk in fall")
        self.assertEqual(p.province, "cumberland_plateau")
        self.assertEqual(p.season, "fall")
        self.assertEqual(p.fauna["white_tailed_deer"], 2)
        self.assertGreaterEqual(p.fauna["wild_turkey"], 3)
        self.assertEqual(plan("a shotgun house in the delta").buildings, ["shotgun"])


class Assets(unittest.TestCase):
    def test_store_roundtrip_and_hit(self):
        d = tempfile.mkdtemp()
        try:
            s = AssetStore(d)
            enc, dec = tree_codec()
            params = dict(species="eastern_redbud", seed=[0, 1], season="spring", detail="low", moisture=0.5)
            build = lambda: generate_tree("eastern_redbud", seed=(0, 1), season="spring", detail="low")
            a = s.get_or_build("tree", params, build, enc, dec)
            b = AssetStore(d).get_or_build("tree", params, lambda: self.fail("should hit the library"), enc, dec)
            np.testing.assert_allclose(a.bark.positions, b.bark.positions)
            self.assertEqual(len(s.find("tree", species="eastern_redbud")), 1)
        finally:
            shutil.rmtree(d)


class EndToEnd(unittest.TestCase):
    def test_prompt_to_valid_glb(self):
        d = tempfile.mkdtemp()
        try:
            p = plan("longleaf savanna near Mobile with a barn and deer", size_m=64)
            res = compose(p, d, sim_seconds=20, log=lambda *a: None, store=AssetStore(os.path.join(d, "lib")))
            self.assertEqual(validate_glb(res["glb"]), [])
            self.assertLess(os.path.getsize(res["glb"]), 15e6)
            self.assertTrue(os.path.exists(os.path.join(d, "scene.json")))
        finally:
            shutil.rmtree(d)


class Licenses(unittest.TestCase):
    def test_detector(self):
        self.assertEqual(detect_license("Permission is hereby granted, free of charge, to any person"), "MIT")
        self.assertEqual(detect_license("Licensed under the Apache License, Version 2.0 (the"), "Apache-2.0")
        self.assertEqual(detect_license("Creative Commons Attribution-NonCommercial 4.0"), "CC-BY-NC-4.0")


if __name__ == "__main__":
    unittest.main()

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
        from plandscape.fauna import gait
        from plandscape.fauna.bodies import body, rig
        for k in ("white_tailed_deer", "wild_turkey", "human", "gray_squirrel"):
            r = rig(k, (0.5, 0.4, 0.3))
            b = body(k, (0.5, 0.4, 0.3))
            neck = sum(r[k]["mesh"].n_tris for k in ("neck", "tail") if r[k])
            self.assertEqual(b.n_tris, r["torso"].n_tris + neck + sum(lg["thigh"].n_tris + lg["shank"].n_tris
                                                                      for lg in r["legs"]))
            for lg in r["legs"]:  # rest pose puts the foot on the ground, slightly flexed
                th1, th2 = gait.rest_pose(r["hip"], lg["l1"], lg["l2"], lg["knee"])
                foot_z = -lg["l1"] * np.cos(th1) - lg["l2"] * np.cos(th1 + th2)
                self.assertAlmostEqual(foot_z, -r["hip"], places=4)
                self.assertGreater(abs(th2), np.radians(10))

    def test_ik_plants_feet_in_stance(self):
        from plandscape.fauna import gait
        h, l1, l2 = 0.95, 0.5, 0.5
        for knee in (1.0, -1.0):
            psi = np.linspace(0, 0.6, 13)  # stance (β = 0.65)
            x, z = gait.foot_path(psi, 0.65, 0.6, h, 0.12)
            np.testing.assert_allclose(z, -h)
            th1, th2 = gait.two_bone(x, z, l1, l2, knee)
            fx = l1 * np.sin(th1) + l2 * np.sin(th1 + th2)
            fz = -l1 * np.cos(th1) - l2 * np.cos(th1 + th2)
            np.testing.assert_allclose(fx, x, atol=1e-6)
            np.testing.assert_allclose(fz, z, atol=1e-6)
            kx = l1 * np.sin(th1)  # the knee sits on its anatomical side of the hip-foot line
            self.assertTrue(np.all(np.sign(kx - x / 2) == knee))
        x, z = gait.foot_path(np.linspace(0.7, 0.95, 6), 0.65, 0.6, h, 0.12)
        self.assertTrue(np.all(z > -h))  # swing feet are lifted


class Behaviour(unittest.TestCase):
    def test_head_track_and_bob_keep_feet_down(self):
        from plandscape.fauna import gait
        t = np.arange(0, 10, 0.25)
        states = ["travel"] * 10 + ["eat"] * 10 + ["eat"] * 10 + ["alert"] * 10
        tk, hv = gait.head_track(t, states, np.radians(110))
        self.assertTrue(np.all(np.diff(tk) > 0))
        self.assertAlmostEqual(float(np.interp(5.0, tk, hv)), np.radians(110))  # grazing: head down
        self.assertLess(float(hv[-1]), 0)  # alert: head up
        # moving with bob: the IK still lands stance feet on the ground
        x = 1.5 * t
        bob = []
        tk2, ang, names = gait.leg_ik(t, np.c_[x, 0 * x], 0.95, [-1.0, -1.0, 1.0, 1.0], "quad", seg=(0.5, 0.5), bob=bob)
        bob = np.asarray(bob)
        self.assertEqual(len(bob), len(tk2))
        self.assertGreater(np.abs(bob).max(), 0.005)
        th1, th2 = ang[:, 2, 0], ang[:, 2, 1]
        fz = -0.5 * np.cos(th1) - 0.5 * np.cos(th1 + th2) + bob  # foot height above the ground (hip at h + b)
        self.assertGreater(np.isclose(fz, -0.95, atol=1e-4).mean(), 0.4)  # in stance about half the time
        self.assertTrue(np.all(fz >= -0.95 - 1e-4))  # never below the ground


class LyingAndFlag(unittest.TestCase):
    def test_rest_folds_legs_and_flee_raises_the_flag(self):
        from plandscape.fauna import gait
        from plandscape.fauna.bodies import rig
        r = rig("white_tailed_deer", (0.5, 0.4, 0.3))
        h = r["hip"]
        t = np.arange(0, 20, 0.25)
        states = ["idle"] * 20 + ["rest"] * 40 + ["flee"] * 20
        x = np.where(t >= 15, (t - 15) * 8.0, 0.0)  # lies down, then bolts
        drop = gait.pose_track(t, states, r["lie"] * h, gait.LIE, gait.LIE_EASE)
        bob = []
        lg = r["legs"][2]
        tk, ang, _ = gait.leg_ik(t, np.c_[x, 0 * x], h, [l_["knee"] for l_ in r["legs"]], "quad",
                                 seg=(lg["l1"], lg["l2"]), bob=bob, drop=drop)
        bob = np.asarray(bob)
        lying = (tk > 5.99) & (tk < 14.9)  # fully down from 6 s (5 s + 1 s ease) until it bolts at 15 s
        self.assertGreater(lying.sum(), 0)
        self.assertTrue(np.allclose(bob[lying], -r["lie"] * h))  # trunk lowered 62 % of hip height
        th1, th2 = ang[lying, 2, 0], ang[lying, 2, 1]
        foot = -lg["l1"] * np.cos(th1) - lg["l2"] * np.cos(th1 + th2) + bob[lying]
        np.testing.assert_allclose(foot, -h, atol=1e-4)  # folded legs still reach the ground
        self.assertGreater(np.degrees(np.abs(th2)).min(), 90)  # sharply folded
        fk, fv = gait.pose_track(t, states, r["tail"]["flag"], gait.TAIL, gait.TAIL_EASE)
        self.assertAlmostEqual(float(fv[-1]), r["tail"]["flag"])  # fleeing: flag up
        self.assertAlmostEqual(float(np.interp(10, fk, fv)), 0.0)


class Refine(unittest.TestCase):
    def test_validate_keeps_only_what_generators_honour(self):
        from plandscape.scene.planner import refine
        good = {"province": "coastal_plain", "biome": "pine_savanna", "trees": {"longleaf_pine": 3, "live_oak": 1},
                "fauna": {"wild_turkey": 4}, "hour": 6.5, "season": "spring", "buildings": ["church"],
                "seed": 999, "detail": "cm"}
        p = refine("a church in the longleaf at dawn", lambda prompt, schema: good)
        self.assertEqual((p.province, p.biome, p.season, p.hour), ("coastal_plain", "pine_savanna", "spring", 6.5))
        self.assertAlmostEqual(p.trees["longleaf_pine"], 0.75)
        self.assertEqual(p.fauna, {"wild_turkey": 4})
        base = plan("a church in the longleaf at dawn")
        self.assertEqual((p.seed, p.detail), (base.seed, base.detail))  # never from the LLM
        bad = {"province": "Narnia", "trees": {"baobab": 1}, "fauna": {"wild_turkey": 500}, "hour": True,
               "season": ["fall"], "buildings": ["castle"], "tree_density": 3, "color": "blue"}
        q = refine("a quiet hollow", lambda prompt, schema: bad)
        base = plan("a quiet hollow")
        for k in ("province", "trees", "fauna", "hour", "season", "buildings", "tree_density"):
            self.assertEqual(getattr(q, k), getattr(base, k), k)
        self.assertEqual(sum("kept planner value" in n for n in q.notes), 7)
        self.assertTrue(any("unknown field color" in n for n in q.notes))

    def test_failures_fall_back_and_client_parses(self):
        import json
        from unittest import mock
        from plandscape.scene import planner
        def boom(prompt, schema):
            raise OSError("offline")
        p = planner.refine("a quiet hollow", boom)
        self.assertTrue(any("LLM unavailable (OSError)" in n for n in p.notes))
        self.assertEqual(planner.extract_json('Sure! {"season": "fall", "x": {"a": 1}} done'),
                         {"season": "fall", "x": {"a": 1}})
        self.assertIsNone(planner.extract_json("no json here"))
        reply = json.dumps({"content": [{"type": "text", "text": 'Plan: {"season": "winter", "hour": 7}'}]}).encode()

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return reply
        with mock.patch("urllib.request.urlopen", return_value=R()) as u:
            q = planner.refine("a cold morning in the cove", planner.claude_llm(api_key="test", model="m"))
            req = u.call_args[0][0]
            self.assertEqual(req.full_url, "https://api.anthropic.com/v1/messages")
            self.assertEqual(json.loads(req.data)["model"], "m")
        self.assertEqual((q.season, q.hour), ("winter", 7.0))


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

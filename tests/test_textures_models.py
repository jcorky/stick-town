"""UVs, textures, GLB images, the glTF importer and decimation. No network: downloads are
blocked in setUp, so textures come from the library or fall back to procedural ones."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import numpy as np

from plandscape import models, textures
from plandscape.assets.store import AssetStore, tree_codec
from plandscape.export.gltf import GLB
from plandscape.export.validate import validate_glb
from plandscape.flora.tree import generate_tree
from plandscape.mesh import SOLID_UV, Mesh, MeshBuilder
from plandscape.render import render


def _sphere(n=24):
    th, ph = np.meshgrid(np.linspace(0, np.pi, n), np.linspace(0, 2 * np.pi, 2 * n, endpoint=False), indexing="ij")
    P = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1).reshape(-1, 3)
    UV = np.stack([ph / (2 * np.pi), th / np.pi], -1).reshape(-1, 2)
    m = 2 * n
    I = []
    for i in range(n - 1):
        for j in range(m):
            a, b = i * m + j, i * m + (j + 1) % m
            I += [(a, b, a + m), (b, b + m, a + m)]
    return P, UV.astype(np.float32), np.array(I)


def _offline(*_a, **_k):
    raise OSError("network disabled in tests")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = AssetStore(self.tmp)
        self.net = mock.patch("plandscape.sources.sites._get", _offline)
        self.net.start()
        self.dl = mock.patch("plandscape.sources.sites.DOWNLOADS", os.path.join(self.tmp, "dl"))
        self.dl.start()
        # generators that call AssetStore() without a store must not touch the real library
        self.root = mock.patch("plandscape.assets.store.DEFAULT_ROOT", os.path.join(self.tmp, "lib"))
        self.root.start()
        self.reg = dict(textures._REGISTRY)
        textures._REGISTRY.clear()

    def tearDown(self):
        self.net.stop()
        self.dl.stop()
        self.root.stop()
        textures._REGISTRY.clear()
        textures._REGISTRY.update(self.reg)
        shutil.rmtree(self.tmp)


class Textures(Base):
    def test_fallbacks_are_never_cached(self):
        textures.get("bark/Bark012", self.store)
        self.assertEqual(self.store.find("texture"), [])

    def test_offline_fallback_and_solid_patch(self):
        for key in ("leaf/LeafSet016", "needle/PineNeedles001", "bark/Bark012", "ground/Ground078"):
            t = textures.get(key, self.store)
            self.assertEqual(t.key, key)
            self.assertIn("fallback", t.meta)  # network blocked → procedural, and recorded as such
            px = t.sample(np.array([SOLID_UV[0]]), np.array([SOLID_UV[1]]))[0]
            self.assertGreater(px[3], 0.99)  # untextured parts of a textured mesh stay visible
            if t.alpha:
                u0, v0, u1, v1, cov = textures.card_box(key, self.store)
                self.assertGreaterEqual(v0, 0.125)  # card crop never includes the solid patch (rows < 1/8)
                self.assertGreater(cov, 0.05)

    def test_builder_fills_solid_uv_and_merge_drops_mixed(self):
        mb = MeshBuilder("leaf/procedural")
        mb.add([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [0.2, 0.5, 0.1], [[0, 1, 2]], [[0.2, 1], [0.8, 1], [0.5, 0.2]])
        mb.add([[0, 0, 1], [1, 0, 1], [0, 1, 1]], [0.9, 0.9, 0.9], [[0, 1, 2]])  # e.g. a flower
        m = mb.build()
        np.testing.assert_allclose(m.uvs[3:], np.tile(SOLID_UV, (3, 1)), atol=1e-6)
        plain = Mesh(m.positions[:3], m.colors[:3], np.array([[0, 1, 2]], np.uint32))
        self.assertIsNone(Mesh.merge([m, plain]).uvs)
        self.assertEqual(Mesh.merge([m, m]).texture, "leaf/procedural")

    def test_tree_cache_keeps_uvs(self):  # regression: library hits used to drop UVs → solid green quads
        tm = generate_tree("white_oak", seed=1, detail="low")
        self.assertEqual(tm.foliage.texture, textures.leaf_key("white_oak"))
        self.assertIsNotNone(tm.bark.uvs)
        enc, dec = tree_codec()
        self.store.put("tree", {"t": 1}, *enc(tm)[:2])
        a, e = self.store.get("tree", {"t": 1})
        back = dec(a, e.meta)
        np.testing.assert_allclose(back.foliage.uvs, tm.foliage.uvs)
        self.assertEqual(back.foliage.texture, tm.foliage.texture)
        self.assertEqual(back.bark.texture, tm.bark.texture)

    def test_glb_embeds_textures_and_tints(self):
        tm = generate_tree("loblolly_pine", seed=2, detail="low")
        g = GLB()
        tex = textures.get(tm.foliage.texture, self.store)
        mi = g.material("foliage:x", double=True, texture=tex)
        g.node("f", g.mesh(tm.foliage, "f", mi))
        bt = textures.get(tm.bark.texture, self.store)
        g.node("b", g.mesh(tm.bark, "b", g.material("bark:x", texture=bt)))
        path = os.path.join(self.tmp, "t.glb")
        g.save(path)
        self.assertEqual(validate_glb(path), [])
        self.assertEqual(len(g.images), 2)
        self.assertEqual(g.materials[0]["alphaMode"], "MASK")
        acc = g.meshes[0]["primitives"][0]["attributes"]
        self.assertIn("TEXCOORD_0", acc)
        self.assertEqual(g.accessors[acc["TEXCOORD_0"]]["componentType"], 5123)  # quantised 0..1 card UVs

    def test_preview_alpha_test(self):
        # one alpha card over the sky: textured render must show fewer leaf pixels than the solid quad
        t = textures.get("leaf/procedural", self.store)
        u0, v0, u1, v1, _ = textures.card_box("leaf/procedural", self.store)
        P = np.array([[0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 0, 1]], np.float32)
        uv = np.array([[u0, v1], [u1, v1], [u1, v0], [u0, v0]], np.float32)
        I = np.array([[0, 1, 2], [0, 2, 3]], np.uint32)
        C = np.tile([0.1, 0.6, 0.1], (4, 1)).astype(np.float32)
        from PIL import Image
        a, b = os.path.join(self.tmp, "a.png"), os.path.join(self.tmp, "b.png")
        render([Mesh(P, C, I, uv, t.key)], a, size=(120, 120), azimuth=0, elevation=0)
        render([Mesh(P, C, I)], b, size=(120, 120), azimuth=0, elevation=0)
        green = [(np.asarray(Image.open(p))[..., 1] > np.asarray(Image.open(p))[..., 0] + 40).sum() for p in (a, b)]
        self.assertLess(green[0], green[1] * 0.85)
        self.assertGreater(green[0], 0)


class Library(Base):
    def test_behaviour_clip_not_rewritten(self):
        from types import SimpleNamespace
        from plandscape.assets.store import store_behavior
        a = SimpleNamespace(spec=SimpleNamespace(key="armadillo"), id=1, trait={"boldness": 0.5}, events=[],
                            log=[(0.0, 1.0, 2.0, 0.0, 0.0, "travel"), (1.0, 2.0, 2.0, 0.0, 0.0, "eat")])
        e1 = store_behavior(self.store, a, "scene")
        path = os.path.join(self.store.root, os.path.splitext(e1.path)[0] + ".json")
        before = open(path).read()
        e2 = store_behavior(self.store, a, "scene")
        self.assertEqual(e1.key, e2.key)
        self.assertEqual(open(path).read(), before)  # same clip, same file: no git churn

    def test_leaf_cards_are_folded(self):
        tm = generate_tree("sweetgum", seed=1, detail="low")
        P = tm.foliage.positions.astype(np.float64)
        n = (len(P) // 6) * 6
        card = P[:n].reshape(-1, 6, 3)[:50]  # spine is vertices 1 and 4; the wings leave its plane
        spine = card[:, 4] - card[:, 1]
        wing_l, wing_r = card[:, 0] - card[:, 1], card[:, 2] - card[:, 1]
        nl = np.cross(spine, wing_l)
        nr = np.cross(wing_r, spine)
        cosang = (nl * nr).sum(1) / np.linalg.norm(nl, axis=1) / np.linalg.norm(nr, axis=1)
        self.assertTrue((cosang < 0.97).all())  # every card has a real fold


class Bark(Base):
    def test_chain_tubes_share_rings_and_detail_matters(self):
        from plandscape.flora.tree import _chains
        lo = generate_tree("sweetgum", seed=3, detail="low")
        hi = generate_tree("sweetgum", seed=3, detail="high")
        self.assertLess(lo.bark.n_tris, hi.bark.n_tris * 0.9)  # TWIG_CULL now actually culls at low
        chains = _chains(lo.skeleton, 0.0)
        nodes = sum(len(c) for c, _ in chains)
        self.assertEqual(nodes, len(lo.skeleton.pos))  # every node in exactly one chain
        # shared rings: far fewer vertices than two private rings per skeleton segment
        self.assertLess(len(lo.bark.positions), 2 * len(lo.skeleton.pos) * 4)


class Erosion(unittest.TestCase):
    def test_droplets_cut_gullies_and_fill_hollows(self):
        from plandscape.terrain.erosion import droplet_erosion
        from plandscape.terrain.heightfield import _thermal_erosion, flow_accumulation
        from plandscape import noise
        n = 96
        Y, X = np.mgrid[0:n, 0:n].astype(float)
        z = 0.4 * X + 3 * noise.fbm(X / 30, Y / 30, 3, octaves=4)  # a tilted, lumpy slope (~40 m relief)
        z = _thermal_erosion(z, 1.0, iters=5)
        a = droplet_erosion(z, seed=1)
        np.testing.assert_array_equal(a, droplet_erosion(z, seed=1))  # deterministic
        self.assertTrue(np.isfinite(a).all())
        d = a - z
        self.assertLess(np.abs(d).max(), 0.2 * np.ptp(z))  # reshapes, doesn't wreck
        rough = lambda h: np.abs(np.diff(h, axis=0)).mean()  # across-slope roughness = gullies
        self.assertGreater(rough(a), rough(z) * 1.05)
        acc = flow_accumulation(z)
        sinks = acc > np.percentile(acc, 98)
        self.assertGreater(d[sinks].mean(), d[~sinks].mean())  # sediment settles where flow gathers


class Splat(Base):
    def test_weights_follow_layers(self):
        from plandscape.ground.surface import ground_weights
        from plandscape.terrain.heightfield import generate_tile
        hf = generate_tile(32, 1.0, "piedmont", 3, creek=False)
        hf.layers["slope"][:] = 0
        hf.layers["water"][:] = 0
        G, canopy, dens = np.zeros_like(hf.z), np.zeros_like(hf.z), np.zeros_like(hf.z)
        G[:, :8] = 1.0          # trail strip
        canopy[:, 12:20] = 1.0  # wood
        dens[:, 24:] = 1.0      # lawn
        w = ground_weights(hf, dens, G, canopy).reshape(*hf.z.shape, 4)
        np.testing.assert_allclose(w.sum(-1), 1, atol=1e-5)
        self.assertEqual(int(np.argmax(w[16, 3])), 1)   # soil on the trail
        self.assertEqual(int(np.argmax(w[16, 16])), 0)  # litter under canopy
        self.assertEqual(int(np.argmax(w[16, 28])), 2)  # grass on the lawn

    def test_height_blend(self):
        a = np.array([[1, 0, 0, 0], [0.5, 0.5, 0, 0]], float)
        h = np.array([[0.2, 0.9, 0.5, 0.5], [0.2, 0.9, 0.5, 0.5]])
        w = textures.height_blend(a, h)
        np.testing.assert_allclose(w.sum(-1), 1)
        np.testing.assert_allclose(w[0], [1, 0, 0, 0], atol=1e-9)  # zero weight stays zero
        self.assertGreater(w[1, 1], 0.99)  # equal weights: the higher texel wins (k = 8)

    def test_glb_carries_splat(self):
        import json, struct
        P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32)
        tex = [textures.get(k, self.store) for k in textures.splat_keys("hardwood")]
        m = Mesh(P, np.full((3, 3), 0.5, np.float32), np.array([[0, 1, 2]], np.uint32), P[:, :2] / 2, tex[0].key,
                 np.eye(4, dtype=np.float32)[[0, 1, 2]], tuple(t.key for t in tex))
        g = GLB()
        g.node("t", g.mesh(m, "t", g.material("terrain", texture=tex[0], splat=tex)))
        path = os.path.join(self.tmp, "s.glb")
        g.save(path)
        self.assertEqual(validate_glb(path), [])
        d = open(path, "rb").read()
        doc = json.loads(d[20:20 + struct.unpack_from("<I", d, 12)[0]])
        self.assertIn("_SPLAT", doc["meshes"][0]["primitives"][0]["attributes"])
        self.assertEqual(len(doc["materials"][0]["extras"]["splat"]["textures"]), 4)


class Models(Base):
    def test_decimate_welds_and_hits_target(self):
        P, UV, I = _sphere()
        P2, UV2, I2 = models.decimate(P, UV, I, 300)
        self.assertLessEqual(len(I2), 300)
        self.assertGreater(len(I2), 60)
        self.assertEqual(int(I2.max()) + 1, len(P2))  # no unreferenced vertices
        # welded: every edge (by position) is shared by ≥ 2 triangles, so no cracks open
        key = {tuple(np.round(p, 6)): k for k, p in enumerate(P2)}
        pid = np.array([key[tuple(np.round(p, 6))] for p in P2])
        e = np.sort(np.concatenate([pid[I2][:, [0, 1]], pid[I2][:, [1, 2]], pid[I2][:, [2, 0]]]), 1)
        _, counts = np.unique(e, axis=0, return_counts=True)
        self.assertEqual(int((counts < 2).sum()), 0)

    def test_thin_cards_keeps_stems(self):
        r = np.random.default_rng(0)
        stem = _sphere(10)
        P, UV, I = [stem[0] * [0.05, 0.05, 1]], [stem[1]], [stem[2]]
        off = len(P[0])
        for k in range(200):  # 200 two-triangle leaf cards
            c = r.uniform(-0.5, 0.5, 3)
            P.append(c + np.array([[0, 0, 0], [0.1, 0, 0], [0.1, 0, 0.1], [0, 0, 0.1]]))
            UV.append(np.zeros((4, 2), np.float32))
            I.append(off + np.array([[0, 1, 2], [0, 2, 3]]))
            off += 4
        P, UV, I = np.concatenate(P), np.concatenate(UV), np.concatenate(I)
        P2, UV2, I2 = models.thin_cards(P, UV, I, len(stem[2]) + 100, r)
        self.assertLessEqual(len(I2), len(stem[2]) + 100)
        self.assertGreater(np.ptp(P2[:, 2]), 1.9)  # the 2 m stem survived

    def test_gltf_roundtrip_through_importer(self):
        P, UV, I = _sphere(12)
        P = P * [1.0, 2.0, 3.0]  # distinct extents per axis catch a wrong up-axis conversion
        g = GLB()
        tex = textures.Texture.from_rgba("x", np.full((8, 8, 4), 200, np.uint8))
        g.node("ball", g.mesh(Mesh(P.astype(np.float32), np.ones_like(P, np.float32), I.astype(np.uint32),
                                   UV, "x"), "ball", g.material("m", texture=tex)))
        path = os.path.join(self.tmp, "ball.glb")
        g.save(path)
        (name, P2, UV2, I2, mi, doc), = list(models.read_gltf(path))
        self.assertEqual(name, "ball")
        np.testing.assert_allclose(np.ptp(P2, 0), np.ptp(P, 0), rtol=1e-5)
        self.assertEqual(len(I2), len(I))

    def test_model_codec_roundtrip(self):
        P, UV, I = _sphere(8)
        tex = textures.Texture.from_rgba("model/demo/0", np.full((8, 8, 4), 200, np.uint8))
        part = models.Part(Mesh(P.astype(np.float32), np.tile(np.float32(tex.mean), (len(P), 1)),
                                I.astype(np.uint32), UV, tex.key), tex,
                           dict(id="demo", variant=0, role="rock", tris=len(I), size=[2, 2, 2], src_tris=len(I),
                                source=dict(url="u", licence="CC0-1.0")))
        enc, dec = models.model_codec()
        self.store.get_or_build("model", dict(id="demo", variant=0, target=1), lambda: part, enc, dec)
        textures._REGISTRY.clear()
        got = models.variants(self.store, "demo")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].mesh.texture, "model/demo/0")
        self.assertIs(textures.get("model/demo/0"), got[0].texture)  # registered for export and preview


if __name__ == "__main__":
    unittest.main()

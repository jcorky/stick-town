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
        self.reg = dict(textures._REGISTRY)
        textures._REGISTRY.clear()

    def tearDown(self):
        self.net.stop()
        self.dl.stop()
        textures._REGISTRY.clear()
        textures._REGISTRY.update(self.reg)
        shutil.rmtree(self.tmp)


class Textures(Base):
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

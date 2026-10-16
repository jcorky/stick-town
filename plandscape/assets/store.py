"""Content-addressed asset library — generate once, reuse everywhere.

Every asset (tree, building, terrain tile, animal body, behaviour clip, grass
patch) is stored under   key = hash(kind, generator version, params)
so the same request always hits the same file, and bumping a generator's
version cleanly invalidates only that kind. Payloads are compressed .npz
(arrays) + a .json sidecar (metadata), with an optional .glb per asset for
use in Blender / three.js / game engines. `index.jsonl` makes the library
searchable ("all fall sweetgums", "every deer clip with boldness > 0.7").

Because generation is deterministic, the index alone can rebuild the library
bit-for-bit; the binaries are a speed cache that can live in Git LFS, a
bucket or a release asset (see docs/ASSETS.md).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass

import numpy as np

from ..mesh import Mesh

# Bump a version when its generator's output changes; old entries stay readable
# but are no longer matched.
GENERATOR_VERSIONS = {
    "tree": "tree-0.2.1",
    "building": "building-0.1.1",
    "terrain": "terrain-0.1.1",
    "body": "body-0.1.0",
    "behavior": "behavior-0.1.1",
    "grass_patch": "grass-0.1.0",
    "texture": "texture-0.1.3",
    "model": "model-0.1.3",
}

DEFAULT_ROOT = os.environ.get(
    "PLANDSCAPE_ASSETS", os.path.join(os.path.dirname(__file__), "..", "..", "assets_library"))


def _canon(v):
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, (list, tuple)):
        return [_canon(x) for x in v]
    if isinstance(v, dict):
        return {k: _canon(v[k]) for k in sorted(v)}
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    return v


@dataclass
class Entry:
    key: str
    kind: str
    version: str
    params: dict
    meta: dict
    path: str


class AssetStore:
    def __init__(self, root: str | None = None, export_glb: bool = False):
        self.root = os.path.abspath(root or DEFAULT_ROOT)
        os.makedirs(self.root, exist_ok=True)
        self.index_path = os.path.join(self.root, "index.jsonl")
        self.export_glb = export_glb
        self.entries: dict[str, Entry] = {}
        self.hits = self.misses = 0
        if os.path.exists(self.index_path):
            with open(self.index_path) as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        self.entries[d["key"]] = Entry(**d)

    # ── keys ───────────────────────────────────────────────────────────
    @staticmethod
    def key(kind: str, params: dict) -> str:
        blob = json.dumps({"kind": kind, "v": GENERATOR_VERSIONS[kind], "p": _canon(params)},
                          sort_keys=True, separators=(",", ":"))
        return hashlib.blake2b(blob.encode(), digest_size=16).hexdigest()

    def _file(self, kind, key, ext):
        d = os.path.join(self.root, kind, key[:2])
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{key}{ext}")

    # ── raw put/get ────────────────────────────────────────────────────
    def has(self, kind, params) -> bool:
        k = self.key(kind, params)
        return k in self.entries and os.path.exists(self._file(kind, k, ".npz"))

    def put(self, kind, params, arrays: dict, meta: dict | None = None, meshes: dict | None = None) -> Entry:
        k = self.key(kind, params)
        path = self._file(kind, k, ".npz")
        np.savez_compressed(path, **arrays)
        meta = dict(meta or {}, created=time.strftime("%Y-%m-%dT%H:%M:%S"))
        e = Entry(k, kind, GENERATOR_VERSIONS[kind], _canon(params), _canon(meta),
                  os.path.relpath(path, self.root))
        with open(self._file(kind, k, ".json"), "w") as f:
            json.dump(e.__dict__, f, indent=1)
        if self.export_glb and meshes:
            from ..export.gltf import GLB
            g = GLB()
            for name, (m, double) in meshes.items():
                mi = g.mesh(m, name, g.material(name, double=double))
                if mi is not None:
                    g.node(name, mi)
            g.save(self._file(kind, k, ".glb"), extras=dict(key=k, kind=kind, params=e.params))
        if k not in self.entries:
            with open(self.index_path, "a") as f:
                f.write(json.dumps(e.__dict__) + "\n")
        self.entries[k] = e
        return e

    def get(self, kind, params):
        k = self.key(kind, params)
        e = self.entries.get(k)
        if e is None:
            return None, None
        path = os.path.join(self.root, e.path)
        if not os.path.exists(path):
            return None, None
        with np.load(path, allow_pickle=False) as z:
            return {n: z[n] for n in z.files}, e

    def get_or_build(self, kind, params, build, encode, decode):
        arrays, e = self.get(kind, params)
        if arrays is not None:
            self.hits += 1
            return decode(arrays, e.meta)
        self.misses += 1
        obj = build()
        arrays, meta, meshes = encode(obj)
        self.put(kind, params, arrays, meta, meshes)
        return obj

    # ── search ─────────────────────────────────────────────────────────
    def find(self, kind=None, current_only=True, **match):
        out = []
        for e in self.entries.values():
            if kind and e.kind != kind:
                continue
            if current_only and e.version != GENERATOR_VERSIONS.get(e.kind):
                continue
            ok = True
            for k, v in match.items():
                have = e.params.get(k, e.meta.get(k))
                if callable(v):
                    ok = ok and have is not None and bool(v(have))
                else:
                    ok = ok and have == v
            if ok:
                out.append(e)
        return out

    def stats(self):
        by = {}
        size = 0
        for e in self.entries.values():
            by[e.kind] = by.get(e.kind, 0) + 1
            p = os.path.join(self.root, e.path)
            if os.path.exists(p):
                size += os.path.getsize(p)
        return dict(root=self.root, entries=len(self.entries), by_kind=by, mb=round(size / 1e6, 2),
                    session_hits=self.hits, session_misses=self.misses)


# ── codecs ─────────────────────────────────────────────────────────────

def mesh_arrays(prefix, m: Mesh):
    a = {f"{prefix}_p": m.positions.astype(np.float32), f"{prefix}_c": (np.clip(m.colors, 0, 1) * 255).astype(np.uint8),
         f"{prefix}_i": m.indices.astype(np.uint32)}
    if m.uvs is not None and m.texture:  # textured: keep UVs and the texture key (a plain unicode array)
        a[f"{prefix}_uv"] = m.uvs.astype(np.float32)
        a[f"{prefix}_tex"] = np.array(m.texture)
    return a


def arrays_mesh(prefix, a):
    uv, tex = a.get(f"{prefix}_uv"), a.get(f"{prefix}_tex")
    return Mesh(a[f"{prefix}_p"], a[f"{prefix}_c"].astype(np.float32) / 255.0, a[f"{prefix}_i"],
                uv, str(tex) if tex is not None else None)


def tree_codec():
    from ..flora.species import SPECIES
    from ..flora.tree import Skeleton, TreeModel

    def enc(tm):
        a = {**mesh_arrays("bark", tm.bark), **mesh_arrays("fol", tm.foliage),
             "sk_pos": tm.skeleton.pos.astype(np.float32), "sk_parent": tm.skeleton.parent.astype(np.int32),
             "sk_radius": tm.skeleton.radius.astype(np.float32), "sk_trunk": tm.skeleton.trunk}
        meta = dict(species=tm.species.key, height=float(tm.height), tris=tm.n_tris,
                    trunk_radius=float(tm.skeleton.radius[0]))
        return a, meta, {"bark": (tm.bark, False), "foliage": (tm.foliage, True)}

    def dec(a, meta):
        sk = Skeleton(a["sk_pos"].astype(np.float64), a["sk_parent"].astype(np.int64),
                      a["sk_radius"].astype(np.float64), a["sk_trunk"].astype(bool))
        return TreeModel(SPECIES[meta["species"]], None, float(meta["height"]), sk,
                         arrays_mesh("bark", a), arrays_mesh("fol", a))
    return enc, dec


def mesh_codec(name="mesh", double=False):
    def enc(obj):
        m, meta = obj if isinstance(obj, tuple) else (obj, {})
        return mesh_arrays("m", m), dict(meta, tris=m.n_tris), {name: (m, double)}

    def dec(a, meta):
        return arrays_mesh("m", a), meta
    return enc, dec


def terrain_codec():
    from ..terrain.heightfield import Heightfield

    def enc(hf):
        a = {"z": hf.z.astype(np.float32), **{f"L_{k}": v.astype(np.float32) for k, v in hf.layers.items()}}
        return a, dict(province=hf.province, res=hf.res, origin=list(hf.origin), shape=list(hf.z.shape)), None

    def dec(a, meta):
        hf = Heightfield(a["z"].astype(np.float64), float(meta["res"]), tuple(meta["origin"]), meta["province"])
        hf.layers = {k[2:]: a[k].astype(np.float64) for k in a if k.startswith("L_")}
        return hf
    return enc, dec


STATES = ["idle", "travel", "eat", "drink", "rest", "pause", "alert", "freeze", "flee", "dig", "groom", "scratch"]


def store_behavior(store: AssetStore, agent, scene_key: str):
    """Save an agent's lived trajectory as a reusable motion clip."""
    L = np.array([(l[0], l[1], l[2], l[3], l[4]) for l in agent.log], np.float32)
    st = np.array([STATES.index(l[5]) if l[5] in STATES else 0 for l in agent.log], np.uint8)
    x0 = L[0, 1:3].copy()
    L[:, 1:3] -= x0  # store relative to start so clips can be re-placed anywhere
    params = dict(species=agent.spec.key, scene=scene_key, agent=agent.id)
    if store.has("behavior", params):  # deterministic: same scene, same clip; don't rewrite it (git churn)
        return store.entries[store.key("behavior", params)]
    states, n = np.unique(st, return_counts=True)
    meta = dict(species=agent.spec.key, traits={k: round(float(v), 3) for k, v in agent.trait.items()},
                duration=float(L[-1, 0]), distance=float(np.hypot(*np.diff(L[:, 1:3], axis=0).T).sum()),
                state_mix={STATES[s]: int(c) for s, c in zip(states, n)},
                events=[list(e) for e in agent.events[:120]])
    return store.put("behavior", params, {"track": L, "state": st}, meta)

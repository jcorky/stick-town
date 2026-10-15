"""Imported models: Poly Haven glTF → decimated, textured, library-cached variants.

  python -m plandscape.assets bake-models          # fetch, decimate and store everything in MODELS

Poly Haven ships photoscans at 0.2–2 M triangles. Scenes need a few thousand per
prop, so each glTF node (Poly Haven packs variants side by side, e.g. six rocks)
becomes one library entry:
  * solid meshes are decimated by vertex clustering; positions are shared per spatial
    cell, so neighbouring triangles stay welded and no cracks open,
  * alpha-card meshes (ferns, shrubs) are thinned by dropping whole cards and
    enlarging the rest, which keeps their silhouette and cover,
  * the colour map (with the alpha map folded in) is cut to 512 px.
Everything stays numpy + scipy + Pillow. Licence and authors come from the
licence-gated fetcher and are kept in each entry's metadata.
"""

from __future__ import annotations

import io
import json
import os
import struct
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from . import textures
from .mesh import Mesh
from .rng import rng as make_rng

# id: (role, target triangles per variant). Chosen for Southern woods: mossy sandstone
# (Cumberland Plateau), stumps and fallen logs, ferns and understory shrubs.
MODELS = {
    "tree_stump_01": ("stump", 2500),
    "tree_stump_02": ("stump", 2500),
    "dead_tree_trunk": ("log", 3000),
    "dead_tree_trunk_02": ("log", 3000),
    "dry_branches_medium_01": ("deadfall", 800),
    "rock_moss_set_01": ("rock", 1200),
    "rock_moss_set_02": ("rock", 1200),
    "boulder_01": ("boulder", 3000),
    "fern_02": ("fern", 1600),
    "shrub_02": ("shrub", 8000),  # leaf cards: thinning below ~1/3 leaves leaves floating, so keep it whole
}
TEX_SIZE = 512

COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
NORM_DIV = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


@dataclass
class Part:
    """One variant: a z-up mesh with UVs, its texture, and where it came from."""
    mesh: Mesh
    texture: textures.Texture
    meta: dict = field(default_factory=dict)


# ── glTF reading ────────────────────────────────────────────────────────────

def _load_doc(path):
    if path.endswith(".glb"):
        with open(path, "rb") as f:
            data = f.read()
        jl = struct.unpack_from("<I", data, 12)[0]
        doc = json.loads(data[20:20 + jl])
        bl = struct.unpack_from("<I", data, 20 + jl)[0]
        return doc, [data[28 + jl:28 + jl + bl]]
    with open(path) as f:
        doc = json.load(f)
    bufs = []
    for b in doc["buffers"]:
        uri = b["uri"]
        if uri.startswith("data:") or ".." in uri:
            raise ValueError("embedded or escaping buffer URIs are not supported")
        with open(os.path.join(os.path.dirname(path), uri), "rb") as f:
            bufs.append(f.read())
    return doc, bufs


def _accessor(doc, bufs, i):
    a = doc["accessors"][i]
    v = doc["bufferViews"][a["bufferView"]]
    dt = np.dtype(COMP[a["componentType"]])
    n = NCOMP[a["type"]]
    stride = v.get("byteStride", dt.itemsize * n)
    off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    raw = np.frombuffer(bufs[v["buffer"]], np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * n, offset=off)
    out = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * n), (stride, 1)).copy()
    out = out.view(dt).reshape(a["count"], n)
    if a.get("normalized"):
        out = out.astype(np.float32) / NORM_DIV[a["componentType"]]
    return out


def _quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _local(node):
    M = np.eye(4)
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    S = np.diag(node.get("scale", [1, 1, 1]))
    M[:3, :3] = _quat_mat(node.get("rotation", [0, 0, 0, 1])) @ S
    M[:3, 3] = node.get("translation", [0, 0, 0])
    return M


def read_gltf(path):
    """Yield (node_name, positions_zup, uvs, indices, material_index) per mesh node.
    Node rotation/scale are applied; translation is dropped so each variant sits at the origin."""
    doc, bufs = _load_doc(path)
    parents = {c: i for i, n in enumerate(doc["nodes"]) for c in n.get("children", [])}
    for ni, node in enumerate(doc["nodes"]):
        if "mesh" not in node:
            continue
        M, k = _local(node), ni
        while k in parents:
            k = parents[k]
            M = _local(doc["nodes"][k]) @ M
        M[:3, 3] = 0
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4 or "TEXCOORD_0" not in prim["attributes"]:
                continue
            P = _accessor(doc, bufs, prim["attributes"]["POSITION"]).astype(np.float64)
            P = (np.c_[P, np.ones(len(P))] @ M.T)[:, :3]
            P = np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1)  # glTF y-up → world z-up
            UV = _accessor(doc, bufs, prim["attributes"]["TEXCOORD_0"]).astype(np.float32)
            I = (_accessor(doc, bufs, prim["indices"]).ravel() if "indices" in prim
                 else np.arange(len(P))).astype(np.int64).reshape(-1, 3)
            yield node.get("name", f"node{ni}"), P, UV, I, prim.get("material"), doc


def _material_texture(doc, mat_index, gltf_path, alpha_path, asset_id):
    """The material's colour map at TEX_SIZE. Keyed by asset and image, so variants that share
    an atlas (a rock set's six rocks) share one texture in the library and in the GLB."""
    mat = doc["materials"][mat_index] if mat_index is not None else {}
    pbr = mat.get("pbrMetallicRoughness", {})
    bt = pbr.get("baseColorTexture")
    key = f"model/{asset_id}/{mat_index}"
    if bt is None:
        rgb = np.array(pbr.get("baseColorFactor", [0.5, 0.5, 0.5, 1])[:3]) * 255
        return textures.Texture.from_rgba(key, np.tile(np.r_[rgb, 255].astype(np.uint8), (8, 8, 1)))
    uri = doc["images"][doc["textures"][bt["index"]]["source"]]["uri"]
    if ".." in uri:
        raise ValueError(uri)
    img = Image.open(os.path.join(os.path.dirname(gltf_path), uri)).convert("RGB").resize(
        (TEX_SIZE, TEX_SIZE), Image.LANCZOS)
    rgba = np.dstack([np.asarray(img), np.full((TEX_SIZE, TEX_SIZE), 255, np.uint8)])
    if mat.get("alphaMode") == "MASK" and alpha_path:
        a = np.asarray(Image.open(alpha_path).convert("L").resize((TEX_SIZE, TEX_SIZE), Image.LANCZOS))
        rgba[..., 3] = np.where(a > 127, 255, 0)
    return textures.Texture.from_rgba(key, rgba)


# ── decimation ──────────────────────────────────────────────────────────────

def _cluster(P, UV, I, cell, uv_bins=6):
    nrm = np.zeros_like(P)
    fn = np.cross(P[I[:, 1]] - P[I[:, 0]], P[I[:, 2]] - P[I[:, 0]])
    for k in range(3):
        np.add.at(nrm, I[:, k], fn)
    axis = np.argmax(np.abs(nrm), 1) * 2 + (nrm[np.arange(len(nrm)), np.argmax(np.abs(nrm), 1)] > 0)
    g = np.floor((P - P.min(0)) / cell).astype(np.int64)
    _, pos_lab = np.unique(g, axis=0, return_inverse=True)  # one welded position per cell: no cracks
    pos_lab = pos_lab.ravel()
    # vertices split by UV chart and facing, so seams and two-sided sheets keep their own UVs
    _, vlab = np.unique(np.c_[pos_lab, np.floor(UV * uv_bins).astype(np.int64), axis], axis=0,
                        return_inverse=True)
    vlab = vlab.ravel()
    npos, nv = pos_lab.max() + 1, vlab.max() + 1
    cnt = np.bincount(pos_lab, minlength=npos)[:, None]
    Pc = np.stack([np.bincount(pos_lab, P[:, k], npos) for k in range(3)], 1) / cnt
    vcnt = np.bincount(vlab, minlength=nv)[:, None]
    UVc = np.stack([np.bincount(vlab, UV[:, k], nv) for k in range(2)], 1) / vcnt
    vpos = np.zeros(nv, np.int64)
    vpos[vlab] = pos_lab                       # vertices of one cell share one position: no cracks
    T = vlab[I]
    pT = vpos[T]
    ok = (pT[:, 0] != pT[:, 1]) & (pT[:, 1] != pT[:, 2]) & (pT[:, 0] != pT[:, 2])
    T = T[ok]
    _, first = np.unique(np.sort(vpos[T], 1), axis=0, return_index=True)
    T = T[np.sort(first)]
    used, T = np.unique(T, return_inverse=True)
    return Pc[vpos[used]], UVc[used], T.reshape(-1, 3)


def decimate(P, UV, I, target):
    """Vertex-clustering simplification to roughly `target` triangles (never more)."""
    if len(I) <= target:
        return P, UV, I
    ext = float(np.ptp(P, 0).max())
    lo, hi = ext / 2000, ext / 3
    best = None
    for _ in range(22):
        cell = np.sqrt(lo * hi)
        out = _cluster(P, UV, I, cell)
        if len(out[2]) > target:
            lo = cell
        else:
            hi, best = cell, out
            if len(out[2]) > 0.85 * target:
                break
    return best if best is not None else _cluster(P, UV, I, hi)


def thin_cards(P, UV, I, target, r):
    """Alpha-card foliage: keep whole connected cards, enlarged about their centres to hold cover."""
    if len(I) <= target:
        return P, UV, I
    n = len(P)
    e = np.r_[I[:, 0], I[:, 1], I[:, 2]], np.r_[I[:, 1], I[:, 2], I[:, 0]]
    _, lab = connected_components(coo_matrix((np.ones(len(e[0])), e), (n, n)), directed=False)
    tri_lab = lab[I[:, 0]]
    comps = np.unique(tri_lab)
    tri_per = np.bincount(tri_lab, minlength=lab.max() + 1)
    big = comps[tri_per[comps] > 0.05 * len(I)]  # stems and trunks: always kept, or leaves float
    order = np.r_[big, r.permutation(np.setdiff1d(comps, big))]
    keep, total = [], 0
    for c in order:
        if total + tri_per[c] > target and keep and c not in big:
            continue
        keep.append(c)
        total += tri_per[c]
    keep = np.array(keep)
    frac = max(total - tri_per[big].sum(), 1) / max(len(I) - tri_per[big].sum(), 1)
    T = I[np.isin(tri_lab, keep)]
    used, T = np.unique(T, return_inverse=True)
    Pk, lk = P[used].copy(), lab[used]
    cen = np.stack([np.bincount(lk, Pk[:, k], lab.max() + 1) for k in range(3)], 1) / \
        np.maximum(np.bincount(lk, minlength=lab.max() + 1), 1)[:, None]
    grow = np.where(np.isin(lk, big), 1.0, min(1 / np.sqrt(frac), 2.0))[:, None]
    Pk = cen[lk] + (Pk - cen[lk]) * grow
    return Pk, UV[used], T.reshape(-1, 3)


# ── import + library ────────────────────────────────────────────────────────

def import_model(asset_id, target=None, res="1k"):
    """Fetch a Poly Haven model and return one Part per variant (node)."""
    from .sources.sites import fetch_polyhaven_model
    got = fetch_polyhaven_model(asset_id, res)
    role, tgt = MODELS.get(asset_id, ("prop", 3000))
    target = target or tgt
    parts = []
    for v, (name, P, UV, I, mi, doc) in enumerate(read_gltf(got["gltf"])):
        tex = _material_texture(doc, mi, got["gltf"], got.get("alpha"), asset_id)
        key = tex.key
        src_tris = len(I)
        if tex.alpha:
            P, UV, I = thin_cards(P, UV, I, target, make_rng("thin", asset_id, v))
        else:
            P, UV, I = decimate(P, UV, I, target)
        P = P - [*(P[:, :2].min(0) + P[:, :2].max(0)) / 2, P[:, 2].min()]  # centred, base on z=0
        m = Mesh(P.astype(np.float32), np.tile(np.float32(tex.mean), (len(P), 1)), I.astype(np.uint32),
                 UV.astype(np.float32), key)
        parts.append(Part(m, tex, dict(id=asset_id, variant=v, name=name, role=role, src_tris=src_tris,
                                       tris=int(len(I)), size=[round(float(x), 3) for x in np.ptp(P, 0)],
                                       source=got["_source"])))
    return parts


def model_codec():
    def enc(part: Part):
        m, t = part.mesh, part.texture
        # each variant stores the shared map too (entries must stand alone); 512² JPEGs are ~60–150 KB
        a = {"p": m.positions, "uv": m.uvs, "i": m.indices, "tex": np.frombuffer(t.data, np.uint8)}
        meta = dict(part.meta, mime=t.mime, mean=[round(float(x), 4) for x in t.mean], alpha=t.alpha, tex_key=t.key)
        return a, meta, {"model": (Mesh(m.positions, m.colors, m.indices), t.alpha)}

    def dec(a, meta):
        key = meta["tex_key"]
        tex = textures._REGISTRY.get(key) or textures.register(
            textures.Texture.from_bytes(key, a["tex"].tobytes(), meta["mime"], meta["mean"]))
        m = Mesh(a["p"], np.tile(np.float32(meta["mean"]), (len(a["p"]), 1)), a["i"], a["uv"], key)
        return Part(m, tex, meta)
    return enc, dec


def bake(store, ids=None, log=print):
    """Import every model in MODELS (or `ids`) into the library; returns {id: n_variants}."""
    enc, dec = model_codec()
    out = {}
    for mid in ids or MODELS:
        have = store.find("model", id=mid)
        if have:
            out[mid] = len(have)
            continue
        parts = import_model(mid)
        for p in parts:
            store.get_or_build("model", dict(id=mid, variant=p.meta["variant"], target=MODELS.get(mid, ("", 0))[1]),
                               lambda p=p: p, enc, dec)
        out[mid] = len(parts)
        log(f"{mid}: {len(parts)} variants, {sum(p.meta['src_tris'] for p in parts)} → "
            f"{sum(p.meta['tris'] for p in parts)} tris")
    return out


def variants(store, mid):
    """Decoded Parts for a model already in the library (no network)."""
    _, dec = model_codec()
    out = []
    for e in sorted(store.find("model", id=mid), key=lambda e: e.params["variant"]):
        arrays, entry = store.get("model", e.params)
        if arrays is not None:  # missing binary (e.g. an un-pulled LFS pointer): skip, never rebuild here
            store.hits += 1
            out.append(dec(arrays, entry.meta))
    return out

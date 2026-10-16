"""Per-vertex wind attributes: what each vertex of a tree, an impostor or a grass blade needs so the viewer can
move it (TECHNIQUES §34). Three uint8/int8 vec4s, 12 bytes a vertex:

    _WIND0  u8   φ_t = 1 − cos(π z / 2H),  √(d1/D_MAX),  √(d2/D_MAX),  lever/L_MAX
    _WIND1  i8   limb axis (glTF frame, unit),  limb phase ∈ [−1, 1]
    _WIND2  u8   f1/F1_MAX,  f2/F2_MAX,  branch phase,  leaf phase

d1, d2 are static deflections at U_REF (stored as square roots: millimetre twigs and metre limbs both keep
precision in 8 bits); f1, f2 the limb and branch frequencies from response.mechanics. Grass reuses _WIND0 as
(φ along the blade, shelter/2, blade length, phase).
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from ..rng import derive_seed
from .response import D_MAX, F1_MAX, F2_MAX, L_MAX, leaf_cards, mechanics, mode_shape


def _hash01(ids, salt):
    ids = np.asarray(ids, np.int64)
    return ((ids * 2654435761 + derive_seed("wind-phase", salt) % 997) % 1009) / 1009.0


def _u8(a):
    return np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)


def _i8(a):
    return np.round(np.clip(a, -1, 1) * 127).astype(np.int8)


def _to_gltf(v):
    return np.stack([v[..., 0], v[..., 2], -v[..., 1]], -1)


def pack(phi, d1, d2, lever, axis, ph1, f1, f2, ph2, phl):
    w0 = np.stack([_u8(phi), _u8(np.sqrt(np.maximum(d1, 0) / D_MAX)), _u8(np.sqrt(np.maximum(d2, 0) / D_MAX)),
                   _u8(lever / L_MAX)], -1)
    w1 = np.concatenate([_i8(_to_gltf(axis)), _i8(2 * ph1[:, None] - 1)], -1)
    w2 = np.stack([_u8(f1 / F1_MAX), _u8(f2 / F2_MAX), _u8(ph2), _u8(phl)], -1)
    return {"_WIND0": w0, "_WIND1": w1, "_WIND2": w2}


def unpack(a):
    """Decode packed attributes back to physical values (what the shader does)."""
    w0 = a["_WIND0"].astype(np.float64) / 255
    w1 = a["_WIND1"].astype(np.float64) / 127
    w2 = a["_WIND2"].astype(np.float64) / 255
    ax = w1[:, :3]
    return dict(phi=w0[:, 0], d1=D_MAX * w0[:, 1] ** 2, d2=D_MAX * w0[:, 2] ** 2, lever=L_MAX * w0[:, 3],
                axis=np.stack([ax[:, 0], -ax[:, 2], ax[:, 1]], -1), ph1=(w1[:, 3] + 1) / 2,
                f1=F1_MAX * w2[:, 0], f2=F2_MAX * w2[:, 1], ph2=w2[:, 2], phl=w2[:, 3])


def tree_attributes(tm, season="summer"):
    """(TreeWind, {"bark": attrs, "foliage": attrs}) for a tree model."""
    tw, nd = mechanics(tm, season)
    sk = tm.skeleton
    H = tm.height
    kd = cKDTree(sk.pos)
    out = {}
    for name, m in (("bark", tm.bark), ("foliage", tm.foliage)):
        if m is None or not len(m.positions):
            continue
        P = m.positions.astype(np.float64)
        if name == "foliage":
            lab, node, lever, _, _ = leaf_cards(m, sk)
            phl = _hash01(lab, "leaf")
        else:
            node = kd.query(P)[1]
            lever, phl = np.zeros(len(P)), np.zeros(len(P))
        phi = mode_shape(P[:, 2], H)
        out[name] = pack(phi, nd["d1"][node], nd["d2"][node], lever, nd["axis"][node],
                         _hash01(nd["limb"][node], "limb"), nd["f1"][node], nd["f2"][node],
                         _hash01(nd["branch"][node], "branch"), phl)
    return tw, out


def impostor_attributes(mesh, H):
    """Far cards sway with the trunk mode only."""
    P = mesh.positions
    n = len(P)
    z = np.zeros(n)
    return pack(mode_shape(P[:, 2], H), z, z, z, np.tile([0.0, 0.0, 1.0], (n, 1)), z, z, z, z, z)


def grass_attributes(grass, wind, cover_at, seed=0):
    """Grass blades come as 5 vertices (two pairs and a tip): φ = t² along the blade, the local shelter
    s = U(h_blade, cover)/U_h, blade length, and a per-blade phase."""
    P = grass.positions.astype(np.float64)
    nb = len(P) // 5
    B = P[: nb * 5].reshape(nb, 5, 3)
    base = B[:, :2].mean(1)
    tip = B[:, 4]
    L = np.maximum(np.linalg.norm(tip - base, axis=1), 1e-3)
    t = np.array([0.0, 0.0, 0.5, 0.5, 1.0])
    s = wind.mean_speed(0.6 * L, cover_at(base[:, 0], base[:, 1])) / wind.Uh
    ph = _hash01(np.arange(nb), ("grass", seed))
    w0 = np.stack([_u8(np.tile(t ** 2, nb)), _u8(np.repeat(s / 2, 5)), _u8(np.repeat(L, 5)),
                   _u8(np.repeat(ph, 5))], -1)
    return {"_WIND0": w0}

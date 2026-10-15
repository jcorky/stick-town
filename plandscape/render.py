"""Dependency-free preview renderer (z-buffer + Lambert shading, alpha-tested textures).

Used by tests and review loops: every generator change should be looked at,
not just measured. Not a substitute for the three.js viewer or Blender.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .mesh import Mesh


def _gather(meshes):
    """Concatenate meshes keeping per-triangle texture ids and per-vertex UVs."""
    from . import textures
    P, C, I, U, T, texs, off = [], [], [], [], [], [], 0
    for m in meshes:
        if m is None or not len(m.positions) or not m.n_tris:
            continue
        tex = textures.get(m.texture) if (m.texture and m.uvs is not None) else None
        tid = -1
        if tex is not None:
            texs.append(tex)
            tid = len(texs) - 1
        P.append(m.positions)
        C.append(m.colors)
        I.append(m.indices + off)
        U.append(m.uvs if tex is not None else np.zeros((len(m.positions), 2), np.float32))
        T.append(np.full(m.n_tris, tid, np.int32))
        off += len(m.positions)
    if not P:
        z = np.zeros((0, 3), np.float32)
        return z, z, np.zeros((0, 3), np.uint32), np.zeros((0, 2), np.float32), np.zeros(0, np.int32), []
    return (np.concatenate(P).astype(np.float64), np.concatenate(C).astype(np.float32), np.concatenate(I),
            np.concatenate(U).astype(np.float32), np.concatenate(T), texs)


def render(meshes, path, size=(900, 700), azimuth=35.0, elevation=22.0,
           sky=(0.72, 0.80, 0.88), sun=(0.4, -0.3, 0.85), fit=None, max_tris=400_000, keep_first=1):
    """Meshes after the first `keep_first` may be thinned to `max_tris` for speed;
    the leading meshes (terrain, buildings) are never thinned, or the ground gets holes."""
    meshes = list(meshes) if isinstance(meshes, (list, tuple)) else [meshes]
    P, COL, tri, UV, TID, texs = _gather(meshes)
    n_solid = sum(m.n_tris for m in meshes[:keep_first] if m is not None)
    budget = max(max_tris - n_solid, 0)
    if len(tri) - n_solid > budget:
        keep = np.random.default_rng(0).choice(len(tri) - n_solid, budget, replace=False) + n_solid
        sel = np.r_[np.arange(n_solid), np.sort(keep)]
        tri, TID = tri[sel], TID[sel]
    m = Mesh(P, COL, tri)
    means = [np.asarray(t.mean, np.float32) for t in texs]
    az, el = np.radians(azimuth), np.radians(elevation)
    fwd = np.array([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), -np.sin(el)])
    right = np.array([np.cos(az), -np.sin(az), 0.0])
    up = np.cross(right, fwd)
    lo, hi = (fit if fit is not None else (P.min(0), P.max(0)))
    c = (np.asarray(lo) + np.asarray(hi)) / 2
    Q = P - c
    sx, sy, depth = Q @ right, Q @ up, Q @ fwd
    W, H = size
    if fit is not None:  # frame the fit box, not the whole mesh
        lo_, hi_ = np.asarray(fit[0], float), np.asarray(fit[1], float)
        corners = np.array([[x, y, z] for x in (lo_[0], hi_[0]) for y in (lo_[1], hi_[1]) for z in (lo_[2], hi_[2])]) - c
        fx_, fy_ = corners @ right, corners @ up
        span = max(np.ptp(fx_) / (W * 0.95), np.ptp(fy_) / (H * 0.95), 1e-6)
    else:
        span = max(np.ptp(sx) / (W * 0.9), np.ptp(sy) / (H * 0.9), 1e-6)
    px = W / 2 + sx / span
    py = H / 2 - sy / span
    a, b, d = (P[tri[:, k]] for k in range(3))
    n = np.cross(b - a, d - a)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    n = np.where((n @ fwd)[:, None] > 0, -n, n)  # two-sided
    s = np.asarray(sun, float) / np.linalg.norm(sun)
    shade = 0.5 + 0.6 * np.clip(n @ s, 0, 1) * min(1.0, 0.4 + s[2] * 2)
    col = m.colors[tri].mean(1) * shade[:, None]
    # atmospheric perspective
    dz = depth[tri].mean(1)
    fog = np.clip((dz - dz.min()) / max(np.ptp(dz), 1e-6), 0, 1)[:, None] * 0.25
    col = col * (1 - fog) + np.asarray(sky) * fog
    # z-buffered rasteriser (painter's ordering breaks on large triangles)
    g = np.linspace(1.0, 0.75, H)[:, None, None] * np.asarray(sky)[None, None]
    frame = np.repeat(g, W, 1).astype(np.float32)
    zbuf = np.full((H, W), np.inf, np.float32)
    X, Y, Z = px[tri], py[tri], depth[tri]
    C = np.clip(col, 0, 1).astype(np.float32)
    x0 = np.clip(np.floor(X.min(1)), 0, W - 1).astype(int)
    x1 = np.clip(np.ceil(X.max(1)), 0, W - 1).astype(int)
    y0 = np.clip(np.floor(Y.min(1)), 0, H - 1).astype(int)
    y1 = np.clip(np.ceil(Y.max(1)), 0, H - 1).astype(int)
    for i in range(len(tri)):
        if x1[i] < x0[i] or y1[i] < y0[i]:
            continue
        xs = np.arange(x0[i], x1[i] + 1) + 0.5
        ys = np.arange(y0[i], y1[i] + 1) + 0.5
        qx, qy = np.meshgrid(xs, ys)
        (ax, bx, cx), (ay, by, cy) = X[i], Y[i]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l1 = ((by - cy) * (qx - cx) + (cx - bx) * (qy - cy)) / den
        l2 = ((cy - ay) * (qx - cx) + (ax - cx) * (qy - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
        if not inside.any():
            continue
        zz = l1 * Z[i, 0] + l2 * Z[i, 1] + l3 * Z[i, 2]
        sub = zbuf[y0[i]:y1[i] + 1, x0[i]:x1[i] + 1]
        win = inside & (zz < sub)
        t = TID[i]
        if t >= 0 and win.any():  # alpha-tested texture lookup, modulated so its mean maps to the vertex colour
            uv = UV[tri[i]]
            u = l1 * uv[0, 0] + l2 * uv[1, 0] + l3 * uv[2, 0]
            v = l1 * uv[0, 1] + l2 * uv[1, 1] + l3 * uv[2, 1]
            s_ = texs[t].sample(u, v)
            win &= s_[..., 3] > 0.5
            sub[win] = zz[win]
            frame[y0[i]:y1[i] + 1, x0[i]:x1[i] + 1][win] = np.clip(C[i] * s_[win][:, :3] / means[t], 0, 1)
            continue
        sub[win] = zz[win]
        frame[y0[i]:y1[i] + 1, x0[i]:x1[i] + 1][win] = C[i]
    img = Image.fromarray((frame * 255).astype(np.uint8))
    img.save(path)
    return path

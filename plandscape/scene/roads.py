"""A county road with a real surface: routed, smoothed, cut into the slope, gravelled.

1. Route: Dijkstra on the 8-connected 1 m grid (after Azgaar's Fantasy-Map-Generator, MIT), with step cost
       w = d · (1 + (s/12)²) · (1 + 8 W) · (0.5 if the step follows an existing path)
   d = step length, s = slope in degrees, W = water. Steep ground and creeks are avoided, old paths reused.
2. Smooth: sharp vertices relaxed toward their neighbours' midpoint (angle < 135° → ½, < 115° → ⅔),
   then Chaikin corner cutting, then resampled every 1 m.
3. Grade: the centreline height is the terrain under it, Gaussian-smoothed along the road (σ = 8 m).
4. Cut and fill: with d the distance to the centreline, W_r the road width,
       crown   z = z_c + 0.08 (1 − (2d/W_r)²) − 0.12 (bed)       for d ≤ W_r/2
       ditch   z = z_c − 0.35 · sin(π (d − W_r/2)/2)              for W_r/2 < d ≤ W_r/2 + 2
       blend   z = lerp(z_c − 0, z_terrain, smoothstep over 4 m)   beyond, back to the untouched slope
5. Surface: a ribbon mesh 3 cm above the graded bed, gravel texture, UV u across, v along every 4 m.
See docs/TECHNIQUES.md §15.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from ..mesh import Mesh

ROAD_WIDTH = 4.5  # m, a rural two-track gravel county road
BED_DROP = 0.12   # m the graded bed sits below the gravel ribbon, so the 1 m terrain grid never pokes through
OFFS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def route(hf, start, goal, trail=None):
    """Least-cost grid path between two world points; returns (N, 2) world xy."""
    ny, nx = hf.z.shape
    slope = hf.layers["slope"]
    water = hf.layers["water"]
    G = np.zeros_like(slope) if trail is None else trail
    cell = (1 + (slope / 12.0) ** 2) * (1 + 8 * water) * np.where(G > 0.35, 0.5, 1.0)
    ii, jj = np.indices((ny, nx))
    rows, cols, wts = [], [], []
    for di, dj in OFFS:
        a = (ii + di >= 0) & (ii + di < ny) & (jj + dj >= 0) & (jj + dj < nx)
        src = (ii * nx + jj)[a]
        dst = ((ii + di) * nx + (jj + dj))[a]
        d = np.hypot(di, dj) * hf.res
        wts.append(d * 0.5 * (cell[ii[a], jj[a]] + cell[ii[a] + di, jj[a] + dj]))
        rows.append(src)
        cols.append(dst)
    g = coo_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), (ny * nx, ny * nx)).tocsr()

    def node(p):
        gx, gy = hf.to_grid(*p)
        return int(np.clip(round(float(gy)), 0, ny - 1)) * nx + int(np.clip(round(float(gx)), 0, nx - 1))
    s, t = node(start), node(goal)
    _, pred = dijkstra(g, indices=s, return_predecessors=True)
    path = [t]
    while path[-1] != s and pred[path[-1]] >= 0:
        path.append(pred[path[-1]])
    path = np.array(path[::-1])
    return np.c_[hf.origin[0] + (path % nx) * hf.res, hf.origin[1] + (path // nx) * hf.res].astype(float)


def smooth(pts, iters=3, step=1.0):
    """Relax sharp angles, cut corners (Chaikin), resample every `step` metres."""
    p = np.asarray(pts, float)
    for _ in range(2):
        q = p.copy()
        for k in range(1, len(p) - 1):
            a, b = p[k - 1] - p[k], p[k + 1] - p[k]
            cosang = np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-9)
            ang = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
            if ang < 135:
                f = 2 / 3 if ang < 115 else 0.5
                q[k] = p[k] + f * ((p[k - 1] + p[k + 1]) / 2 - p[k])
        p = q
    for _ in range(iters):  # Chaikin: each edge → points at ¼ and ¾
        a, b = p[:-1], p[1:]
        mid = np.stack([0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b], 1).reshape(-1, 2)
        p = np.vstack([p[:1], mid, p[-1:]])
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    s = np.arange(0, seg[-1], step)
    return np.c_[np.interp(s, seg, p[:, 0]), np.interp(s, seg, p[:, 1])]


def grade(hf, centre, width=ROAD_WIDTH):
    """Cut and fill the heightfield along the road; returns (graded copy, centreline z, distance grid)."""
    zc = ndimage.gaussian_filter1d(hf.sample(centre[:, 0], centre[:, 1]), 8.0, mode="nearest")
    ny, nx = hf.z.shape
    mask = np.ones((ny, nx), bool)
    gi = np.clip(np.round((centre[:, 1] - hf.origin[1]) / hf.res).astype(int), 0, ny - 1)
    gj = np.clip(np.round((centre[:, 0] - hf.origin[0]) / hf.res).astype(int), 0, nx - 1)
    mask[gi, gj] = False
    owner = np.full((ny, nx), -1)
    owner[gi, gj] = np.arange(len(centre))
    dist, (ii, jj) = ndimage.distance_transform_edt(mask, sampling=hf.res, return_indices=True)
    zroad = zc[owner[ii, jj]]
    half = width / 2
    z = hf.z.copy()
    crown = zroad + 0.08 * (1 - np.clip(2 * dist / width, 0, 1) ** 2) - BED_DROP  # bed sits under the gravel
    t = np.clip((dist - half) / 2.0, 0, 1)
    ditch = zroad - 0.35 * np.sin(np.pi * t)
    u = np.clip((dist - half - 2.0) / 4.0, 0, 1)
    blend = u * u * (3 - 2 * u)
    z = np.where(dist <= half, crown, np.where(dist <= half + 2.0, ditch, zroad * (1 - blend) + hf.z * blend))
    return z, zc, dist


def ribbon(centre, zc, width=ROAD_WIDTH, rgb=(0.60, 0.54, 0.45), texture="ground/Gravel023"):
    """Road surface strip, 3 cm over the graded bed, with along-road UVs."""
    t = np.gradient(centre, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    nrm = np.c_[-t[:, 1], t[:, 0]]
    across = np.linspace(-0.5, 0.5, 5)  # 5 across so the crown shows
    P = (centre[:, None, :] + nrm[:, None, :] * across[None, :, None] * width)
    crown = 0.08 * (1 - (2 * across) ** 2)
    Z = zc[:, None] + crown[None, :] + 0.03
    pos = np.dstack([P, Z]).reshape(-1, 3)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(centre, axis=0), axis=1))]
    uv = np.stack(np.broadcast_arrays((across + 0.5)[None, :] * width / 4.0, s[:, None] / 4.0), -1).reshape(-1, 2)
    n, m = len(centre), len(across)
    k = (np.arange(n - 1)[:, None] * m + np.arange(m - 1)[None, :]).ravel()
    idx = np.concatenate([np.c_[k, k + m, k + 1], np.c_[k + 1, k + m, k + m + 1]])
    edge = np.abs(across) > 0.4  # worn edges darker, centre strip lighter (two tracks)
    shade = np.where(edge, 0.85, np.where(np.abs(across) < 0.1, 1.05, 1.0))
    col = np.tile((np.asarray(rgb)[None, :] * shade[:, None]), (n, 1))
    return Mesh(pos.astype(np.float32), col.astype(np.float32), idx.astype(np.uint32), uv.astype(np.float32),
                texture)

"""Ground: terrain surface colouring, grass blades, and visible signs of life.

Soil colour comes from the province (red Piedmont clay, pale Coastal Plain
sand, dark Delta alluvium). Grass density falls off under canopy, on steep
slopes, in water and on trails; trails show as packed bare soil. Warm-season
lawn grasses go dormant tan in winter, as they do across the South.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from ..mesh import Mesh
from ..rng import rng as make_rng
from ..terrain.heightfield import PROVINCES

GRASSES = {
    # key: (height range m, blade width m, summer rgb, dormant rgb)
    "bermuda": ((0.04, 0.12), 0.003, (0.30, 0.50, 0.16), (0.62, 0.55, 0.36)),
    "st_augustine": ((0.08, 0.16), 0.008, (0.24, 0.44, 0.14), (0.58, 0.52, 0.34)),
    "centipede": ((0.05, 0.12), 0.005, (0.40, 0.52, 0.18), (0.64, 0.56, 0.36)),
    "broomsedge": ((0.5, 1.0), 0.004, (0.45, 0.48, 0.25), (0.78, 0.55, 0.30)),
    "wiregrass": ((0.3, 0.6), 0.002, (0.42, 0.50, 0.26), (0.62, 0.55, 0.35)),
    "fescue_pasture": ((0.15, 0.45), 0.005, (0.28, 0.46, 0.18), (0.40, 0.46, 0.25)),
}

BIOME_GRASS = {
    "lawn": {"st_augustine": 0.5, "bermuda": 0.3, "centipede": 0.2},
    "pasture": {"fescue_pasture": 0.6, "broomsedge": 0.25, "bermuda": 0.15},
    "pine_savanna": {"wiregrass": 0.7, "broomsedge": 0.3},
    "hardwood": {"broomsedge": 0.3, "fescue_pasture": 0.7},
    "swamp": {"fescue_pasture": 1.0},
    "old_field": {"broomsedge": 0.7, "fescue_pasture": 0.3},
}


def grass_density(hf, trail_G, canopy, water=None):
    slope = hf.layers["slope"]
    water = hf.layers["water"] if water is None else water
    d = 1.0 - 0.75 * np.clip(canopy, 0, 1)
    d *= np.clip(1.0 - (slope - 25) / 20, 0, 1)
    d *= 1.0 - np.clip(water * 1.5, 0, 1)
    d *= 1.0 - np.clip(trail_G * 1.6, 0, 1)
    d *= 0.75 + 0.25 * hf.layers["moisture"]
    return np.clip(d, 0, 1)


def terrain_mesh(hf, density, trail_G, canopy, signs=(), season="summer", grass_rgb=(0.32, 0.48, 0.18),
                 litter=0.0) -> Mesh:
    p = PROVINCES[hf.province]
    ny, nx = hf.z.shape
    xs = hf.origin[0] + np.arange(nx) * hf.res
    ys = hf.origin[1] + np.arange(ny) * hf.res
    X, Y = np.meshgrid(xs, ys)
    pos = np.stack([X, Y, hf.z], -1).reshape(-1, 3)
    soil = np.array(p["soil"])
    soil2 = np.array(p["soil2"])
    r = make_rng("soil", hf.province)
    mott = ndimage.gaussian_filter(r.uniform(0, 1, hf.z.shape), 1.5)
    mott = (mott - mott.min()) / max(np.ptp(mott), 1e-9)
    base = soil * (1 - mott[..., None]) + soil2 * mott[..., None]
    g = np.array(grass_rgb)
    if season == "winter":
        g = np.array([0.60, 0.53, 0.35])
    elif season == "fall":
        g = g * 0.6 + np.array([0.62, 0.53, 0.30]) * 0.4
    gn = 0.85 + 0.3 * ndimage.gaussian_filter(r.uniform(0, 1, hf.z.shape), 3)
    col = base * (1 - density[..., None]) + (g * gn[..., None]) * density[..., None]
    # leaf litter / pine straw under canopy
    lit = np.array([0.42, 0.30, 0.18])
    lc = np.clip(canopy * (0.6 + litter), 0, 0.85)[..., None]
    col = col * (1 - lc) + lit * lc
    # packed trail soil (slightly darker, compacted)
    tg = np.clip(trail_G * 1.3, 0, 1)[..., None]
    col = col * (1 - tg) + soil * 0.85 * tg
    w = hf.layers["water"][..., None]
    col = col * (1 - w) + np.array([0.20, 0.27, 0.22]) * w  # tannin-dark creek water
    for s in signs:  # digs, scratches, beds
        i = int(round((s["y"] - hf.origin[1]) / hf.res))
        j = int(round((s["x"] - hf.origin[0]) / hf.res))
        if 0 <= i < ny and 0 <= j < nx:
            if s["type"] in ("armadillo_dig", "turkey_scratch", "acorn_cache"):
                col[i, j] = soil2 * 0.7
            elif s["type"] == "deer_bed":
                col[i, j] = col[i, j] * 0.8 + np.array([0.55, 0.50, 0.35]) * 0.2
    idx = []
    k = np.arange((ny - 1) * (nx - 1))
    ii, jj = k // (nx - 1), k % (nx - 1)
    a = ii * nx + jj
    idx = np.concatenate([np.c_[a, a + 1, a + nx], np.c_[a + 1, a + nx + 1, a + nx]])
    return Mesh(pos.astype(np.float32), col.reshape(-1, 3).astype(np.float32), idx.astype(np.uint32))


def ground_weights(hf, density, trail_G, canopy, litter=0.2, seed=0):
    """Per-vertex splat weights a = (litter, soil, grass, mud), summing to 1 (see textures.SPLAT_LAYERS).

    litter = clip(c (0.6 + l)) (1 - g)          under canopy, off trails
    soil   = max(g, clip((s - 25)/20)) + 0.25 (1 - d)(1 - c)   trodden paths, steep and bare ground
    grass  = d (1 - 0.8 c)(1 - g)                open, grassy ground
    mud    = clip(2 (W * N_2)) (1 - clip(s/45))  creek banks (water blurred by a 2 m Gaussian)
    with g = clip(1.3 G), then jittered by low-frequency noise (amplitude 0.12) so edges wander.
    """
    slope = hf.layers["slope"]
    water = hf.layers["water"]
    g = np.clip(trail_G * 1.3, 0, 1)
    c = np.clip(canopy, 0, 1)
    a = np.stack([
        np.clip(c * (0.6 + litter), 0, 1) * (1 - g),
        np.maximum(g, np.clip((slope - 25) / 20, 0, 1)) + 0.25 * (1 - density) * (1 - c),
        density * (1 - 0.8 * c) * (1 - g),
        np.clip(2 * ndimage.gaussian_filter(water, 2.0), 0, 1) * (1 - np.clip(slope / 45, 0, 1)),
    ], -1)
    r = make_rng("ground_weights", seed)
    jit = np.stack([ndimage.gaussian_filter(r.uniform(-1, 1, hf.z.shape), 4) for _ in range(4)], -1)
    a = np.clip(a + 0.12 * jit / max(np.abs(jit).max(), 1e-9), 0, None) + 1e-4
    return (a / a.sum(-1, keepdims=True)).reshape(-1, 4).astype(np.float32)


def grass_mesh(hf, density, region, budget=40000, mix=None, seed=0, season="summer", trail=None) -> Mesh:
    """Individual grass blades inside `region` (x0, y0, x1, y1), placed by density."""
    mix = mix or BIOME_GRASS["lawn"]
    r = make_rng("grass", seed, region)
    x0, y0, x1, y1 = region
    n = budget * 3
    x = r.uniform(x0, x1, n)
    y = r.uniform(y0, y1, n)
    keep = r.uniform(0, 1, n) < _sample(hf, density, x, y)
    x, y = x[keep][:budget], y[keep][:budget]
    n = len(x)
    if n == 0:
        return Mesh.empty()
    keys = list(mix)
    kind = r.choice(len(keys), n, p=np.array([mix[k] for k in keys]) / sum(mix.values()))
    z = hf.sample(x, y)
    h = np.empty(n)
    wdt = np.empty(n)
    col = np.empty((n, 3))
    for ki, k in enumerate(keys):
        (h0, h1), w, summer, dormant = GRASSES[k]
        m = kind == ki
        h[m] = r.uniform(h0, h1, m.sum())
        wdt[m] = w * r.uniform(0.7, 1.3, m.sum())
        c = np.array(dormant if season == "winter" else summer)
        if season == "fall":
            c = 0.6 * np.array(summer) + 0.4 * np.array(dormant)
        col[m] = c * r.uniform(0.75, 1.2, (m.sum(), 1))
    # blades are drawn ~4x wider than life at default budget so a patch reads as turf;
    # at detail="cm" (budget in the millions) set widen=1.
    widen = float(np.clip(np.sqrt(4e5 / max(budget, 1)), 1.0, 5.0))
    ang = r.uniform(0, 2 * np.pi, n)
    bend = r.uniform(0.15, 0.6, n)  # tip displacement as a fraction of height
    if trail is not None:  # trampled: shorter, bent over, lying along the direction of travel (⟂ ∇G)
        g = np.clip(_sample(hf, trail, x, y) * 1.4, 0, 1)
        gy_, gx_ = np.gradient(ndimage.gaussian_filter(trail, 1.0))
        tx, ty = -_sample(hf, gy_, x, y), _sample(hf, gx_, x, y)
        along = np.arctan2(ty, tx) + np.where(r.uniform(0, 1, n) < 0.5, 0, np.pi)
        has = np.hypot(tx, ty) > 1e-4
        ang = np.where(has & (g > 0.15), ang * (1 - g) + along * g, ang)
        h = h * (1 - 0.65 * g)
        bend = bend + (0.95 - bend) * g
    # curved blade: 2 segments (5 vertices; 3 cost +2.7 MB per scene), quadratic bend p(t) = base + up·h·t·(1 − 0.5 b² t) + dir·h·b·t², width w(1 − t)
    ts = np.array([0.0, 0.5, 1.0])
    dirv = np.c_[np.cos(ang), np.sin(ang), np.zeros(n)]
    side = np.c_[np.cos(ang + np.pi / 2), np.sin(ang + np.pi / 2), np.zeros(n)] * (wdt * widen / 2)[:, None]
    base = np.c_[x, y, z - 0.01]
    pts = []
    for t in ts:
        c = base + np.c_[np.zeros(n), np.zeros(n), h * t * (1 - 0.5 * bend ** 2 * t)] + dirv * (h * bend * t * t)[:, None]
        wv = (1 - t) * side
        pts += [c - wv, c + wv] if t < 1 else [c]
    P = np.stack(pts, 1).reshape(-1, 3)  # 5 vertices per blade: 2 pairs + tip
    shade = np.array([0.7, 0.7, 0.9, 0.9, 1.08])  # darker at the base, lit at the tip
    C = (col[:, None, :] * shade[None, :, None]).reshape(-1, 3)
    k = (np.arange(n) * 5)[:, None]
    idx = np.concatenate([k + [0, 1, 3], k + [0, 3, 2], k + [2, 3, 4]])
    return Mesh(P.astype(np.float32), np.clip(C, 0, 1).astype(np.float32), idx.astype(np.uint32))


def _sample(hf, arr, x, y):
    gx, gy = hf.to_grid(x, y)
    return ndimage.map_coordinates(arr, [gy, gx], order=1, mode="nearest")

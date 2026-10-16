"""Creeks as channels, not cells: traced, sized by the water they carry, meandered, graded and cut in.

1. Trace: depressions are filled first (Priority-Flood + ε, Barnes et al. 2014) so no pit ends a creek; D8 receivers give every cell one downhill neighbour. Cells draining A ≥ A_c cells are channel;
   each channel head (no channel donor) is walked downstream until it reaches the outlet or a reach traced
   before it (a junction), so the network becomes polylines that join instead of loose cells.
2. Size (hydraulic geometry, Leopold & Maddock 1953; FMG grows rivers with flux^0.7 instead):
       w = w_0 (A / A_c)^0.5,   d = d_0 (A / A_c)^0.4
3. Meander: a sine-generated curve (Langbein & Leopold 1966) with Kinoshita's skew and flattening terms,
       θ(s) = θ_0 sin(ks) + θ_0³ (J_s cos 3ks − J_f sin 3ks),   k = 2π/λ,  λ = 11 w̄
   (J_s = 1/32, J_f = 1/192 after Abad & Garcia 2009), integrated to a lateral offset y(s) = ∫ sin θ ds.
   θ_0 = θ_min + (θ_max − θ_min) · clip(1 − S/S_max) with θ_min = 20°, θ_max = 80°, S_max = 0.08: steep
   mountain branches wander a little, flat-country creeks loop.
4. Grade: bank-full level z_b(s) = cumulative minimum, downstream, of the terrain smoothed along the reach,
   so no reach runs uphill; tributaries are ramped to the bed they join.
5. Cut: with r the distance to the centreline, z ← min(z, z_b − d (1 − (2r/w)²)) inside the channel and
   z ← min(z, z_b + (r − w/2) · 0.6) on the banks, faded back to the terrain by a smoothstep over w + 2 m. Water stands at z_b − 0.4 d, wetted out to r < 0.39 w.
See docs/TECHNIQUES.md §21.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from ..rng import rng as make_rng

OFFS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
W0, D0 = 1.2, 0.35           # m, width and depth of a creek right at the channel threshold
W_MAX, D_MAX = 9.0, 1.6
THETA_MAX = np.radians(80)   # meander angle on flat ground (Abad & Garcia use up to 110°)
THETA_MIN = np.radians(20)   # steep step-pool creeks still wander between rocks
S_MAX = 0.08                 # channel slope (m/m) above which a reach runs straight
JS, JF = 1 / 32, 1 / 192     # Kinoshita skewness and flatness
BANK = 0.6                   # bank slope (m/m) the cut blends back to the terrain with
STAGE = 0.6                  # water fills this fraction of the depth


def priority_flood(z, eps=1e-3):
    """Fill depressions so every cell drains to the tile edge (Priority-Flood + ε, Barnes, Lehman & Mulla 2014):
    grow inward from the border in order of height; each newly reached cell is raised to at least
        z'(n) = max(z(n), z'(c) + ε)
    for the cell c it was reached from. Pits become gently sloping flats that route water out."""
    import heapq
    ny, nx = z.shape
    out = np.asarray(z, float).copy()
    closed = np.zeros(z.shape, bool)
    closed[[0, -1], :] = closed[:, [0, -1]] = True
    heap = [(out[i, j], i, j) for i, j in zip(*np.nonzero(closed))]
    heapq.heapify(heap)
    while heap:
        h, i, j = heapq.heappop(heap)
        for a, b in OFFS:
            u, v = i + a, j + b
            if 0 <= u < ny and 0 <= v < nx and not closed[u, v]:
                closed[u, v] = True
                if out[u, v] < h + eps:
                    out[u, v] = h + eps
                heapq.heappush(heap, (out[u, v], u, v))
    return out


JITTER = 0.35  # relative slope jitter for D8 (see receivers)


def routing_surface(z, eps=1e-3, kappa=0.3):
    """Surface water is routed over: pits filled (priority_flood), then each filled flat tilted toward its own
    centreline, after Garbrecht & Martz (1997) "away from higher terrain":
        z_r = PF(PF(z) − κ ε · d_edge),   κ = 0.3
    d_edge = distance to the flat's rim. Without it, flow across a filled pond runs in parallel lines that
    never meet, drawing a fan of creeks; κ < 1 keeps the outlet gradient ε dominant, so no new pits form."""
    filled = priority_flood(z, eps)
    flat = filled - z > eps / 2
    if not flat.any():
        return filled
    d = ndimage.distance_transform_edt(flat)
    return priority_flood(filled - kappa * eps * d, eps)


def receivers(z, seed=None):
    """Flat index of each cell's steepest-descent D8 neighbour, −1 at pits and the tile edge outflow.

    Plain D8 snaps flow to 8 directions, so a valley trending 10° off an axis drains in a dead-straight
    grid line. With a seed, each candidate slope is scaled by (1 + ε), ε ~ U(−0.35, 0.35) keyed per cell and
    direction (jittered D8, in the spirit of Fairfield & Leymarie's Rho8): neighbouring cells pick different
    near-best directions and the route follows the true aspect on average."""
    ny, nx = z.shape
    dist = np.array([np.hypot(a, b) for a, b in OFFS])
    pad = np.pad(z, 1, mode="edge")
    stack = np.stack([pad[1 + a:1 + a + ny, 1 + b:1 + b + nx] for a, b in OFFS])
    drop = (z[None] - stack) / dist[:, None, None]
    if seed is not None:
        drop = drop * (1 + make_rng("d8_jitter", seed).uniform(-JITTER, JITTER, drop.shape))
    best = np.argmax(drop, axis=0)
    ii, jj = np.indices(z.shape)
    ti = ii + np.array([o[0] for o in OFFS])[best]
    tj = jj + np.array([o[1] for o in OFFS])[best]
    ok = (np.max(drop, axis=0) > 0) & (ti >= 0) & (ti < ny) & (tj >= 0) & (tj < nx)
    tgt = np.full(z.shape, -1, np.int64)
    tgt[ok] = (ti * nx + tj)[ok]
    return tgt.ravel()


def accumulate(z, seed=None):
    """D8 flow accumulation: cells draining through each cell (itself included), over receivers(z, seed)."""
    tgt = receivers(z, seed)
    acc = np.ones(z.size)
    for idx in np.argsort(z, axis=None)[::-1]:  # high → low
        t = tgt[idx]
        if t >= 0:
            acc[t] += acc[idx]
    return acc.reshape(z.shape)


def trace(z, acc, a_c, min_len=20, margin=3, seed=None):
    """Channel polylines as lists of flat cell indices, head → junction/outlet, longest-first.
    Channels stop `margin` cells short of the tile edge, where edge padding makes water run along the border."""
    tgt = receivers(z, seed)
    inner = np.zeros(z.shape, bool)
    inner[margin:-margin, margin:-margin] = True
    ch = (acc.ravel() >= a_c) & inner.ravel()
    cells = np.nonzero(ch)[0]
    fed = np.zeros(ch.size, bool)
    t = tgt[cells]
    fed[t[(t >= 0)][ch[t[t >= 0]]]] = True
    heads = cells[~fed[cells]]
    heads = heads[np.argsort(-z.ravel()[heads])]  # highest first, so the long stems claim the valley floor
    owner = np.full(ch.size, -1)
    lines = []
    for h in heads:
        line, c = [], h
        while c >= 0 and ch[c] and owner[c] < 0:
            line.append(c)
            owner[c] = len(lines)
            c = tgt[c]
        joins = int(c) if c >= 0 and owner[c] >= 0 else -1
        if joins >= 0:
            line.append(joins)  # end on the reach it joins
        if len(line) >= min_len or joins >= 0 and len(line) >= 3:
            lines.append((np.array(line), joins))
        else:
            owner[line[:-1] if joins >= 0 else line] = -1
    return _prune_parallel(lines, acc.ravel(), z.shape[1])


def _prune_parallel(lines, acc, nx, near=6.0, frac=0.4):
    """Drop a line that runs within `near` cells of a bigger kept line for more than `frac` of its length
    (flow spreading over a fan or valley floor in parallel threads: one valley, one creek)."""
    from scipy.spatial import cKDTree
    order = sorted(range(len(lines)), key=lambda i: -acc[lines[i][0]].max())
    kept, pts = [], np.zeros((0, 2))
    for i in order:
        cells, joins = lines[i]
        xy = np.c_[cells % nx, cells // nx].astype(float)
        if len(pts):
            d, _ = cKDTree(pts).query(xy[:-8] if joins >= 0 and len(xy) > 12 else xy)
            if (d < near).mean() > frac:
                continue
        kept.append(i)
        pts = np.vstack([pts, xy])
    return [lines[i] for i in sorted(kept)]


def geometry(acc, a_c):
    """Hydraulic geometry: (width, depth) in metres for drainage area `acc` (cells)."""
    q = np.maximum(np.asarray(acc, float) / a_c, 1.0)
    return np.minimum(W0 * q ** 0.5, W_MAX), np.minimum(D0 * q ** 0.4, D_MAX)


def _chaikin(p, iters=2):
    for _ in range(iters):
        a, b = p[:-1], p[1:]
        mid = np.stack([0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b], 1).reshape(-1, p.shape[1])
        p = np.vstack([p[:1], mid, p[-1:]])
    return p


def _resample(p, step):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]
    t = np.arange(0, s[-1] + 1e-9, step)
    if t[-1] < s[-1] - 1e-6:
        t = np.r_[t, s[-1]]
    return np.stack([np.interp(t, s, p[:, k]) for k in range(p.shape[1])], 1), t


def meander_offset(s, w, slope, phase, skew=1.0):
    """Lateral offset y(s) of a sine-generated (Kinoshita) curve; zero at both ends."""
    lam = 11.0 * float(np.mean(w))
    k = 2 * np.pi / lam
    th0 = THETA_MIN + (THETA_MAX - THETA_MIN) * np.clip(1 - slope / S_MAX, 0, 1)
    u = k * s + phase
    theta = th0 * np.sin(u) + th0 ** 3 * (skew * JS * np.cos(3 * u) - JF * np.sin(3 * u))
    ds = np.gradient(s)
    y = np.cumsum(np.sin(theta) * ds)
    y -= ndimage.gaussian_filter1d(y, lam / max(ds.mean(), 1e-9) / 2, mode="nearest")  # no drift
    L = s[-1] if len(s) else 0.0
    ramp = np.clip(np.minimum(s, L - s) / (lam / 2), 0, 1)
    return y * ramp * ramp * (3 - 2 * ramp)


def build(hf, acc, a_c, seed=0, extra=(), step=0.5, network=True, routed=None):
    """Trace, size, meander and grade the network. `extra` adds (xy (N,2), flux (N,)) reaches, e.g. a bayou
    laid out by the province. Returns a list of reaches: dict(xy, s, w, d, zb, line)."""
    z = hf.z
    ny, nx = z.shape
    reaches = []
    placed = {}  # flat cell → (reach id, sample index), to snap tributary mouths onto the meandered stem
    r = make_rng("meander", seed)
    raw = [(np.c_[(c % nx) * hf.res + hf.origin[0], (c // nx) * hf.res + hf.origin[1]], acc.ravel()[c], c, j)
           for c, j in (trace(z if routed is None else routed, acc, a_c, seed=seed) if network else [])]
    raw += [(np.asarray(xy, float), np.asarray(f, float), None, -1) for xy, f in extra]
    for xy, flux, cells, joins in raw:
        p = np.c_[xy, flux]
        if cells is not None and len(p) > 4:  # D8 lines are stair-stepped: smooth them, ends pinned
            sm = ndimage.gaussian_filter1d(p[:, :2], 2.0, axis=0, mode="nearest")
            k = np.minimum(np.arange(len(p)), np.arange(len(p))[::-1])
            f = np.clip(k / 3.0, 0, 1)[:, None]
            p[:, :2] = p[:, :2] * (1 - f) + sm * f
        p = _chaikin(p, 2)
        p, s = _resample(p, step)
        if len(s) < 3:
            continue
        w, d = geometry(p[:, 2], a_c)
        zt = ndimage.gaussian_filter1d(hf.sample(p[:, 0], p[:, 1]), 4 / step, mode="nearest")
        slope = np.clip(-np.gradient(zt, s), 0, None) if cells is not None else np.zeros_like(s)
        slope = ndimage.gaussian_filter1d(slope, 10 / step, mode="nearest")
        t = np.gradient(p[:, :2], axis=0)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
        nrm = np.c_[-t[:, 1], t[:, 0]]
        y = meander_offset(s, w, slope, r.uniform(0, 2 * np.pi), r.choice([-1.0, 1.0]))
        q = p[:, :2] + nrm * y[:, None]
        zb = np.minimum.accumulate(ndimage.gaussian_filter1d(hf.sample(q[:, 0], q[:, 1]), 4 / step, mode="nearest"))
        if joins >= 0 and joins in placed:  # tributary: end on the stem's meandered bank-full point
            rid, k = placed[joins]
            tq, tz = reaches[rid]["xy"][k], reaches[rid]["zb"][k]
            ramp = np.clip(1 - (s[-1] - s) / max(min(s[-1], 20.0), 1e-9), 0, 1)
            q = q + (tq - q[-1]) * ramp[:, None]
            zb = np.minimum(zb, tz + 0.02 * (s[-1] - s))
        rid = len(reaches)
        if cells is not None:  # remember where each traced cell landed
            src = np.c_[(cells % nx) * hf.res + hf.origin[0], (cells // nx) * hf.res + hf.origin[1]]
            k = np.argmin(((p[None, :, :2] - src[:, None, :]) ** 2).sum(-1), axis=1)
            for c, kk in zip(cells[:-1] if joins >= 0 else cells, k):
                placed.setdefault(int(c), (rid, int(kk)))
        reaches.append(dict(xy=q, s=s, w=w, d=d, zb=zb, line=rid))
    return reaches


def carve(hf, reaches):
    """Cut the reaches into a copy of hf.z. Returns (z, water mask, stage grid)."""
    z0 = hf.z
    ny, nx = z0.shape
    if not reaches:
        return z0.copy(), np.zeros_like(z0), np.zeros_like(z0)
    xy = np.concatenate([q["xy"] for q in reaches])
    w = np.concatenate([q["w"] for q in reaches])
    d = np.concatenate([q["d"] for q in reaches])
    zb = np.concatenate([q["zb"] for q in reaches])
    # exact distance to the nearest centreline sample (KD-tree; samples are 0.5 m apart, under the 1 m grid)
    from scipy.spatial import cKDTree
    ii, jj = np.indices(z0.shape)
    pts = np.c_[jj.ravel() * hf.res + hf.origin[0], ii.ravel() * hf.res + hf.origin[1]]
    reach = float(w.max() * 1.5 + 2.0)
    dist, k = cKDTree(xy).query(pts, distance_upper_bound=reach)
    near = np.isfinite(dist)
    z = z0.ravel().copy()
    stage = np.zeros(z.size)
    water = np.zeros(z.size)
    kk = k[near]
    rr, ww, dd, bb = dist[near], w[kk], d[kk], zb[kk]
    inside = rr <= ww / 2
    bed = bb - dd * (1 - (2 * rr / ww) ** 2)
    bank = bb + (rr - ww / 2) * BANK
    cut = np.minimum(z[near], np.where(inside, bed, bank))
    u = np.clip((rr - ww / 2) / (ww + 2.0), 0, 1)  # banks fade back to the untouched slope within w + 2 m
    fade = 1 - u * u * (3 - 2 * u)
    z[near] = z[near] + (cut - z[near]) * fade
    lvl = bb - (1 - STAGE) * dd
    wet = rr < ww / 2 * np.sqrt(STAGE)
    wet_idx = np.nonzero(near)[0][wet]
    water[wet_idx] = 1.0
    stage[wet_idx] = lvl[wet]
    return z.reshape(z0.shape), water.reshape(z0.shape), stage.reshape(z0.shape)


def to_array(reaches):
    """Pack reaches as (N, 7) float32 rows x, y, stage, wetted width, line id, s, depth — for the asset library."""
    if not reaches:
        return np.zeros((0, 7), np.float32)
    rows = [np.c_[q["xy"], q["zb"] - (1 - STAGE) * q["d"], q["w"] * np.sqrt(STAGE), np.full(len(q["s"]), q["line"]),
                  q["s"], q["d"]] for q in reaches]
    return np.concatenate(rows).astype(np.float32)


def unpack(packed, step=None):
    """Reaches back from to_array (for re-cutting at finer spacing), optionally resampled every `step` m."""
    if packed is None or len(packed) == 0 or packed.shape[1] < 7:
        return []
    out = []
    for rid in np.unique(packed[:, 4]):
        q = packed[packed[:, 4] == rid]
        q = q[np.argsort(q[:, 5])].astype(float)
        cols = q[:, [0, 1, 2, 3, 6]]
        if step:
            cols, _ = _resample(cols, step)
        w, d = cols[:, 3] / np.sqrt(STAGE), cols[:, 4]
        out.append(dict(xy=cols[:, :2], w=w, d=d, zb=cols[:, 2] + (1 - STAGE) * d, line=int(rid),
                        s=np.r_[0, np.cumsum(np.linalg.norm(np.diff(cols[:, :2], axis=0), axis=1))]))
    return out


def water_mesh(packed, rgb=(0.18, 0.26, 0.24), over=1.15, step=1.0):
    """Water surface ribbons along packed reaches (see to_array), flat across at the stage height."""
    from ..mesh import Mesh
    pos, idx, n0 = [], [], 0
    for rid in np.unique(packed[:, 4]) if len(packed) else []:
        q = packed[packed[:, 4] == rid]
        q = q[np.argsort(q[:, 5])]
        q, _ = _resample(q[:, :4].astype(float), step)
        if len(q) < 2:
            continue
        t = np.gradient(q[:, :2], axis=0)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
        nrm = np.c_[-t[:, 1], t[:, 0]]
        across = np.array([-0.5, 0.0, 0.5])
        P = q[:, None, :2] + nrm[:, None, :] * (across[None, :, None] * q[:, None, 3:4] * over)
        Z = np.repeat(q[:, 2:3], 3, 1)
        pos.append(np.dstack([P, Z]).reshape(-1, 3))
        n, m = len(q), 3
        k = (np.arange(n - 1)[:, None] * m + np.arange(m - 1)[None, :]).ravel() + n0
        idx.append(np.concatenate([np.c_[k, k + m, k + 1], np.c_[k + 1, k + m, k + m + 1]]))
        n0 += n * m
    if not pos:
        return None
    P = np.concatenate(pos).astype(np.float32)
    return Mesh(P, np.tile(np.asarray(rgb, np.float32), (len(P), 1)), np.concatenate(idx).astype(np.uint32))

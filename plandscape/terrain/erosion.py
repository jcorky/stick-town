"""Droplet hydraulic erosion, batched in numpy (after Sebastian Lague's Hydraulic-Erosion, MIT).

Thousands of rain droplets run downhill at once. Each picks up sediment while it accelerates
downhill and its capacity exceeds its load, and drops it where it slows, climbs or overloads,
so slopes grow gullies, hollows fill and small fans form where channels flatten out.
See docs/TECHNIQUES.md §14 and catalog/notes/seblague-erosion.md.

Our heights are metres with relief from ~3 m (floodplain) to ~120 m (ridges); the algorithm's
constants assume heights in 0..1, so the tile is normalised to [0, 1] first and scaled back.
"""

from __future__ import annotations

import numpy as np

from ..rng import rng as make_rng


def _brush(radius):
    """Offsets with x² + y² < r² and weights w = 1 − d/r, normalised to sum 1."""
    o = [(dy, dx) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)
         if dy * dy + dx * dx < radius * radius]
    d = np.array([np.hypot(dy, dx) for dy, dx in o])
    w = np.maximum(1 - d / radius, 0)
    return np.array(o), w / w.sum()


def droplet_erosion(z, seed=0, droplets_per_cell=0.5, batch=2048, lifetime=30, inertia=0.4, capacity=4.0,
                    min_capacity=0.01, erode=0.3, deposit=0.3, evaporate=0.01, gravity=4.0, radius=5,
                    strength=1.0):
    """Return an eroded copy of heightfield `z` (2-D array, any units).

    Defaults differ from Lague's (r 3, inertia .05–.3, ~0.75 droplets/cell): at our 1 m cells those
    carve hair-fine rills; r = 5, inertia 0.4 and 0.5 droplets/cell give ravine-scale gullies.

    Per droplet step, with p the position, d the direction, v speed, w water, s sediment:
      g  = bilinear gradient at p          d ← normalise(d·inertia − g·(1 − inertia)),  p ← p + d
      Δh = h(p_new) − h(p_old)             c  = max(−Δh·v·w·capacity, min_capacity)
      if s > c or Δh > 0: deposit  (Δh > 0 ? min(Δh, s) : (s − c)·deposit)  bilinearly at p_old
      else:               erode    min((c − s)·erode, −Δh)  over a radius-r brush around p_old
      v ← sqrt(max(0, v² + Δh·gravity)),   w ← w·(1 − evaporate)
    """
    z = np.asarray(z, np.float64)
    lo, H = float(z.min()), float(np.ptp(z))
    if H < 1e-9:
        return z.copy()
    ny, nx = z.shape
    r = radius
    zn = np.pad((z - lo) / H, r, mode="edge")  # pad so brush indices stay in bounds
    NY, NX = zn.shape
    flat = zn.ravel()  # view: writes go to zn
    offs, bw = _brush(r)
    boff = offs[:, 0] * NX + offs[:, 1]
    rng = make_rng("droplets", seed)
    total = int(droplets_per_cell * ny * nx)
    for b0 in range(0, total, batch):
        B = min(batch, total - b0)
        px = rng.uniform(r, r + nx - 1.001, B)
        py = rng.uniform(r, r + ny - 1.001, B)
        dx = np.zeros(B)
        dy = np.zeros(B)
        v = np.ones(B)
        w = np.ones(B)
        s = np.zeros(B)
        alive = np.ones(B, bool)
        for _ in range(lifetime):
            if not alive.any():
                break
            ix, iy = px.astype(np.int64), py.astype(np.int64)
            fx, fy = px - ix, py - iy
            i00 = iy * NX + ix
            hNW, hNE, hSW, hSE = flat[i00], flat[i00 + 1], flat[i00 + NX], flat[i00 + NX + 1]
            gx = (hNE - hNW) * (1 - fy) + (hSE - hSW) * fy
            gy = (hSW - hNW) * (1 - fx) + (hSE - hNE) * fx
            h0 = hNW * (1 - fx) * (1 - fy) + hNE * fx * (1 - fy) + hSW * (1 - fx) * fy + hSE * fx * fy
            dx = dx * inertia - gx * (1 - inertia)
            dy = dy * inertia - gy * (1 - inertia)
            ln = np.maximum(np.hypot(dx, dy), 0.01)
            dx, dy = dx / ln, dy / ln
            nxp, nyp = px + dx, py + dy
            inside = (nxp >= r) & (nxp < r + nx - 1) & (nyp >= r) & (nyp < r + ny - 1)
            alive &= inside
            if not alive.any():
                break
            jx = np.clip(nxp, r, r + nx - 1.001)
            jy = np.clip(nyp, r, r + ny - 1.001)
            kx, ky = jx.astype(np.int64), jy.astype(np.int64)
            gx2, gy2 = jx - kx, jy - ky
            j00 = ky * NX + kx
            h1 = (flat[j00] * (1 - gx2) * (1 - gy2) + flat[j00 + 1] * gx2 * (1 - gy2)
                  + flat[j00 + NX] * (1 - gx2) * gy2 + flat[j00 + NX + 1] * gx2 * gy2)
            dh = h1 - h0
            cap = np.maximum(-dh * v * w * capacity, min_capacity)
            dep_mask = alive & ((s > cap) | (dh > 0))
            ero_mask = alive & ~dep_mask
            # deposit, bilinear on the four corners of the old cell
            amt = np.where(dh > 0, np.minimum(dh, s), (s - cap) * deposit) * dep_mask
            s -= amt
            corners = np.concatenate([i00, i00 + 1, i00 + NX, i00 + NX + 1])
            cw = np.concatenate([(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy]) * np.tile(amt, 4)
            flat += np.bincount(corners, cw, minlength=flat.size) * strength
            # erode over the brush, never below a node's own height (heights are >= 0 here)
            amt = np.minimum((cap - s) * erode, -dh) * ero_mask
            amt = np.maximum(amt, 0)
            nodes = (i00[:, None] + boff[None, :]).ravel()
            want = (amt[:, None] * bw[None, :]).ravel()
            take = np.minimum(want, flat[nodes])
            flat -= np.bincount(nodes, take, minlength=flat.size) * strength
            s += take.reshape(B, -1).sum(1)
            v = np.sqrt(np.maximum(0.0, v * v + dh * gravity))
            w *= 1 - evaporate
            px = np.where(alive, nxp, px)
            py = np.where(alive, nyp, py)
    out = zn[r:r + ny, r:r + nx] * H + lo
    return out

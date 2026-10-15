"""Desire paths via the active-walker model (Helbing, Keltsch & Molnár, Nature 1997).

Walkers travel between attractors (doors, mailboxes, a creek ford, a shady
oak). Each step they head toward their destination but are pulled toward
ground that is already trampled (it's easier to walk on). Footsteps deposit
"trail" G; untrodden ground recovers toward G0 over time. Shortcuts emerge,
merge and stabilise exactly the way real desire lines do, and obstacles
(steep slopes, water, trunks, buildings) are routed around.

The same field is reused by the fauna sim, so deer that follow game trails
reinforce them — human and animal paths share one ground memory.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from ..rng import rng as make_rng


@dataclass
class TrailField:
    G: np.ndarray          # trail strength (0 = pristine, 1 = bare packed soil)
    res: float
    origin: tuple

    def to_grid(self, x, y):
        return (np.asarray(x) - self.origin[0]) / self.res, (np.asarray(y) - self.origin[1]) / self.res

    def deposit(self, x, y, amount, gmax=1.0):
        gx, gy = self.to_grid(x, y)
        i = np.clip(np.round(gy).astype(int), 0, self.G.shape[0] - 1)
        j = np.clip(np.round(gx).astype(int), 0, self.G.shape[1] - 1)
        np.add.at(self.G, (i, j), amount * (1.0 - self.G[i, j] / gmax))

    def sample(self, x, y, arr=None):
        gx, gy = self.to_grid(x, y)
        return ndimage.map_coordinates(self.G if arr is None else arr,
                                       [np.atleast_1d(gy), np.atleast_1d(gx)], order=1, mode="nearest")


def obstacle_cost(hf, trunks=(), footprints=()):
    """0 = free, 1 = impassable. Slope, water, trunks and building footprints."""
    slope = hf.layers["slope"]
    c = np.clip((slope - 18.0) / 20.0, 0, 1)
    c = np.maximum(c, hf.layers["water"] * 0.85)
    ny, nx = c.shape
    yy, xx = np.indices(c.shape)
    for (x, y, rad) in trunks:
        gx, gy = (x - hf.origin[0]) / hf.res, (y - hf.origin[1]) / hf.res
        r = max(rad / hf.res, 0.6) + 0.5
        sl = (slice(max(0, int(gy - r - 1)), min(ny, int(gy + r + 2))),
              slice(max(0, int(gx - r - 1)), min(nx, int(gx + r + 2))))
        d = np.hypot(xx[sl] - gx, yy[sl] - gy)
        c[sl] = np.maximum(c[sl], (d <= r).astype(float))
    for (x0, y0, x1, y1) in footprints:
        i0, i1 = int((y0 - hf.origin[1]) / hf.res), int((y1 - hf.origin[1]) / hf.res) + 1
        j0, j1 = int((x0 - hf.origin[0]) / hf.res), int((x1 - hf.origin[0]) / hf.res) + 1
        c[max(i0, 0):max(i1, 0), max(j0, 0):max(j1, 0)] = 1.0
    return c


def simulate(hf, attractors, n_trips=600, seed=0, cost=None, field: TrailField | None = None,
             step=0.7, visibility=2.5, attraction=1.4, intensity=0.06, recovery=0.002,
             max_steps=1200, record=False):
    """Run walkers between weighted attractors; returns (TrailField, tracks)."""
    r = make_rng("desire", seed)
    if field is None:
        field = TrailField(np.zeros_like(hf.z), hf.res, hf.origin)
    if cost is None:
        cost = obstacle_cost(hf)
    pts = np.array([(a[0], a[1]) for a in attractors], float)
    w = np.array([a[2] if len(a) > 2 else 1.0 for a in attractors], float)
    w = w / w.sum()
    cgy, cgx = np.gradient(ndimage.gaussian_filter(cost, 1.0))
    tracks = []
    sigma = visibility / hf.res
    batch = 24  # walkers advance in lockstep for speed
    for b0 in range(0, n_trips, batch):
        V = ndimage.gaussian_filter(field.G, sigma)  # comfort: what walkers "see"
        vgy, vgx = np.gradient(V)
        field.G -= recovery * batch * field.G        # vegetation regrowth
        k = min(batch, n_trips - b0)
        ab = np.array([r.choice(len(pts), 2, replace=False, p=w) for _ in range(k)])
        p = pts[ab[:, 0]] + r.normal(0, 0.6, (k, 2))
        dest = pts[ab[:, 1]] + r.normal(0, 0.3, (k, 2))
        live = np.ones(k, bool)
        tr = [[q.copy()] for q in p] if record else None
        for _ in range(max_steps):
            if not live.any():
                break
            to = dest - p
            dist = np.linalg.norm(to, axis=1)
            live &= dist > step * 1.5
            e = to / np.maximum(dist, 1e-9)[:, None]
            g = np.stack([field.sample(p[:, 0], p[:, 1], vgx), field.sample(p[:, 0], p[:, 1], vgy)], 1)
            gn = np.linalg.norm(g, axis=1, keepdims=True)
            e = e + attraction * g / np.maximum(gn, 1e-9) * np.minimum(1.0, gn * 40)
            o = np.stack([field.sample(p[:, 0], p[:, 1], cgx), field.sample(p[:, 0], p[:, 1], cgy)], 1)
            e = e - 6.0 * o + r.normal(0, 0.12, e.shape)
            e /= np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-9)
            prev = p
            p = np.where(live[:, None], p + e * step, p)
            if live.any():  # deposit at the step and its midpoint so trails stay continuous on a 1 m grid
                mid = (prev + p) / 2
                field.deposit(np.r_[p[live, 0], mid[live, 0]], np.r_[p[live, 1], mid[live, 1]], intensity * 0.6)
            if record:
                for i in np.nonzero(live)[0]:
                    tr[i].append(p[i].copy())
        if record:
            tracks += [np.array(t) for t in tr]
    np.clip(field.G, 0, 1, out=field.G)
    return field, tracks

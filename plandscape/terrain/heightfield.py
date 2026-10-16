"""Procedural terrain tiles shaped after Southern physiographic provinces.

World frame: metres, x = east, y = north, z = up. A tile is a regular grid.

Real elevation (USGS 3DEP, ~1 m lidar DEMs in much of the South) is the
intended base layer at production time; `load_dem()` is where that plugs in.
Procedural detail is then synthesised *below* the source resolution, which is
how the project reaches centimetre-scale detail without storing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from .. import noise
from ..rng import derive_seed
from .erosion import droplet_erosion

# Relief and character per province. Numbers are design targets meant to *feel*
# right at tile scale, not survey statistics.
PROVINCES: dict[str, dict] = {
    "coastal_plain": dict(relief=6.0, freq=1 / 700, ridged=0.0, warp=80, plateau=0.0,
                          soil=(0.86, 0.80, 0.66), soil2=(0.62, 0.55, 0.42)),  # pale sands
    "floodplain": dict(relief=2.5, freq=1 / 900, ridged=0.0, warp=120, plateau=0.0,
                       soil=(0.36, 0.30, 0.24), soil2=(0.25, 0.22, 0.18)),  # dark alluvium
    "piedmont": dict(relief=28.0, freq=1 / 450, ridged=0.15, warp=70, plateau=0.0,
                     soil=(0.66, 0.33, 0.20), soil2=(0.55, 0.27, 0.17)),  # red clay
    "cumberland_plateau": dict(relief=90.0, freq=1 / 500, ridged=0.25, warp=60, plateau=1.0,
                               soil=(0.60, 0.42, 0.28), soil2=(0.45, 0.36, 0.28)),  # Monte Sano-like
    "ridge_and_valley": dict(relief=120.0, freq=1 / 420, ridged=0.85, warp=40, plateau=0.0,
                             soil=(0.58, 0.40, 0.27), soil2=(0.44, 0.33, 0.25)),
}


@dataclass
class Heightfield:
    z: np.ndarray            # (ny, nx) elevations, metres
    res: float               # metres per cell
    origin: tuple = (0.0, 0.0)
    province: str = "piedmont"
    layers: dict = field(default_factory=dict)  # slope, moisture, flow, water, ...

    @property
    def shape(self):
        return self.z.shape

    @property
    def size(self):
        ny, nx = self.z.shape
        return ((nx - 1) * self.res, (ny - 1) * self.res)

    def to_grid(self, x, y):
        return ((np.asarray(x) - self.origin[0]) / self.res,
                (np.asarray(y) - self.origin[1]) / self.res)

    def sample(self, x, y, layer: str | None = None):
        arr = self.z if layer is None else self.layers[layer]
        gx, gy = self.to_grid(x, y)
        return ndimage.map_coordinates(arr, [np.atleast_1d(gy), np.atleast_1d(gx)],
                                       order=1, mode="nearest")

    def normal(self, x, y):
        e = self.res
        dzdx = (self.sample(x + e, y) - self.sample(x - e, y)) / (2 * e)
        dzdy = (self.sample(x, y + e) - self.sample(x, y - e)) / (2 * e)
        n = np.stack([-dzdx, -dzdy, np.ones_like(dzdx)], -1)
        return n / np.linalg.norm(n, axis=-1, keepdims=True)


EROSION_STRENGTH = {"floodplain": 0.25, "coastal_plain": 0.5}


def _thermal_erosion(z, res, iters=30, talus_deg=34.0, rate=0.35):
    talus = np.tan(np.radians(talus_deg)) * res
    for _ in range(iters):
        pad = np.pad(z, 1, mode="edge")
        moved = np.zeros_like(z)
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            nb = pad[1 + dy:1 + dy + z.shape[0], 1 + dx:1 + dx + z.shape[1]]
            d = z - nb
            m = np.where(d > talus, (d - talus) * rate * 0.25, 0.0)
            moved -= m
            moved += np.roll(np.roll(m, dy, 0), dx, 1)
        z = z + moved
    return z


def flow_accumulation(z):
    """D8 flow accumulation (cells draining through each cell)."""
    ny, nx = z.shape
    order = np.argsort(z, axis=None)[::-1]
    acc = np.ones(z.size)
    zf = z.ravel()
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    dist = np.array([np.hypot(a, b) for a, b in offs])
    pad = np.pad(z, 1, mode="edge")
    stack = np.stack([pad[1 + a:1 + a + ny, 1 + b:1 + b + nx] for a, b in offs])
    drop = (z[None] - stack) / dist[:, None, None]
    best = np.argmax(drop, axis=0)
    has = np.max(drop, axis=0) > 0
    tgt = np.full(z.shape, -1, dtype=np.int64)
    ii, jj = np.indices(z.shape)
    ti = ii + np.array([o[0] for o in offs])[best]
    tj = jj + np.array([o[1] for o in offs])[best]
    ok = has & (ti >= 0) & (ti < ny) & (tj >= 0) & (tj < nx)
    tgt[ok] = (ti * nx + tj)[ok]
    tgtf = tgt.ravel()
    for idx in order:  # high → low
        t = tgtf[idx]
        if t >= 0:
            acc[t] += acc[idx]
    _ = zf
    return acc.reshape(z.shape)


def generate_tile(size_m=192.0, res_m=1.0, province="piedmont", seed=0,
                  origin=(0.0, 0.0), creek=True) -> Heightfield:
    p = PROVINCES[province]
    n = int(round(size_m / res_m)) + 1
    xs = origin[0] + np.arange(n) * res_m
    ys = origin[1] + np.arange(n) * res_m
    X, Y = np.meshgrid(xs, ys)
    s = derive_seed("terrain", province, seed) % 10_000
    wx, wy = noise.warp(X * p["freq"], Y * p["freq"], s, strength=p["warp"] * p["freq"])
    base = noise.fbm(wx, wy, s, octaves=6)
    if p["ridged"]:
        rx = noise.ridged(wx * 0.8, wy * 2.2, s + 3, octaves=5)  # anisotropic ridges
        base = (1 - p["ridged"]) * base + p["ridged"] * rx
    if p["plateau"]:
        # mesa: flat cap, steep escarpment, benches (sandstone over limestone)
        t = np.clip((base + 0.15) * 3.0, 0, 1)
        cap = t * t * (3 - 2 * t)
        bench = 0.08 * np.round(base * 6) / 6
        base = 0.8 * cap + bench + 0.12 * base
    z = base * p["relief"]
    # fine micro-relief (roots, rills, ant mounds) — sub-metre detail starts here
    z += 0.08 * noise.fbm(X / 3.0, Y / 3.0, s + 17, octaves=3)
    z = _thermal_erosion(z, res_m, iters=20)
    # rain: gullies on slopes, filled hollows (flat country barely gullies)
    z = droplet_erosion(z, seed=s, strength=EROSION_STRENGTH.get(province, 1.0))

    if creek and province in ("floodplain", "coastal_plain"):
        # flat country: a meandering bayou/branch, since flow routing alone finds no channel
        r = np.random.default_rng(s)
        t = np.linspace(0, 1, 400)
        amp = r.uniform(0.08, 0.18) * size_m
        cy = origin[1] + size_m * r.uniform(0.35, 0.75) + amp * np.sin(2 * np.pi * t * r.uniform(1.2, 2.2) + r.uniform(0, 6)) \
            + 0.05 * size_m * noise.fbm(t * 4, 0.5, s + 5, octaves=3)
        cx = origin[0] + t * size_m
        mask = np.zeros_like(z)
        gi = np.clip(((cy - origin[1]) / res_m).astype(int), 0, n - 1)
        gj = np.clip(((cx - origin[0]) / res_m).astype(int), 0, n - 1)
        mask[gi, gj] = 1.0
        width = r.uniform(2.5, 5.0) / res_m
        mask = ndimage.gaussian_filter(ndimage.binary_dilation(mask, iterations=int(width)).astype(float), 1.0)
        z = z - mask * 1.6
    acc = flow_accumulation(z)
    water = np.zeros_like(z)
    if creek:
        thresh = np.percentile(acc, 99.0)
        channel = ndimage.gaussian_filter((acc > thresh).astype(float), 1.2)
        carve = np.clip(channel * 2.5, 0, 1)
        z = z - carve * min(2.5, 0.05 * p["relief"] + 0.6)
        water = (carve > 0.55).astype(float)
        if province in ("floodplain", "coastal_plain"):
            water = np.maximum(water, (z < np.percentile(z, 4) + 0.3).astype(float) * (mask > 0.5))

    gy, gx = np.gradient(z, res_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    rel = z - ndimage.gaussian_filter(z, 12 / res_m)
    wet = np.log1p(acc) / np.log1p(acc.max())
    moisture = np.clip(0.55 * wet - 0.04 * rel + 0.3 * ndimage.gaussian_filter(water, 6)
                       + 0.25 - 0.006 * slope, 0, 1)
    hf = Heightfield(z=z, res=res_m, origin=origin, province=province)
    hf.layers.update(slope=slope, moisture=moisture, flow=acc, water=water)
    return hf


def load_dem(path: str):  # pragma: no cover - production hook
    """Load a real DEM (e.g. USGS 3DEP 1 m GeoTIFF) as a Heightfield.

    Requires rasterio/GDAL, which aren't in the zero-dependency core.
    See docs/DATA_SOURCES.md for the download flow.
    """
    raise NotImplementedError("Install rasterio and implement 3DEP loading — see docs/DATA_SOURCES.md")

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
from ..rng import rng as make_rng
from . import channels
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
    layers: dict = field(default_factory=dict)  # slope, moisture, flow, water, stage, ...
    channels: np.ndarray = None  # (N, 6) creek centrelines: x, y, stage, wetted width, reach id, s (channels.py)

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


def flow_accumulation(z, seed=None):
    """D8 flow accumulation (cells draining through each cell); see channels.accumulate."""
    return channels.accumulate(z, seed)


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

    flat = province in ("floodplain", "coastal_plain")
    filled = channels.routing_surface(z)  # pits filled, flats tilted, so channels connect (TECHNIQUES §21)
    acc = channels.accumulate(filled, seed=s)
    water, stage, reaches = np.zeros_like(z), np.zeros_like(z), []
    if creek:
        # channels traced, sized by drainage area, meandered and cut in (TECHNIQUES §21). Flat country gets
        # one bayou or branch laid across the tile instead, since flow routing finds no channel there.
        a_c = max(float(np.percentile(acc, 98.8)), 150.0)
        extra = []
        if flat:
            r = make_rng("bayou", s)
            t = np.linspace(0, 1, 200)
            cy = origin[1] + size_m * r.uniform(0.35, 0.65) \
                + 0.07 * size_m * np.sin(2 * np.pi * t * r.uniform(0.5, 1.0) + r.uniform(0, 6)) \
                + 0.04 * size_m * noise.fbm(t * 3, 0.5, s + 5, octaves=3)
            q = r.uniform(16, 36)  # (w / w_0)² for a 4.8–7.2 m bayou
            extra = [(np.c_[origin[0] + t * size_m, cy], np.full(len(t), q * a_c))]
        tmp = Heightfield(z=z, res=res_m, origin=origin, province=province)
        reaches = channels.build(tmp, acc, a_c, seed=s, extra=extra, network=not flat, routed=filled)
        z, water, stage = channels.carve(tmp, reaches)
        acc = channels.accumulate(channels.routing_surface(z), seed=s)

    gy, gx = np.gradient(z, res_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    rel = z - ndimage.gaussian_filter(z, 12 / res_m)
    wet = np.log1p(acc) / np.log1p(acc.max())
    moisture = np.clip(0.55 * wet - 0.04 * rel + 0.3 * ndimage.gaussian_filter(water, 6)
                       + 0.25 - 0.006 * slope, 0, 1)
    hf = Heightfield(z=z, res=res_m, origin=origin, province=province, channels=channels.to_array(reaches))
    hf.layers.update(slope=slope, moisture=moisture, flow=acc, water=water, stage=stage)
    return hf


def load_dem(path: str):  # pragma: no cover - production hook
    """Load a real DEM (e.g. USGS 3DEP 1 m GeoTIFF) as a Heightfield.

    Requires rasterio/GDAL, which aren't in the zero-dependency core.
    See docs/DATA_SOURCES.md for the download flow.
    """
    raise NotImplementedError("Install rasterio and implement 3DEP loading — see docs/DATA_SOURCES.md")

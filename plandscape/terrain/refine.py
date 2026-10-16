"""Near-camera terrain: fine nested grids inside the 1 m tile (a two-level geometry clipmap).

Geometry clipmaps (Losasso & Hoppe 2004; Terrain3D draws its terrain the same way) keep resolution where
the eye is. A scene here is static, so the windows are chosen: the focus patch (grass, props, closeup) and
the creek where it is widest. Inside a window of spacing h (0.25 m at detail low) the height is

    z_f = B(z) + τ · (C(z) − B(z) + m)           then the creeks are cut again at spacing h, also × τ
    m   = A_m · fbm(x/0.9, y/0.9) · (1 − W)      micro relief: roots, clods, ant hills (A_m = 4 cm)
    τ   = smoothstep(min(d_edge / 2 m, 1))        0 on the window border

B is bilinear interpolation (exactly what the 1 m mesh draws along its grid lines), C is cubic B-spline
interpolation (rounder hills), W the water layer. Because τ = 0 on the border and the windows sit on whole
metres, the fine border lies on the coarse mesh's edges: no seam, no skirt. Creek beds and banks use the same
carve as channels.carve, on centrelines resampled every 5 cm, so banks are smooth curves instead of 1 m steps.
See docs/TECHNIQUES.md §22.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from .. import noise
from ..mesh import Mesh
from ..rng import derive_seed
from . import channels

MICRO = 0.04          # m, micro-relief amplitude
BLEND = 2.0           # m, border band over which the fine detail fades in
WINDOW = {"low": (24, 0.25), "med": (32, 0.25), "high": (48, 0.2), "cm": (32, 0.1)}  # (size m, spacing m)


@dataclass
class Patch:
    x0: float
    y0: float
    h: float
    z: np.ndarray        # (n, n) heights
    water: np.ndarray    # (n, n) wetted mask at fine spacing

    @property
    def x1(self):
        return self.x0 + (self.z.shape[1] - 1) * self.h

    @property
    def y1(self):
        return self.y0 + (self.z.shape[0] - 1) * self.h

    def inside(self, x, y):
        return (x >= self.x0) & (x <= self.x1) & (y >= self.y0) & (y <= self.y1)

    def sample(self, x, y):
        return ndimage.map_coordinates(self.z, [(y - self.y0) / self.h, (x - self.x0) / self.h], order=1,
                                       mode="nearest")


def creek_focus(hf):
    """Point of the widest wetted channel in the middle 60 % of the tile, or None."""
    c = hf.channels
    if c is None or not len(c):
        return None
    S = hf.size[0]
    mid = (c[:, 0] > 0.2 * S) & (c[:, 0] < 0.8 * S) & (c[:, 1] > 0.2 * S) & (c[:, 1] < 0.8 * S)
    k = int(np.argmax(np.where(mid, c[:, 3], -1) if mid.any() else c[:, 3]))
    return float(c[k, 0]), float(c[k, 1])


def windows(hf, centre, detail="low"):
    """Whole-metre windows (x0, y0, x1, y1): the focus centre, plus the creek unless the two overlap."""
    size, _ = WINDOW.get(detail, WINDOW["low"])
    S = hf.size[0]

    def box(x, y):
        x0 = float(np.clip(np.round(x - size / 2), hf.origin[0], hf.origin[0] + S - size))
        y0 = float(np.clip(np.round(y - size / 2), hf.origin[1], hf.origin[1] + S - size))
        return (x0, y0, x0 + size, y0 + size)
    out = [box(*centre)]
    cf = creek_focus(hf)
    if cf is not None:
        b = box(*cf)
        a = out[0]
        if b[0] >= a[2] or b[2] <= a[0] or b[1] >= a[3] or b[3] <= a[1]:
            out.append(b)
    return out


def build(hf, wins, h=0.25, seed=0, protect=None):
    """Fine patches for `wins`. `protect` (coarse grid, 0..1) marks ground the creek re-cut must not touch
    (the graded road bed where it fords)."""
    reaches = channels.unpack(hf.channels, step=0.05) if hf.channels is not None else []
    s = derive_seed("micro", seed) % 10_000
    out = []
    for (x0, y0, x1, y1) in wins:
        n = int(round((x1 - x0) / h)) + 1
        xs, ys = x0 + np.arange(n) * h, y0 + np.arange(n) * h
        X, Y = np.meshgrid(xs, ys)
        gx, gy = (X - hf.origin[0]) / hf.res, (Y - hf.origin[1]) / hf.res
        B = ndimage.map_coordinates(hf.z, [gy, gx], order=1, mode="nearest")
        C = ndimage.map_coordinates(hf.z, [gy, gx], order=3, mode="nearest")
        W = ndimage.map_coordinates(hf.layers["water"], [gy, gx], order=1, mode="nearest")
        m = MICRO * noise.fbm(X / 0.9, Y / 0.9, s, octaves=4) * (1 - np.clip(W, 0, 1))
        d = np.minimum.reduce([X - x0, x1 - X, Y - y0, y1 - Y])
        t = np.clip(d / BLEND, 0, 1)
        tau = t * t * (3 - 2 * t)
        z = B + tau * (C - B + m)
        water = np.zeros_like(z)
        if reaches:
            from .heightfield import Heightfield
            fine = Heightfield(z=z, res=h, origin=(x0, y0), province=hf.province)
            zc, water, _ = channels.carve(fine, reaches)
            keep = tau.copy()
            if protect is not None:
                keep *= 1 - np.clip(ndimage.map_coordinates(protect, [gy, gx], order=1, mode="nearest"), 0, 1)
            z = z + keep * (zc - z)
            water = water * (keep > 0.5)
        out.append(Patch(x0, y0, h, z, water))
    return out


def stitch(coarse: Mesh, hf, patches, tile=None) -> Mesh:
    """The coarse terrain mesh with each window's triangles replaced by its fine patch. Colours and splat
    weights of fine vertices are interpolated from the coarse vertices; UVs are xy / `tile`, like the coarse."""
    if not patches:
        return coarse
    ny, nx = hf.z.shape
    cen = coarse.positions[coarse.indices].mean(1)
    drop = np.zeros(len(cen), bool)
    for p in patches:
        drop |= p.inside(cen[:, 0], cen[:, 1])
    P, Cl, I, UV, Wt = [coarse.positions], [coarse.colors], [coarse.indices[~drop]], [coarse.uvs], [coarse.weights]
    off = len(coarse.positions)
    if coarse.uvs is None:
        tile = None
    for p in patches:
        n = p.z.shape[0]
        xs, ys = p.x0 + np.arange(n) * p.h, p.y0 + np.arange(n) * p.h
        X, Y = np.meshgrid(xs, ys)
        gx, gy = (X - hf.origin[0]) / hf.res, (Y - hf.origin[1]) / hf.res

        def interp(a):
            a = a.reshape(ny, nx, -1)
            return np.stack([ndimage.map_coordinates(a[..., c], [gy, gx], order=1, mode="nearest")
                             for c in range(a.shape[-1])], -1).reshape(-1, a.shape[-1])
        P.append(np.c_[X.ravel(), Y.ravel(), p.z.ravel()].astype(np.float32))
        Cl.append(interp(coarse.colors).astype(np.float32))
        UV.append(None if tile is None else (np.c_[X.ravel(), Y.ravel()] / tile).astype(np.float32))
        Wt.append(None if coarse.weights is None else interp(coarse.weights).astype(np.float32))
        k = np.arange((n - 1) * (n - 1))
        a = (k // (n - 1)) * n + k % (n - 1) + off
        I.append(np.concatenate([np.c_[a, a + 1, a + n], np.c_[a + 1, a + n + 1, a + n]]))
        off += n * n
    return Mesh(np.concatenate(P), np.concatenate(Cl), np.concatenate(I).astype(np.uint32),
                None if tile is None else np.concatenate(UV), coarse.texture,
                None if coarse.weights is None else np.concatenate(Wt), coarse.splat)

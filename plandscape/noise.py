"""Vectorised gradient noise, fBm, ridged noise and domain warping (numpy only)."""

from __future__ import annotations

import numpy as np

from .rng import rng

_TABLES: dict[int, tuple] = {}


def _tables(seed: int):
    t = _TABLES.get(seed)
    if t is None:
        r = rng("perlin", seed)
        perm = r.permutation(256)
        perm = np.concatenate([perm, perm])
        ang = r.uniform(0.0, 2.0 * np.pi, 256)
        t = (perm, np.cos(ang), np.sin(ang))
        _TABLES[seed] = t
    return t


def _fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def perlin2(x, y, seed: int = 0):
    """2-D gradient noise in roughly [-1, 1]."""
    perm, gx, gy = _tables(seed)
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    xf0 = np.floor(x)
    yf0 = np.floor(y)
    xf = x - xf0
    yf = y - yf0
    xi = xf0.astype(np.int64) & 255
    yi = yf0.astype(np.int64) & 255
    xi1 = (xi + 1) & 255
    yi1 = (yi + 1) & 255

    def g(ix, iy, dx, dy):
        h = perm[perm[ix] + iy]
        return gx[h] * dx + gy[h] * dy

    n00 = g(xi, yi, xf, yf)
    n10 = g(xi1, yi, xf - 1, yf)
    n01 = g(xi, yi1, xf, yf - 1)
    n11 = g(xi1, yi1, xf - 1, yf - 1)
    u = _fade(xf)
    v = _fade(yf)
    nx0 = n00 + u * (n10 - n00)
    nx1 = n01 + u * (n11 - n01)
    return 1.414 * (nx0 + v * (nx1 - nx0))


def fbm(x, y, seed=0, octaves=6, lacunarity=2.0, gain=0.5):
    total = np.zeros(np.broadcast(np.asarray(x), np.asarray(y)).shape)
    amp, freq, norm = 1.0, 1.0, 0.0
    for o in range(octaves):
        total += amp * perlin2(x * freq, y * freq, seed + 101 * o)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm


def ridged(x, y, seed=0, octaves=6, lacunarity=2.0, gain=0.5):
    total = np.zeros(np.broadcast(np.asarray(x), np.asarray(y)).shape)
    amp, freq, norm, weight = 1.0, 1.0, 0.0, 1.0
    for o in range(octaves):
        n = 1.0 - np.abs(perlin2(x * freq, y * freq, seed + 131 * o))
        n = n * n * weight
        weight = np.clip(n * 2.0, 0.0, 1.0)
        total += amp * n
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm * 2.0 - 1.0


def warp(x, y, seed=0, strength=1.0, freq=1.0):
    """Domain warp: returns displaced coordinates (organic, non-grid-like shapes)."""
    dx = fbm(x * freq, y * freq, seed + 7, octaves=3)
    dy = fbm(x * freq + 5.2, y * freq + 1.3, seed + 11, octaves=3)
    return x + strength * dx, y + strength * dy

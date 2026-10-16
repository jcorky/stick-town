"""Reference motion: exactly what the viewer's vertex shader computes (viewer/wind.js), in numpy.

Used for the gallery plots, for tests, and as the spec the GLSL is checked against. Every vertex moves by

    Δ = φ_t q_trunk + Δ_limb + Δ_branch + Δ_leaf           (tree, object frame)

    q_trunk  = Q G(U) [(1 + β r_u) ŵ + r_v p̂]             r = Σ_k a_k |H_k| cos(θ_k − ψ_k + ϑ_k)
    Δ_limb   = d1 G(U) (1 + β r_u¹) (ŵ − (ŵ·a) a)          same sum with f1, ζ_b
    Δ_branch = d2 G(U) (1 + β r_u²) (ŵ − (ŵ·a) a)          same sum with f2
    Δ_leaf   = λ [sin α(U) ŵ + A_f(U) sin(2π f_l t + 2π φ_l) n]

G(U) = F(U)/F(U_REF), β = d ln F/d ln U. θ_k is the travelling gust phase at the vertex (field.Wind.phases).
ϑ_k decorrelates small gusts between limbs: a limb's own random phase 2π φ is applied in proportion to
1 − exp(−C_y f_k ℓ / U_c), the Davenport coherence lost over the limb's size ℓ (3 m limbs, 1 m branches).
"""

from __future__ import annotations

import numpy as np

from .field import DAVENPORT_CY
from .response import U_REF, ZETA_BRANCH, drag, drag_slope, transfer

LIMB_L, BRANCH_L = 3.0, 1.0      # m, decorrelation sizes (design values)
ALPHA_MAX, U_ALPHA = 0.9, 6.0     # leaf reconfiguration: tip angle α = α_max (1 − e^{−U/U_α}) (design)
FLUTTER_HZ = 6.0                  # leaf torsional flutter, 6 ± 1 Hz on cherry, weakly speed-dependent (Tadrist 2018)
FLUTTER_A, U_FLUTTER = 0.12, 6.0  # flutter amplitude as a fraction of lever, saturating speed
GRASS_HZ, ZETA_GRASS = 1.5, 0.15  # grass blade mode (design)
GRASS_BETA, GRASS_U0 = 1.25, 4.0  # max bend angle (rad) and the speed giving half of it (design)


def gain(U):
    return drag(U, 1.0) / drag(U_REF, 1.0)


def modal(wind, fn, zeta, tu, tv, decor=0.0, ell=0.0):
    """Response sums r_u, r_v of an oscillator (fn, ζ) to the gust phases (…, n)."""
    c = wind.comps
    g, psi = transfer(c["f"], np.asarray(fn, float)[..., None], zeta)
    lost = 1 - np.exp(-DAVENPORT_CY * c["f"] * ell / wind.Uc) if ell else 0.0
    extra = 2 * np.pi * np.asarray(decor, float)[..., None] * lost
    ru = (c["au"] * g * np.cos(tu - psi + extra)).sum(-1)
    rv = (c["av"] * g * np.cos(tv - psi + extra)).sum(-1)
    return ru, rv


def trunk(wind, inst, t, Uh=None):
    """Top deflection (object frame xy, before yaw) of one tree instance at time(s) t.
    inst: dict(x, y, yaw, scale, f0, zeta, Q, shelter) — f0 per instance, Q in model metres."""
    Uh = wind.Uh if Uh is None else Uh
    U = Uh * inst["shelter"]
    tu, tv = wind.phases(inst["x"], inst["y"], t)
    ru, rv = modal(wind, inst["f0"], inst["zeta"], tu, tv)
    b = drag_slope(U)
    q = inst["Q"] * gain(U)
    w, p = _obj(wind, inst["yaw"])
    a, c = q * (1 + b * ru), q * rv
    return a[..., None] * w + c[..., None] * p


def _obj(wind, yaw):
    """Wind direction and its left normal in the instance's object frame (undo the yaw)."""
    c, s = np.cos(-yaw), np.sin(-yaw)
    R = np.array([[c, -s], [s, c]])
    w2, p2 = R @ wind.dir, R @ wind.perp
    return np.r_[w2, 0.0], np.r_[p2, 0.0]


def displace(wind, inst, P, A, N, t, Uh=None):
    """Displacement (object frame) of vertices P (object frame, metres) with decoded attributes A
    (attrs.unpack) and normals N at time t."""
    Uh = wind.Uh if Uh is None else Uh
    U = Uh * inst["shelter"]
    G, b = gain(U), drag_slope(U)
    q = trunk(wind, inst, t, Uh)
    out = A["phi"][:, None] * q[None, :]
    # world position of each vertex (for the travelling gust): rotate by yaw, scale, translate
    c, s = np.cos(inst["yaw"]), np.sin(inst["yaw"])
    k = inst["scale"]
    X = inst["x"] + k * (c * P[:, 0] - s * P[:, 1])
    Y = inst["y"] + k * (s * P[:, 0] + c * P[:, 1])
    tu, tv = wind.phases(X, Y, np.full(len(P), t))
    w, _ = _obj(wind, inst["yaw"])
    ax = A["axis"]
    perp = w[None, :] - (ax @ w)[:, None] * ax
    fs = 1.0 / k
    for d, f, ph, ell in ((A["d1"], A["f1"], A["ph1"], LIMB_L), (A["d2"], A["f2"], A["ph2"], BRANCH_L)):
        live = d > 0
        if not live.any():
            continue
        ru, _ = modal(wind, np.maximum(f[live] * fs, 0.05), ZETA_BRANCH, tu[live], tv[live], ph[live], ell)
        out[live] += (d[live] * G * (1 + b * ru))[:, None] * perp[live]
    lv = A["lever"] > 0
    if lv.any():
        al = ALPHA_MAX * (1 - np.exp(-U / U_ALPHA))
        af = FLUTTER_A * min(U / U_FLUTTER, 1.0)
        fl = np.sin(2 * np.pi * FLUTTER_HZ * t + 2 * np.pi * A["phl"][lv])
        out[lv] += A["lever"][lv, None] * (np.sin(al) * w[None, :] + (af * fl)[:, None] * N[lv])
    z = np.maximum(P[:, 2], 1.0)
    out[:, 2] -= 0.5 * (out[:, 0] ** 2 + out[:, 1] ** 2) / z  # arcs, not shears: the top drops as it leans
    return out


def grass(wind, P, W0, t, Uh=None):
    """Displacement (world) of grass vertices P with their packed _WIND0 at time t."""
    Uh = wind.Uh if Uh is None else Uh
    a = W0.astype(np.float64) / 255
    phi, shelter, L, ph = a[:, 0], 2 * a[:, 1], a[:, 2], a[:, 3]
    U = Uh * shelter
    tu, tv = wind.phases(P[:, 0], P[:, 1], np.full(len(P), t))
    ru, rv = modal(wind, GRASS_HZ, ZETA_GRASS, tu, tv, ph, 0.3)
    C = (U / GRASS_U0) ** 2
    beta = np.clip(GRASS_BETA * C / (1 + C) * (1 + 2 * ru), 0, 1.45)
    side = GRASS_BETA * C / (1 + C) * rv
    h = phi * L
    out = np.zeros_like(P, dtype=np.float64)
    out[:, :2] = h[:, None] * (np.sin(beta)[:, None] * wind.dir[None] + np.sin(side)[:, None] * wind.perp[None])
    out[:, 2] = -h * (1 - np.cos(beta))
    return out

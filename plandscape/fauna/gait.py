"""Gaits matched to speed: stride from dynamic similarity, gait from the Froude number, legs swung by phase.

Alexander's dynamic similarity: animals of any size move alike at equal Froude number Fr = v² / (g h), with h the
hip height. Relative stride length follows (Alexander 1976, Nature 261)

    λ / h = 2.3 · Fr^0.3

and quadrupeds change gait at about the same Fr (Alexander & Jayes 1983): walk below 0.5, trot to about 2.5,
gallop above. Each leg's swing angle is a sine of the stride phase φ, offset per leg by the gait's footfall
pattern, with amplitude set by how far the foot travels while on the ground (duty factor β):

    φ(t) = ∫ 2π v / λ(v) dt,     θ_leg = θ_max · sin(φ − 2π o_leg),     θ_max = asin(min(λβ / 2h, 0.7))

Keyframes go at fixed phase steps (8 per stride), not fixed times: a resting animal costs no keys and a gallop
is sampled as finely as a walk. See docs/TECHNIQUES.md §25.
"""

from __future__ import annotations

import numpy as np

G = 9.81
KEYS_PER_STRIDE = 8
# footfall offsets (fraction of a stride) for legs ordered LF, RF, LH, RH, and duty factors
QUAD = {"walk": ((0.25, 0.75, 0.0, 0.5), 0.65),     # lateral-sequence walk
        "trot": ((0.0, 0.5, 0.5, 0.0), 0.45),       # diagonal pairs together
        "gallop": ((0.5, 0.6, 0.0, 0.1), 0.35)}     # transverse gallop: hinds, then fores
BIPED = {"walk": ((0.0, 0.5), 0.6), "trot": ((0.0, 0.5), 0.4), "gallop": ((0.0, 0.5), 0.35)}


def froude(v, h):
    return np.asarray(v, float) ** 2 / (G * h)


def stride(v, h):
    """Stride length λ = 2.3 h Fr^0.3 (Alexander 1976)."""
    return 2.3 * h * np.maximum(froude(v, h), 1e-9) ** 0.3


def gait_name(fr):
    return "walk" if fr < 0.5 else ("trot" if fr < 2.5 else "gallop")


def phase_track(times, xy, h, v_min=0.05):
    """Speed over each log interval (v[i] for (t[i−1], t[i]]) and cumulative stride phase at the samples.
    Speed is constant within an interval, so phase advances by 2π f_i Δt_i (no trapezoid: that would keep
    the legs moving for half a step after the animal stopped)."""
    t = np.asarray(times, float)
    xy = np.asarray(xy, float)
    dt = np.maximum(np.diff(t), 1e-6)
    v = np.r_[0.0, np.hypot(*np.diff(xy, axis=0).T) / dt]
    v = np.where(v < v_min, 0.0, v)
    f = np.where(v > 0, v / stride(np.maximum(v, v_min), h), 0.0)
    phi = np.r_[0.0, np.cumsum(f[1:] * dt)] * 2 * np.pi
    return v, phi


def _interval_speed(times, v, tk):
    i = np.clip(np.searchsorted(times, tk, side="left"), 1, len(times) - 1)
    return v[i]


def key_times(times, v, phi):
    """Keyframe times: every π/4 of phase while moving, plus the samples where motion starts or stops."""
    t = np.asarray(times, float)
    k = np.arange(0.0, phi[-1], 2 * np.pi / KEYS_PER_STRIDE)
    ph = phi + np.arange(len(phi)) * 1e-9  # strictly increasing for interpolation
    tk = np.interp(k, ph, t)
    moving = v > 0
    edge = np.nonzero(moving[1:] != moving[:-1])[0]
    extra = np.r_[t[0], t[-1], t[edge], t[np.minimum(edge + 1, len(t) - 1)]]
    return np.unique(np.r_[tk, extra])


def leg_angles(times, xy, h, legs="quad"):
    """(key times (K,), angles (K, n_legs) radians, gait name per key) for a logged path."""
    v, phi = phase_track(times, xy, h)
    tk = key_times(times, v, phi)
    vk = _interval_speed(times, v, tk)
    pk = np.interp(tk, times, phi)
    fr = froude(vk, h)
    table = QUAD if legs == "quad" else BIPED
    names = [gait_name(x) for x in fr]
    lam = stride(np.maximum(vk, 1e-3), h)
    out = np.zeros((len(tk), len(table["walk"][0])))
    for i, (nm, p, l, vv) in enumerate(zip(names, pk, lam, vk)):
        if vv <= 0:
            continue
        offs, beta = table[nm]
        amp = np.arcsin(min(l * beta / (2 * h), 0.7))
        out[i] = amp * np.sin(p - 2 * np.pi * np.asarray(offs))
    return tk, out, names


def hop_heights(times, xy, h, height):
    """Bounding small animals (squirrels): the body rises |sin(φ/2)| · height once per stride."""
    v, phi = phase_track(times, xy, h)
    tk = key_times(times, v, phi)
    vk = _interval_speed(times, v, tk)
    pk = np.interp(tk, times, phi)
    return tk, np.where(vk > 0, height * np.abs(np.sin(pk / 2)), 0.0)

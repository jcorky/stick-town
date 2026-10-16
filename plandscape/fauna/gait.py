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

Knees (§26): legs are two segments (thigh l1, shank l2, l1 + l2 = h / 0.95, so the rest pose is slightly flexed).
Each foot follows a path in the hip frame, leg phase ψ = frac(φ/2π − o):
    stance ψ < β:  x = S (½ − ψ/β),                         z = −h            (on the ground, sliding back)
    swing  ψ ≥ β:  x = S (−½ + smoothstep(u)), u = (ψ−β)/(1−β),  z = −h + H_lift sin(πu)
with S = λβ the distance the body covers while the foot is down. Two-bone IK (law of cosines) gives
    γ = acos((l1² + d² − l2²) / 2 l1 d),   K = acos((l1² + l2² − d²) / 2 l1 l2),   α = atan2(x, −z)
    θ_hip = α + κ γ,   θ_knee = −κ (π − K)
with κ = +1 for knees that bend forward (stifle, human knee) and −1 for joints that bend backward (a deer's
carpus, a bird's intertarsal joint). Out-of-reach targets are clamped to a straight leg.
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


LIFT = {"walk": 0.12, "trot": 0.2, "gallop": 0.3}  # swing-foot lift, fraction of hip height
REACH = 1 / 0.95  # leg length / hip height


def foot_path(psi, beta, S, h, lift):
    """Foot (x forward, z up) relative to the hip for leg phase ψ ∈ [0, 1)."""
    psi = np.mod(psi, 1.0)
    st = psi < beta
    u = np.clip((psi - beta) / max(1 - beta, 1e-6), 0, 1)
    ss = u * u * (3 - 2 * u)
    x = np.where(st, S * (0.5 - psi / max(beta, 1e-6)), S * (-0.5 + ss))
    z = np.where(st, -h, -h + lift * h * np.sin(np.pi * u))
    return x, z


def two_bone(x, z, l1, l2, knee=1.0):
    """Hip and knee pitch (forward-positive) putting the foot at (x, z) relative to the hip."""
    d = np.clip(np.hypot(x, z), abs(l1 - l2) + 1e-6, l1 + l2 - 1e-6)
    gam = np.arccos(np.clip((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1, 1))
    K = np.arccos(np.clip((l1 * l1 + l2 * l2 - d * d) / (2 * l1 * l2), -1, 1))
    a = np.arctan2(x, -z)
    return a + knee * gam, -knee * (np.pi - K)


def rest_pose(h, l1, l2, knee):
    return two_bone(0.0, -h, l1, l2, knee)


def leg_ik(times, xy, h, knees, legs="quad", seg=None):
    """(key times (K,), angles (K, n_legs, 2) hip/knee radians, gait names) with feet planted in stance."""
    v, phi = phase_track(times, xy, h)
    tk = key_times(times, v, phi)
    vk = _interval_speed(times, v, tk)
    pk = np.interp(tk, times, phi)
    table = QUAD if legs == "quad" else BIPED
    L = h * REACH
    l1, l2 = seg if seg is not None else (L / 2, L / 2)
    names = [gait_name(x) for x in froude(vk, h)]
    n = len(table["walk"][0])
    out = np.zeros((len(tk), n, 2))
    for j in range(n):
        out[:, j] = rest_pose(h, l1, l2, knees[j])
    for i, (nm, p, vv) in enumerate(zip(names, pk, vk)):
        if vv <= 0:
            continue
        offs, beta = table[nm]
        S = float(stride(vv, h)) * beta
        for j, o in enumerate(offs):
            x, z = foot_path(p / (2 * np.pi) - o, beta, S, h, LIFT[nm])
            out[i, j] = two_bone(x, z, l1, l2, knees[j])
    return tk, out, names


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

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


def phase_track(times, xy, h, v_min=0.05, air=None):
    """Speed over each log interval (v[i] for (t[i−1], t[i]]) and cumulative stride phase at the samples.
    Speed is constant within an interval, so phase advances by 2π f_i Δt_i (no trapezoid: that would keep
    the legs moving for half a step after the animal stopped)."""
    t = np.asarray(times, float)
    xy = np.asarray(xy, float)
    dt = np.maximum(np.diff(t), 1e-6)
    v = np.r_[0.0, np.hypot(*np.diff(xy, axis=0).T) / dt]
    v = np.where(v < v_min, 0.0, v)
    if air is not None:  # no strides in the air (§33)
        v = np.where(np.asarray(air, bool), 0.0, v)
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
BOB = {"walk": 0.015, "trot": 0.03, "gallop": 0.05}  # trunk bob amplitude, fraction of hip height (§28)
# head pitch per behaviour state, as a fraction of the species' grazing angle (+ = down), and up for alert
HEAD = {"fly": -0.3, "eat": 1.0, "drink": 1.0, "dig": 0.9, "scratch": 0.8, "groom": 0.4, "rest": 0.3, "idle": 0.1,
        "pause": 0.0, "travel": 0.15, "flee": 0.1, "alert": -0.25, "freeze": -0.2}
HEAD_EASE = 0.4  # s to move the head to a new pose
TAIL = {"flee": 1.0, "alert": 0.4}  # deer tail raise, fraction of the flag angle (§29)
TAIL_EASE = 0.3
LIE = {"rest": 1.0}  # trunk drop, fraction of the species' lying drop (§29)
LIE_EASE = 1.0
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


TRAIL = (np.radians(-80), 0.0)  # legs in flight: swung back along the body, knee straight (§33)


def leg_ik(times, xy, h, knees, legs="quad", seg=None, bob=None, drop=None, air=None):
    """(key times (K,), angles (K, n_legs, 2) hip/knee radians, gait names) with feet planted in stance.
    With `bob` a list, it is filled with the trunk lift b(t) = A cos 2φ at each key; feet aim at z = −(h + b)
    so they stay on the ground while the body rises and falls. `drop` = (key times, metres) lowers the trunk
    (lying down, §29): its keys join the timeline, and resting feet aim at z = −(h − drop), folding the legs."""
    v, phi = phase_track(times, xy, h, air=air)
    tk = key_times(times, v, phi)
    if air is not None:  # take-off and landing get keys of their own
        a_ = np.asarray(air, bool)
        e_ = np.nonzero(a_[1:] != a_[:-1])[0]
        tk = np.unique(np.r_[tk, np.asarray(times)[e_], np.asarray(times)[np.minimum(e_ + 1, len(times) - 1)]])
    if drop is not None:
        tk = np.unique(np.r_[tk, np.clip(drop[0], times[0], times[-1])])
    vk = _interval_speed(times, v, tk)
    pk = np.interp(tk, times, phi)
    dk = np.interp(tk, drop[0], drop[1]) if drop is not None else np.zeros(len(tk))
    table = QUAD if legs == "quad" else BIPED
    L = h * REACH
    l1, l2 = seg if seg is not None else (L / 2, L / 2)
    names = [gait_name(x) for x in froude(vk, h)]
    n = len(table["walk"][0])
    out = np.zeros((len(tk), n, 2))
    b = -dk.copy()
    for j in range(n):
        out[:, j] = np.stack(two_bone(np.zeros(len(tk)), -(h - dk), l1, l2, knees[j]), -1)
    for i, (nm, p, vv) in enumerate(zip(names, pk, vk)):
        if vv <= 0:
            continue
        offs, beta = table[nm]
        S = float(stride(vv, h)) * beta
        b[i] = BOB[nm] * h * np.cos(2 * p) - dk[i]
        for j, o in enumerate(offs):
            x, z = foot_path(p / (2 * np.pi) - o, beta, S, h, LIFT[nm])
            out[i, j] = two_bone(x, z - b[i], l1, l2, knees[j])
    if air is not None:
        ak = np.asarray(air, bool)[np.clip(np.searchsorted(times, tk, side="right") - 1, 0, len(times) - 1)]
        out[ak] = TRAIL
        b[ak] = 0.0
    if bob is not None:
        bob.extend(b.tolist())
    return tk, out, names


FLAP_HZ, FLAP_AMP, WING_FOLD = 2.5, np.radians(40), 0.03  # design values (§33); folded wings tuck into the body (§36)


def wing_track(times, air):
    """Wing (roll, span scale) keys: folded to WING_FOLD span on the ground, flapping ±40° at 2.5 Hz in the air,
    8 keys per beat while airborne."""
    t = np.asarray(times, float)
    a = np.asarray(air, bool)
    keys = [t[0], t[-1]]
    e = np.nonzero(a[1:] != a[:-1])[0]
    keys += list(t[e]) + list(t[np.minimum(e + 1, len(t) - 1)])
    for i0 in np.nonzero(a & ~np.r_[False, a[:-1]])[0]:  # each flight
        i1 = i0
        while i1 + 1 < len(a) and a[i1 + 1]:
            i1 += 1
        keys += list(np.arange(t[i0], t[i1], 1 / (FLAP_HZ * 8)))
    tk = np.unique(keys)
    ak = a[np.clip(np.searchsorted(t, tk, side="right") - 1, 0, len(t) - 1)]
    roll = np.where(ak, FLAP_AMP * np.sin(2 * np.pi * FLAP_HZ * tk), 0.0)
    span = np.where(ak, 1.0, WING_FOLD)
    return tk, roll, span


def head_track(times, states, graze):
    """Head pitch keys (+ = down) from behaviour states, as fractions of the grazing angle."""
    return pose_track(times, states, graze, HEAD, HEAD_EASE)


def pose_track(times, states, full, table, ease):
    """Pose keys from behaviour states: `table` maps state → fraction of `full` (an angle or a distance);
    each change eases over `ease` seconds. Returns (times, values)."""
    t = np.asarray(times, float)
    target = np.array([table.get(s, 0.0) * full for s in states])
    tk, val = [t[0]], [target[0]]
    for i in range(1, len(t)):
        if target[i] != target[i - 1]:
            if t[i] > tk[-1] + 1e-6:
                tk.append(t[i])
                val.append(target[i - 1])
            tk.append(t[i] + ease)
            val.append(target[i])
    if t[-1] > tk[-1]:
        tk.append(t[-1])
        val.append(val[-1])
    tk, val = np.array(tk), np.array(val)
    keep = np.r_[True, np.diff(tk) > 1e-6]  # ease windows that overlap a later change collapse to it
    return tk[keep], val[keep]


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

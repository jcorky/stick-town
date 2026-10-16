"""Export-side smoothing of agent tracks: turn-rate-limited headings and keyframe reduction.

The simulation may snap an agent's heading (a new plan points it at its goal, an obstacle turns it 90°), and the GLB
used to sample its path once a second. Displayed motion now:

1. Turns at a bounded rate: the shown heading chases the logged one,
       ĥ_i = ĥ_{i−1} + clip(wrap(h_i − ĥ_{i−1}), −ω_max Δt, ω_max Δt)
   with ω_max per species (design values, not measured: a deer pivots faster than an armadillo).
   While the animal stands still its body holds its heading: the simulation's "look around" jitter is a gaze, not
   a spin in place. A stop longer than 3 s gets one turn, to the circular mean of the logged heading over the stop,
       h̄ = atan2(Σ sin h, Σ cos h).
2. Keeps only the keys linear interpolation needs: Ramer–Douglas–Peucker over time, dropping a sample when the
   segment between kept neighbours reproduces it within 2 cm and 2°. A resting animal costs two keys; a turning one
   keeps its curve. See docs/TECHNIQUES.md §30.
"""

from __future__ import annotations

import numpy as np

OMEGA_MAX = {"white_tailed_deer": 4.0, "coyote": 4.0, "wild_turkey": 3.0, "gray_squirrel": 8.0,
             "armadillo": 2.0, "human": 2.5}  # rad/s


def wrap(a):
    return (np.asarray(a) + np.pi) % (2 * np.pi) - np.pi


def turn_limited(times, headings, omega_max):
    t = np.asarray(times, float)
    h = np.asarray(headings, float)
    out = np.empty_like(h)
    out[0] = h[0]
    for i in range(1, len(h)):
        step = omega_max * max(t[i] - t[i - 1], 0.0)
        out[i] = out[i - 1] + np.clip(wrap(h[i] - out[i - 1]), -step, step)
    return out


def simplify(times, P, H, eps_p=0.02, eps_h=np.radians(2.0)):
    """Indices of the samples to keep so that linear interpolation of positions P (N,3) and unwrapped
    headings H (N,) between kept samples stays within eps_p metres and eps_h radians of every sample."""
    t = np.asarray(times, float)
    P = np.asarray(P, float)
    H = np.asarray(H, float)
    keep = np.zeros(len(t), bool)
    keep[[0, -1]] = True
    stack = [(0, len(t) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        s = (t[a + 1:b] - t[a]) / max(t[b] - t[a], 1e-9)
        ep = np.linalg.norm(P[a + 1:b] - (P[a] + s[:, None] * (P[b] - P[a])), axis=1)
        eh = np.abs(H[a + 1:b] - (H[a] + s * (H[b] - H[a])))
        err = np.maximum(ep / eps_p, eh / eps_h)
        k = int(np.argmax(err))
        if err[k] > 1.0:
            m = a + 1 + k
            keep[m] = True
            stack += [(a, m), (m, b)]
    return np.nonzero(keep)[0]


def body_heading_target(times, xy, headings, v_min=0.05, long_stop=3.0):
    """Logged heading while moving; held (or one turn to the stop's circular mean) while standing still."""
    t = np.asarray(times, float)
    h = np.asarray(headings, float)
    d = np.r_[0.0, np.hypot(*np.diff(np.asarray(xy, float), axis=0).T)]
    moving = d > v_min * np.r_[1.0, np.diff(t)]
    out = h.copy()
    i, n = 0, len(t)
    while i < n:
        if moving[i]:
            i += 1
            continue
        j = i
        while j < n and not moving[j]:
            j += 1
        held = out[i - 1] if i > 0 else h[i]
        if t[j - 1] - t[i] > long_stop:
            held = np.arctan2(np.sin(h[i:j]).sum(), np.cos(h[i:j]).sum())
        out[i:j] = held
        i = j
    return out


def export_track(log, species):
    """(times, positions (K,3), headings (K,)) for the GLB, from an agent log of (t, x, y, z, heading, state)."""
    t = np.array([l[0] for l in log], float)
    P = np.array([(l[1], l[2], l[3]) for l in log], float)
    target = body_heading_target(t, P[:, :2], [l[4] for l in log])
    H = turn_limited(t, np.unwrap(target), OMEGA_MAX.get(species, 3.0))
    k = simplify(t, P, H)
    return t[k], P[k], H[k]

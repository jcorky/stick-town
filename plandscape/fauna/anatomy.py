"""Sculpted anatomy for every species (TECHNIQUES §36): each rig part is a small sculpture of blended forms
(sculpt.py), meshed into a continuous skin and painted by position and normal (countershading, masks, rings,
flags, bands).

Frames match bodies.rig: body x forward, y left, z up, feet at z = 0. The torso is in body coordinates; head,
tail and wings are relative to their pivots; a thigh hangs from its hip and a shank from its knee, along −z.
`h` is the hip-joint height (the leg length the gaits use); the back sits above it. Sizes in
catalog/fauna_sources.json where sourced; the rest are design values drawn from photographs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .sculpt import Sculpt, merge, rot

BUDGET = dict(torso=2600, head=1400, ear=160, eye=160, tail=420, thigh=380, shank=320, hoof=70)

WHITE = np.array([0.93, 0.92, 0.88])
DARK = np.array([0.07, 0.06, 0.05])


def smooth(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return a * (1 - t[:, None]) + np.asarray(b, float) * t[:, None]


def lum(C):
    return C @ np.array([0.3, 0.59, 0.11])


def mottle(P, scale, amp, seed=0.0):
    """Coat variation from a few incommensurate sines: hair whorls and dapple at a distance, no RNG."""
    x, y, z = P[:, 0] / scale, P[:, 1] / scale, P[:, 2] / scale
    n = (np.sin(1.7 * x + 2.3 * z + seed) + np.sin(2.9 * y - 1.3 * x + 0.7 * seed) +
         np.sin(3.7 * z + 1.1 * y + 1.9 * seed)) / 3
    return 1 + amp * n


@dataclass
class Quad:
    """A four-legged body. Lengths in metres; positions along the body as x."""
    h: float                      # hip-joint height
    back: float                   # withers / croup height above the hip joint
    shoulder_x: float             # fore-leg hip (shoulder joint) x
    hip_x: float                  # hind-leg hip x
    half_w: float                 # half body width
    depth: float                  # chest depth (withers to brisket)
    leg_y: float                  # leg spacing (half)
    leg_r: tuple = (0.05, 0.03, 0.022)   # upper, knee, lower leg radii
    neck: list = None             # neck chain points relative to the neck pivot
    neck_r: list = None
    skull: tuple = None           # (centre, radii, pitch)
    muzzle: tuple = None          # (a, b, ra, rb)
    nose_r: float = 0.02
    ears: tuple = None            # (centre, radii, roll, pitch)
    eye: tuple = None             # (centre, radius)
    tail: list = None             # tail chain relative to the tail pivot
    tail_r: list = None
    foot: str = "hoof"            # hoof | paw
    belly_up: float = 0.06        # how much the belly tucks up behind the ribs
    neck_pivot: tuple = None      # where the head part hinges (body frame); the torso grows a neck root toward it
    tail_pivot: tuple = None
    hunch: float = 0.0            # croup higher than withers (raccoons, armadillos), metres
    hind_shank: float = 0.5       # hind leg: share of the leg below the hock (deer: hock to hoof 0.45 m)
    extras: dict = field(default_factory=dict)


def _quad_torso(q: Quad, coat, paint):
    s = Sculpt()
    h, b, d = q.h, q.back, q.depth
    L = q.shoulder_x - q.hip_x
    mid = (q.shoulder_x + q.hip_x) / 2
    zc = h + b - d / 2                                  # chest centre height
    s.ellipsoid((mid, 0, zc + 0.02 * d), (L * 0.55, q.half_w * 0.95, d * 0.46), coat, k=0.25 * d)   # barrel
    s.ellipsoid((q.shoulder_x - 0.05 * L, 0, zc - 0.02 * d), (L * 0.28, q.half_w, d * 0.52), coat, k=0.25 * d)  # chest
    s.ellipsoid((q.shoulder_x - 0.08 * L, 0, h + b - 0.18 * d), (L * 0.22, q.half_w * 0.7, d * 0.25), coat,
                k=0.25 * d)                                                                       # withers
    s.ellipsoid((q.hip_x + 0.02 * L, 0, h + b - 0.3 * d), (L * 0.26, q.half_w * 0.95, d * 0.42), coat,
                k=0.25 * d)                                                                       # croup, rump
    for y in (q.leg_y, -q.leg_y):
        s.ellipsoid((q.hip_x, y * 0.85, h + 0.05 * d), (L * 0.2, q.half_w * 0.55, d * 0.55), coat, k=0.2 * d)  # haunch
        s.ellipsoid((q.shoulder_x - 0.02 * L, y * 0.8, h + 0.15 * d), (L * 0.14, q.half_w * 0.45, d * 0.45), coat,
                    k=0.2 * d)                                                                     # shoulder
    s.ellipsoid((mid + 0.1 * L, 0, zc - d * 0.32), (L * 0.35, q.half_w * 0.8, d * 0.2), coat, k=0.3 * d)  # belly
    if q.hunch:
        s.ellipsoid((q.hip_x + 0.1 * L, 0, h + b - 0.25 * d + q.hunch), (L * 0.3, q.half_w * 0.9, d * 0.4), coat,
                    k=0.3 * d)                                                                     # arched back
    if q.neck_pivot is not None:   # neck root: the head part overlaps it, so the join is buried, not a collar
        pv = np.asarray(q.neck_pivot, float)
        lift = q.extras.get("neck_root_lift", 0.05)
        s.cone((q.shoulder_x - 0.1 * L, 0, zc), pv + np.array([0.04, 0, lift]), q.neck_r[0] * 1.45, q.neck_r[0] * 1.02,
               coat, k=0.2 * d)
    for f in q.extras.get("torso", ()):
        f(s, coat)
    return s.mesh(target=BUDGET["torso"], colour_fn=paint)


def _quad_legs(q: Quad, coat, leg_col, foot_col, sock=None):
    L = q.h / 0.95
    splits = {True: (L / 2, L / 2), False: (L * (1 - q.hind_shank), L * q.hind_shank)}
    r0, r1, r2 = q.leg_r

    def thigh(fore):
        l = splits[fore][0]
        g = Sculpt()
        if fore:
            g.cone((0, 0, 0.3 * r0), (0, 0, -l * 0.45), r0, r1 * 1.2, coat, k=r0)
            g.cone((0, 0, -l * 0.45), (0, 0, -l), r1 * 1.2, r1, leg_col, k=r1)
        else:
            g.cone((0.1 * r0, 0, 0.2 * r0), (-0.4 * r0, 0, -l * 0.5), r0 * 1.1, r1 * 1.15, coat, k=r0)
            g.cone((-0.4 * r0, 0, -l * 0.5), (0, 0, -l), r1 * 1.15, r1, leg_col, k=r1)
            g.ellipsoid((-0.5 * r1, 0, -l * 0.97), (r1 * 1.3, r1, r1 * 1.2), leg_col, k=r1 * 0.8)   # hock
        return g.mesh(target=BUDGET["thigh"])

    def shank(fore):
        l = splits[fore][1]
        g = Sculpt()
        g.cone((0, 0, 0), (0, 0, -l * 0.84), r1, r2, leg_col, k=r2)
        bits = []   # small hard parts, meshed on their own fine grids
        if q.foot == "hoof":
            g.ellipsoid((0, 0, -l * 0.85), (r2 * 1.1, r2 * 0.95, r2 * 1.2), leg_col, k=r2 * 0.6)      # fetlock
            g.cone((0, 0, -l * 0.85), (r2 * 0.8, 0, -l * 0.94), r2 * 0.85, r2 * 0.8, leg_col, k=r2 * 0.5)  # pastern
            for sgn in (1, -1):  # the two halves of a cloven hoof
                bits.append(Sculpt().cone((r2 * 0.8, 0.42 * r2 * sgn, -l * 0.93), (r2 * 2.0, 0.45 * r2 * sgn, -l + 0.2 * r2),
                                          r2 * 0.7, r2 * 0.28, foot_col, k=r2 * 0.25))
            bits.append(Sculpt().ellipsoid((-r2 * 0.9, 0, -l * 0.87), (r2 * 0.35, r2 * 0.6, r2 * 0.45), foot_col,
                                           k=r2 * 0.2))                                                   # dewclaws
        else:    # a paw: pad and toes forward, claws
            g.ellipsoid((r2 * 0.9, 0, -l + r2 * 0.75), (r2 * 1.9, r2 * 1.25, r2 * 0.8), leg_col, k=r2 * 0.6)
            for t in (-1.5, -0.5, 0.5, 1.5):
                g.ellipsoid((r2 * 2.4, t * r2 * 0.55, -l + r2 * 0.45), (r2 * 0.6, r2 * 0.32, r2 * 0.45), leg_col,
                            k=r2 * 0.3)
                bits.append(Sculpt().cone((r2 * 2.7, t * r2 * 0.55, -l + r2 * 0.5), (r2 * 3.2, t * r2 * 0.6, -l + 0.1 * r2),
                                          r2 * 0.2, r2 * 0.06, foot_col, k=r2 * 0.1))

        def paint(P, N, C):
            return C if sock is None else sock(P, N, C, l)
        return merge([g.mesh(target=BUDGET["shank"], colour_fn=paint)] + [b.mesh(target=BUDGET["hoof"]) for b in bits])
    return thigh(True), thigh(False), shank(True), shank(False), splits


def _quad_head(q: Quad, coat, paint, eye_col=DARK, nose_col=DARK, ear_col=None, ear_paint=None):
    n = Sculpt()
    n.chain(q.neck, q.neck_r, coat, k=q.neck_r[0] * 0.6)
    c, r, pitch = q.skull
    n.ellipsoid(c, r, coat, k=r[2] * 0.7, R=rot(pitch=pitch))
    a, b, ra, rb = q.muzzle
    n.cone(a, b, ra, rb, coat, k=ra * 0.7)
    n.ellipsoid(np.asarray(b) + np.array([rb * 0.4, 0, 0]), (q.nose_r, q.nose_r * 1.2, q.nose_r), nose_col,
                k=q.nose_r * 0.4)
    for f in q.extras.get("head", ()):
        f(n, coat)
    parts = [n.mesh(target=BUDGET["head"], colour_fn=paint)]
    ec, er, roll, epitch = q.ears[:4]
    pointed = len(q.ears) > 4 and q.ears[4] == "pointed"
    for sgn in (1, -1):   # ears and eyes are thin or small: their own sculptures, on their own fine grids
        ecol = coat * 0.9 if ear_col is None else ear_col
        if pointed:       # a triangle: a flattened cone, broad at the base, to a point
            R = rot(roll=-roll * sgn, pitch=epitch)
            base = np.array([ec[0], ec[1] * sgn, ec[2] - er[2]])
            tip = base + R @ np.array([0, 0, 2 * er[2]])
            ear = Sculpt()
            for w in (-1, 0, 1):
                ear.cone(base + R @ np.array([w * er[0] * 0.6, 0, 0]), tip, er[1] * 1.3, er[1] * 0.25, ecol, k=er[0] * 0.6)
        else:
            ear = Sculpt().ellipsoid((ec[0], ec[1] * sgn, ec[2]), er, ecol, k=er[1], R=rot(roll=-roll * sgn, pitch=epitch))
        parts.append(ear.mesh(target=BUDGET["ear"], colour_fn=ear_paint))
        eye = Sculpt().ellipsoid((q.eye[0][0], q.eye[0][1] * sgn, q.eye[0][2]), (q.eye[1],) * 3, eye_col)
        parts.append(eye.mesh(target=BUDGET["eye"]))
    return merge(parts)


def _quad_tail(q: Quad, coat, paint, bushy=1.0):
    t = Sculpt()
    t.chain(q.tail, [r * bushy for r in q.tail_r], coat, k=q.tail_r[0] * 0.6)
    return t.mesh(target=BUDGET["tail"], colour_fn=paint)


def _not_dark(C, t):
    """Leave eyes, noses and hooves alone when painting a marking over them."""
    return t * smooth(0.12, 0.22, lum(C))


# ── white-tailed deer ───────────────────────────────────────────────────────

def deer(rgb):
    coat = np.asarray(rgb, float)
    q = Quad(h=0.62, back=0.29, shoulder_x=0.43, hip_x=-0.42, half_w=0.12, depth=0.38, leg_y=0.07,
             leg_r=(0.055, 0.03, 0.02), hind_shank=0.62,
             neck=[(-0.10, 0, -0.10), (0.08, 0, 0.16), (0.16, 0, 0.36)], neck_r=[0.088, 0.08, 0.065],
             skull=((0.24, 0, 0.42), (0.10, 0.065, 0.075), 0.35),
             muzzle=((0.26, 0, 0.40), (0.43, 0, 0.31), 0.055, 0.03), nose_r=0.022,
             ears=((0.19, 0.075, 0.54), (0.035, 0.016, 0.08), 0.7, -0.25),
             eye=((0.30, 0.056, 0.43), 0.016),
             tail=[(0, 0, 0), (-0.06, 0, -0.08), (-0.08, 0, -0.17)], tail_r=[0.04, 0.055, 0.045],
             neck_pivot=(0.45, 0, 0.81), tail_pivot=(-0.56, 0, 0.81))
    h, top = q.h, q.h + q.back

    def torso_paint(P, N, C):
        C = C * mottle(P, 0.05, 0.05)[:, None]
        belly = smooth(h + 0.02, h - 0.1, P[:, 2]) * smooth(0.0, -0.5, N[:, 2])
        rump = smooth(-0.48, -0.56, P[:, 0]) * smooth(top - 0.12, top - 0.22, P[:, 2])
        C = mix(C, coat * 0.72, smooth(top - 0.08, top, P[:, 2]) * 0.4)               # darker along the spine
        return mix(C, WHITE, np.maximum(belly, rump * 0.9))

    def head_paint(P, N, C):
        C = C * mottle(P, 0.03, 0.04)[:, None]
        throat = np.exp(-((P[:, 0] - 0.10) ** 2 / 0.003 + P[:, 1] ** 2 / 0.006 + (P[:, 2] - 0.28) ** 2 / 0.004)) * \
            smooth(0.3, -0.3, N[:, 0])                                                    # white throat patch
        band = smooth(0.37, 0.39, P[:, 0]) * smooth(0.425, 0.405, P[:, 0])               # pale band behind the nose
        ring = np.exp(-((np.hypot(P[:, 0] - 0.30, P[:, 2] - 0.43) - 0.024) ** 2) / 0.00004) * \
            smooth(0.03, 0.05, np.abs(P[:, 1]))                                           # eye ring
        chin = smooth(-0.3, -0.8, N[:, 2]) * smooth(0.33, 0.40, P[:, 0])
        t = np.clip(throat + 0.8 * band + 0.9 * ring + chin, 0, 1)
        return mix(C, WHITE, _not_dark(C, t))

    def tail_paint(P, N, C):                                                              # the flag
        return mix(C, WHITE, smooth(0.2, -0.4, N[:, 0]))

    def sock(P, N, C, l):
        return mix(C, WHITE, _not_dark(C, smooth(-l * 0.75, -l * 0.82, P[:, 2]) * smooth(-l * 0.9, -l * 0.86, P[:, 2]) * 0.5))
    leg_col = coat * 0.82
    tf, th, sf, shh, sp = _quad_legs(q, coat, leg_col, DARK, sock)

    def ear_paint(P, N, C):  # pale inside the ear, dark rim
        return mix(C, WHITE * 0.95, smooth(0.0, 0.7, N[:, 0]) * 0.7)
    return dict(q=q, torso=_quad_torso(q, coat, torso_paint), head=_quad_head(q, coat, head_paint, ear_paint=ear_paint),
                neck_pivot=q.neck_pivot, tail=_quad_tail(q, coat, tail_paint), tail_pivot=q.tail_pivot,
                thigh_fore=tf, thigh_hind=th, shank_fore=sf, shank_hind=shh, splits=sp,
                graze=np.radians(110), flag=np.radians(100))


# ── coyote ──────────────────────────────────────────────────────────────────

def coyote(rgb):
    coat = np.asarray(rgb, float)
    q = Quad(h=0.40, back=0.15, shoulder_x=0.28, hip_x=-0.26, half_w=0.09, depth=0.24, leg_y=0.06,
             leg_r=(0.04, 0.022, 0.016),
             neck=[(-0.07, 0, -0.06), (0.05, 0, 0.06), (0.12, 0, 0.13)], neck_r=[0.065, 0.06, 0.055],
             skull=((0.17, 0, 0.16), (0.08, 0.06, 0.06), 0.1),
             muzzle=((0.2, 0, 0.14), (0.34, 0, 0.10), 0.04, 0.02), nose_r=0.016,
             ears=((0.15, 0.045, 0.25), (0.03, 0.012, 0.055), 0.25, -0.15, "pointed"),
             eye=((0.225, 0.04, 0.175), 0.011),
             tail=[(0, 0, 0), (-0.12, 0, -0.12), (-0.24, 0, -0.26), (-0.28, 0, -0.33)], tail_r=[0.03, 0.06, 0.055, 0.03],
             foot="paw", neck_pivot=(0.30, 0, 0.49), tail_pivot=(-0.36, 0, 0.51))
    q.extras["neck_root_lift"] = 0.0
    h, top = q.h, q.h + q.back
    pale = np.array([0.86, 0.80, 0.70])

    def torso_paint(P, N, C):
        grizzle = mottle(P, 0.012, 0.12) * mottle(P, 0.04, 0.06, 1.3)                    # agouti hairs
        C = C * grizzle[:, None]
        saddle = smooth(top - 0.08, top + 0.01, P[:, 2]) * smooth(-0.3, 0.2, P[:, 0])
        C = mix(C, coat * 0.55, saddle * 0.6)                                           # darker grizzled saddle
        stripe = smooth(0.03, 0.0, np.abs(P[:, 1])) * smooth(top - 0.04, top + 0.01, P[:, 2])
        cross = smooth(0.06, 0.0, np.abs(P[:, 0] - q.shoulder_x + 0.04)) * smooth(top - 0.1, top - 0.02, P[:, 2])
        C = mix(C, DARK * 2, np.clip(stripe + 0.6 * cross, 0, 1) * 0.6)                # black dorsal stripe, shoulder cross
        return mix(C, pale, smooth(h + 0.02, h - 0.06, P[:, 2]) * smooth(0.1, -0.6, N[:, 2]))

    def head_paint(P, N, C):
        C = C * mottle(P, 0.012, 0.1)[:, None]
        throat = smooth(0.0, -0.7, N[:, 2]) * smooth(0.05, 0.2, P[:, 0])
        cheek = smooth(0.24, 0.30, P[:, 0]) * smooth(0.13, 0.10, P[:, 2]) * smooth(0.02, 0.035, np.abs(P[:, 1]))
        muzzle = smooth(0.24, 0.30, P[:, 0]) * smooth(0.13, 0.11, P[:, 2])
        C = mix(C, np.array([0.80, 0.62, 0.38]), _not_dark(C, muzzle * 0.6))          # yellowish muzzle
        return mix(mix(C, pale, _not_dark(C, throat)), coat * 1.15, cheek * 0.5)

    def tail_paint(P, N, C):                                                          # black-tipped brush
        C = C * mottle(P, 0.012, 0.12)[:, None]
        return mix(mix(C, coat * 0.5, smooth(-0.05, -0.2, P[:, 2]) * 0.4), DARK, smooth(-0.27, -0.31, P[:, 2]))

    def ear_paint(P, N, C):   # pale fronts, reddish backs
        return mix(mix(C, np.array([0.66, 0.40, 0.22]), smooth(0.0, -0.6, N[:, 0])), pale, smooth(0.0, 0.7, N[:, 0]) * 0.6)

    def sock(P, N, C, l):
        return mix(C, pale, smooth(0.0, 0.8, N[:, 0]) * 0.25)
    tf, th, sf, shh, sp = _quad_legs(q, coat, coat * 0.95, DARK, sock)
    return dict(q=q, torso=_quad_torso(q, coat, torso_paint), head=_quad_head(q, coat, head_paint, ear_paint=ear_paint),
                neck_pivot=q.neck_pivot, tail=_quad_tail(q, coat, tail_paint), tail_pivot=q.tail_pivot,
                thigh_fore=tf, thigh_hind=th, shank_fore=sf, shank_hind=shh, splits=sp, graze=np.radians(110), flag=0.0)


# ── raccoon ─────────────────────────────────────────────────────────────────

def raccoon(rgb):
    coat = np.asarray(rgb, float)
    q = Quad(h=0.17, back=0.10, shoulder_x=0.17, hip_x=-0.15, half_w=0.10, depth=0.19, leg_y=0.06,
             leg_r=(0.035, 0.022, 0.018), hunch=0.05,
             neck=[(-0.05, 0, -0.03), (0.04, 0, 0.02)], neck_r=[0.06, 0.065],
             skull=((0.09, 0, 0.04), (0.075, 0.07, 0.06), 0.0),
             muzzle=((0.12, 0, 0.02), (0.20, 0, 0.0), 0.035, 0.015), nose_r=0.012,
             ears=((0.07, 0.05, 0.11), (0.022, 0.01, 0.027), 0.35, -0.2, "pointed"),
             eye=((0.135, 0.032, 0.05), 0.009),
             tail=[(0, 0, 0), (-0.12, 0, -0.05), (-0.25, 0, -0.10)], tail_r=[0.035, 0.05, 0.04],
             foot="paw", neck_pivot=(0.21, 0, 0.22), tail_pivot=(-0.24, 0, 0.29))
    q.extras["neck_root_lift"] = -0.01
    h, top = q.h, q.h + q.back
    grey = np.array([0.55, 0.53, 0.50])

    def torso_paint(P, N, C):
        C = C * (mottle(P, 0.01, 0.15) * mottle(P, 0.03, 0.08, 2.0))[:, None]          # long grizzled guard hairs
        return mix(C, coat * 1.25, smooth(h + 0.05, h - 0.02, P[:, 2]) * 0.5)

    def head_paint(P, N, C):
        C = C * mottle(P, 0.01, 0.1)[:, None]
        mask = smooth(0.17, 0.11, P[:, 0]) * smooth(0.08, 0.13, P[:, 0]) * \
            smooth(0.02, 0.04, P[:, 2]) * smooth(0.075, 0.058, P[:, 2])               # the black bandit mask
        brow = smooth(0.12, 0.15, P[:, 0]) * smooth(0.06, 0.08, P[:, 2]) * smooth(0.10, 0.085, P[:, 2])
        muzzle = smooth(0.15, 0.17, P[:, 0]) * smooth(0.035, 0.02, P[:, 2])
        C = mix(C, WHITE, _not_dark(C, np.clip(brow + muzzle + 0.8 * smooth(0, -0.7, N[:, 2]) * smooth(0.05, 0.12, P[:, 0]),
                                               0, 1)))
        return mix(C, DARK * 1.4, mask)

    def tail_paint(P, N, C):                                                         # 5 black rings and a black tip
        u = -P[:, 0] / 0.27
        rings = 0.5 + 0.5 * np.cos(2 * np.pi * 5 * u)
        C = mix(C * mottle(P, 0.01, 0.1)[:, None], grey * 1.15, np.ones(len(P)) * 0.5)
        return mix(C, DARK * 1.3, np.clip(smooth(0.55, 0.85, rings) * smooth(0.05, 0.12, u) + smooth(0.9, 0.98, u), 0, 1))

    def ear_paint(P, N, C):
        return mix(C, WHITE, smooth(0.11, 0.13, P[:, 2]) * 0.8)                     # white-rimmed ears
    tf, th, sf, shh, sp = _quad_legs(q, coat, coat * 0.45, DARK)
    return dict(q=q, torso=_quad_torso(q, coat, torso_paint), head=_quad_head(q, coat, head_paint, ear_paint=ear_paint),
                neck_pivot=q.neck_pivot, tail=_quad_tail(q, coat, tail_paint), tail_pivot=q.tail_pivot,
                thigh_fore=tf, thigh_hind=th, shank_fore=sf, shank_hind=shh, splits=sp, graze=np.radians(70), flag=0.0)


# ── nine-banded armadillo ───────────────────────────────────────────────────

def armadillo(rgb):
    shell = np.asarray(rgb, float)
    skin = np.array([0.72, 0.62, 0.55])
    q = Quad(h=0.08, back=0.11, shoulder_x=0.13, hip_x=-0.13, half_w=0.085, depth=0.15, leg_y=0.06,
             leg_r=(0.022, 0.016, 0.013),
             neck=[(-0.03, 0, -0.01), (0.02, 0, 0.0)], neck_r=[0.04, 0.04],
             skull=((0.05, 0, 0.0), (0.055, 0.04, 0.04), 0.25),
             muzzle=((0.07, 0, -0.01), (0.17, 0, -0.05), 0.026, 0.009), nose_r=0.007,
             ears=((0.035, 0.03, 0.045), (0.012, 0.005, 0.019), 0.35, -0.35, "pointed"),
             eye=((0.08, 0.026, 0.012), 0.005),
             tail=[(0, 0, 0), (-0.12, 0, -0.05), (-0.26, 0, -0.12)], tail_r=[0.03, 0.018, 0.006],
             foot="paw", neck_pivot=(0.21, 0, 0.13), tail_pivot=(-0.22, 0, 0.14))
    q.extras["neck_root_lift"] = -0.02

    # the carapace is its own sculpture on a finer grid: shoulder and hip shields, 9 raised bands between them,
    # all overhanging the body like a skirt
    cap = Sculpt()
    cap.ellipsoid((0.0, 0, 0.16), (0.25, 0.112, 0.092), shell, k=0.04)              # one dome, nose to tail
    cap.ellipsoid((0.15, 0, 0.17), (0.08, 0.108, 0.085), shell, k=0.06)             # scapular shield
    cap.ellipsoid((-0.15, 0, 0.17), (0.09, 0.114, 0.088), shell, k=0.06)            # pelvic shield

    def bands(P):   # 9 ridges between the shields, each a raised lip 3 mm high
        x = P[:, 0]
        inband = smooth(-0.105, -0.095, x) * smooth(0.105, 0.095, x)
        return -0.005 * inband * np.cos(np.pi * (x + 0.099) / 0.022) ** 8
    cap.displace(bands)

    def torso_paint(P, N, C):   # the soft, pale, sparsely haired underside below the shell
        return C * mottle(P, 0.01, 0.06)[:, None]

    def head_paint(P, N, C):   # a scaly head shield; the long snout soft and pinkish
        C = C * (0.9 + 0.1 * np.sign(np.sin(P[:, 0] * 300) * np.sin(P[:, 1] * 300)))[:, None]
        return mix(C, np.array([0.78, 0.6, 0.55]), smooth(0.09, 0.13, P[:, 0]))

    def tail_paint(P, N, C):   # 12–15 rings of scales
        u = -P[:, 0]
        return C * (1 - 0.3 * smooth(0.7, 1.0, np.cos(2 * np.pi * u / 0.02) ** 2))[:, None]
    def cap_paint(P, N, C):  # stippled scutes, the bands' leading edges darker
        x = P[:, 0]
        inband = smooth(-0.105, -0.095, x) * smooth(0.105, 0.095, x)
        edge = inband * smooth(0.6, 1.0, np.sin(np.pi * (x + 0.099) / 0.022) ** 2)
        C = C * (0.9 + 0.1 * np.sign(np.sin(P[:, 0] * 420) * np.sin(P[:, 1] * 420 + P[:, 2] * 300)))[:, None]
        lip = inband * np.cos(np.pi * (x + 0.099) / 0.022) ** 8
        return C * (1 - 0.35 * edge + 0.15 * lip)[:, None]
    tf, th, sf, shh, sp = _quad_legs(q, skin, skin * 0.9, DARK * 2)
    body = merge([_quad_torso(q, skin, torso_paint), cap.mesh(target=2600, colour_fn=cap_paint)])
    return dict(q=q, torso=body,
                head=_quad_head(q, shell, head_paint, ear_col=skin * 0.9),
                neck_pivot=q.neck_pivot, tail=_quad_tail(q, shell, tail_paint), tail_pivot=q.tail_pivot,
                thigh_fore=tf, thigh_hind=th, shank_fore=sf, shank_hind=shh, splits=sp, graze=np.radians(60), flag=0.0)


# ── eastern gray squirrel ───────────────────────────────────────────────────

def squirrel(rgb):
    """Hops (rig kind 'hop'): one sculpture with its legs tucked; the tail is the S-curved plume."""
    coat = np.asarray(rgb, float)
    s = Sculpt()
    s.ellipsoid((0.0, 0, 0.09), (0.11, 0.045, 0.055), coat, k=0.03, R=rot(pitch=-0.35))      # body, sitting up a little
    s.ellipsoid((-0.06, 0, 0.065), (0.06, 0.05, 0.055), coat, k=0.03)                       # haunches
    s.ellipsoid((0.11, 0, 0.14), (0.045, 0.034, 0.036), coat, k=0.02)                       # head
    s.cone((0.12, 0, 0.135), (0.165, 0, 0.125), 0.025, 0.012, coat, k=0.015)               # muzzle
    for y in (0.03, -0.03):
        s.ellipsoid((-0.05, y * 1.2, 0.03), (0.055, 0.016, 0.025), coat, k=0.015)           # hind feet, long
        s.cone((0.05, y, 0.07), (0.08, y * 0.8, 0.02), 0.012, 0.008, coat, k=0.01)          # fore legs
    bits = []
    for sgn in (1, -1):
        bits.append(Sculpt().ellipsoid((0.10, 0.022 * sgn, 0.178), (0.012, 0.005, 0.017), coat * 0.9, k=0.005,
                                       R=rot(roll=-0.3 * sgn)))
        bits.append(Sculpt().ellipsoid((0.135, 0.026 * sgn, 0.15), (0.0075,) * 3, DARK))
    t = Sculpt().chain([(-0.09, 0, 0.07), (-0.16, 0, 0.13), (-0.15, 0, 0.24), (-0.09, 0, 0.30)],
                       [0.025, 0.04, 0.045, 0.03], coat * 0.95, k=0.03)                       # the plume, an S up the back

    def paint(P, N, C):
        C = C * mottle(P, 0.008, 0.1)[:, None] * np.array([1.0, 0.93, 0.85])      # agouti: brownish-grey back
        belly = smooth(-0.2, -0.7, N[:, 2]) * smooth(0.05, 0.08, P[:, 2]) + smooth(0.3, 0.8, N[:, 0]) * \
            smooth(0.13, 0.09, P[:, 2]) * smooth(0.07, 0.10, P[:, 2]) * smooth(0.02, 0.06, P[:, 0])
        flank = smooth(0.0, 0.5, np.abs(N[:, 1])) * smooth(0.05, 0.1, P[:, 2]) * 0.3
        C = mix(C, np.array([0.62, 0.45, 0.3]), flank)                                   # the rusty wash on the flanks
        return mix(C, WHITE, _not_dark(C, np.clip(belly, 0, 1)))

    def tail_paint(P, N, C):                                                        # frosted: pale-tipped hairs
        return mix(C * mottle(P, 0.006, 0.18)[:, None], WHITE * 0.95, smooth(0.6, 0.95, np.abs(N[:, 1])) * 0.3)
    body = merge([s.mesh(target=2200, colour_fn=paint), t.mesh(target=900, colour_fn=tail_paint)] +
                 [b.mesh(target=BUDGET["eye"]) for b in bits])
    return dict(body=body)


# ── birds ───────────────────────────────────────────────────────────────────

def _bird_leg(h, col, toes_col=None, spur=False, thigh_feather=None, thigh_r=0.18, tarsus=None):
    """Bird leg in the rig's two segments: feathered drumstick above the intertarsal joint, scaly tarsus and
    three forward toes and one back toe below. `tarsus` (m) sets the lower segment; default half the leg."""
    Ltot = h / 0.95
    l2 = Ltot / 2 if tarsus is None else tarsus
    l1 = Ltot - l2
    l = l1
    toes_col = col if toes_col is None else toes_col
    a = Sculpt()
    feathered = 0.55 if thigh_r >= 0.12 else 0.3       # waders show bare tibia below a short feathered thigh
    a.cone((0, 0, 0.02 * l), (0, 0, -l * feathered), thigh_r * l, 0.07 * l,
           thigh_feather if thigh_feather is not None else col, k=0.06 * l)
    a.cone((0, 0, -l * feathered), (0, 0, -l), 0.06 * l, 0.045 * l, col, k=0.03 * l)
    u = Ltot / 2      # toe and tarsus girth scale with the whole leg, not the segment
    b = Sculpt()
    b.cone((0, 0, 0), (0, 0, -l2 * 0.95), 0.045 * u, 0.035 * u, col, k=0.02 * u)
    toes = Sculpt()
    for ang in (-0.45, 0.0, 0.45):
        toes.cone((0, 0, -l2 + 0.04 * u), (0.32 * u * np.cos(ang), 0.32 * u * np.sin(ang), -l2), 0.03 * u, 0.012 * u,
                  toes_col, k=0.01 * u)
    toes.cone((0, 0, -l2 + 0.04 * u), (-0.14 * u, 0, -l2), 0.025 * u, 0.01 * u, toes_col, k=0.01 * u)
    if spur:
        toes.cone((-0.01, 0, -l2 * 0.7), (-0.06 * u, 0, -l2 * 0.72), 0.012 * u, 0.003 * u, DARK * 2, k=0.004)
    def scales(P, N, C):
        return C * (0.88 + 0.12 * np.sign(np.sin(P[:, 2] * 900)))[:, None]
    return a.mesh(target=BUDGET["thigh"]), merge([b.mesh(target=BUDGET["shank"], colour_fn=scales),
                                                  toes.mesh(target=260)]), (l1, l2)


def turkey(rgb):
    plum = np.asarray(rgb, float)
    bronze = np.array([0.55, 0.36, 0.18])
    h = 0.36
    s = Sculpt()
    s.ellipsoid((0.0, 0, h + 0.20), (0.27, 0.17, 0.19), plum, k=0.08, R=rot(pitch=0.15))     # body
    s.ellipsoid((0.17, 0, h + 0.22), (0.13, 0.13, 0.15), plum, k=0.08)                      # breast
    s.ellipsoid((-0.2, 0, h + 0.17), (0.16, 0.14, 0.13), plum, k=0.08)                      # rump
    for sgn in (1, -1):                                                                      # folded wings
        s.ellipsoid((-0.03, 0.14 * sgn, h + 0.22), (0.24, 0.04, 0.12), plum, k=0.04, R=rot(pitch=0.12, yaw=0.08 * sgn))
    fan = Sculpt()                                                                           # tail, folded and drooping
    fan.ellipsoid((-0.42, 0, h + 0.14), (0.2, 0.11, 0.025), plum, k=0.03, R=rot(pitch=-0.55))
    beard = Sculpt().cone((0.25, 0, h + 0.26), (0.28, 0, h + 0.03), 0.016, 0.007, DARK * 1.5, k=0.01)   # ~23 cm

    def body_paint(P, N, C):
        # bronze-tipped contour feathers: rows of scallops, iridescent where they face the light
        scal = smooth(0.55, 0.95, np.sin(P[:, 0] * 95 + 3 * np.sin(P[:, 2] * 60)) * np.sin(P[:, 2] * 95 + P[:, 1] * 40))
        C = mix(C, bronze, scal * 0.55 + 0.15 * smooth(0.3, 1.0, N[:, 2]))
        wing = smooth(0.1, 0.14, np.abs(P[:, 1])) * smooth(h + 0.12, h + 0.2, P[:, 2]) * smooth(0.05, -0.15, P[:, 0])
        bars = 0.5 + 0.5 * np.sign(np.sin(P[:, 0] * 160))
        return mix(C, mix(DARK * 2, WHITE * 0.9, bars), wing * 0.8)        # barred primaries and secondaries

    def fan_paint(P, N, C):   # chestnut-tipped tail with a dark subterminal band
        r = np.hypot(P[:, 0] + 0.42, P[:, 2] - h - 0.14)
        return mix(mix(C, bronze * 0.8, 0.3 * np.ones(len(P))), np.array([0.62, 0.42, 0.22]), smooth(0.14, 0.18, r))
    torso = merge([s.mesh(target=3000, colour_fn=body_paint), fan.mesh(target=700, colour_fn=fan_paint),
                   beard.mesh(target=120)])
    pv = np.array([0.25, 0, h + 0.30])
    skin_blue = np.array([0.55, 0.68, 0.85])
    red = np.array([0.78, 0.12, 0.12])
    n = Sculpt()
    n.chain([(-0.04, 0, -0.04), (0.03, 0, 0.12), (0.06, 0, 0.26)], [0.055, 0.03, 0.026], plum, k=0.03)   # neck
    n.ellipsoid((0.08, 0, 0.30), (0.045, 0.03, 0.033), skin_blue, k=0.02)                                # bare head
    n.cone((0.10, 0, 0.30), (0.14, 0, 0.285), 0.012, 0.005, np.array([0.75, 0.7, 0.55]), k=0.006)        # bill
    n.ellipsoid((0.065, 0, 0.21), (0.018, 0.022, 0.05), red, k=0.02)                                    # wattle
    n.cone((0.11, 0, 0.33), (0.135, 0, 0.26), 0.008, 0.005, red, k=0.006)                                # snood

    def head_paint(P, N, C):
        bare = smooth(0.18, 0.24, P[:, 2])
        return mix(C, skin_blue, bare * smooth(0.12, 0.3, lum(C)) * (1 - smooth(0.6, 0.7, C[:, 0] - C[:, 2])))
    eyes = [Sculpt().ellipsoid((0.10, 0.026 * sg, 0.31), (0.007,) * 3, DARK).mesh(target=BUDGET["eye"]) for sg in (1, -1)]
    head = merge([n.mesh(target=1300, colour_fn=head_paint)] + eyes)
    thigh, shank, ls = _bird_leg(h, np.array([0.62, 0.42, 0.38]), spur=True, thigh_feather=plum, tarsus=0.15)
    return dict(torso=torso, head=head, neck_pivot=pv, thigh=thigh, shank=shank, ls=ls, hip=h, graze=np.radians(120))


def heron(rgb):
    blue = np.asarray(rgb, float)
    h = 0.55
    s = Sculpt()
    s.ellipsoid((0.0, 0, h + 0.20), (0.25, 0.11, 0.13), blue, k=0.05, R=rot(pitch=0.25))                 # body
    s.ellipsoid((0.12, 0, h + 0.25), (0.09, 0.09, 0.10), blue, k=0.05)                                   # chest
    for sg in (1, -1):                                                                                   # folded wings
        s.ellipsoid((-0.05, 0.085 * sg, h + 0.22), (0.25, 0.035, 0.1), blue * 0.95, k=0.03, R=rot(pitch=0.2))
    s.ellipsoid((-0.23, 0, h + 0.13), (0.12, 0.07, 0.03), blue * 0.8, k=0.03, R=rot(pitch=0.35))        # tail
    s.cone((0.1, 0, h + 0.2), (0.22, 0, h + 0.05), 0.04, 0.012, np.array([0.8, 0.8, 0.78]), k=0.03)    # breast plumes

    def body_paint(P, N, C):
        thigh = smooth(h + 0.12, h + 0.06, P[:, 2]) * smooth(0.04, 0.0, np.abs(P[:, 0]))
        streak = smooth(0.0, -0.6, N[:, 2]) * smooth(0.0, 0.15, P[:, 0])
        C = mix(C, np.array([0.55, 0.32, 0.2]), thigh)                    # rufous thighs
        return mix(C, mix(WHITE, DARK * 3, smooth(0.6, 0.9, np.sin(P[:, 1] * 300) ** 2)), streak * 0.6)
    torso = s.mesh(target=2400, colour_fn=body_paint)
    pv = np.array([0.14, 0, h + 0.27])
    yellow = np.array([0.88, 0.72, 0.25])
    n = Sculpt()   # the S-neck: back, forward, up
    n.chain([(-0.02, 0, -0.03), (0.07, 0, 0.1), (0.02, 0, 0.22), (0.08, 0, 0.33)], [0.04, 0.028, 0.026, 0.024],
            blue * 1.05, k=0.02)
    n.ellipsoid((0.11, 0, 0.35), (0.04, 0.025, 0.028), WHITE, k=0.015)                                 # head
    n.cone((0.13, 0, 0.35), (0.27, 0, 0.335), 0.014, 0.002, yellow, k=0.006)                             # dagger bill
    n.cone((0.09, 0, 0.37), (-0.04, 0, 0.36), 0.008, 0.002, DARK, k=0.005)                               # black plume

    def head_paint(P, N, C):
        crown = smooth(0.365, 0.375, P[:, 2]) * smooth(0.07, 0.09, P[:, 0]) * smooth(0.14, 0.12, P[:, 0])
        stripe = smooth(0.012, 0.02, np.abs(P[:, 1])) * crown
        foreneck = smooth(0.0, 0.7, N[:, 0]) * smooth(0.3, 0.05, P[:, 2]) * \
            smooth(0.6, 0.9, np.sin(P[:, 2] * 220) ** 2)          # streaked foreneck
        C = mix(C, mix(WHITE * 0.9, DARK * 2, smooth(0.4, 0.9, np.sin(P[:, 2] * 220) ** 2)), foreneck * 0.5)
        return mix(C, DARK, np.maximum(stripe, crown * 0.0))
    eyes = [Sculpt().ellipsoid((0.125, 0.02 * sg, 0.355), (0.006,) * 3, yellow * 0.9).mesh(target=BUDGET["eye"])
            for sg in (1, -1)]
    head = merge([n.mesh(target=1400, colour_fn=head_paint)] + eyes)
    legcol = np.array([0.32, 0.28, 0.22])
    thigh, shank, ls = _bird_leg(h, legcol, thigh_feather=np.array([0.55, 0.32, 0.2]), thigh_r=0.08, tarsus=0.19)
    wings = []
    for side in (1.0, -1.0):   # broad wings, extended along ±y from the shoulder; dark primaries at the tip
        w = Sculpt()
        w.chain([(0, 0.02 * side, 0), (0.05, 0.3 * side, 0), (0.0, 0.62 * side, 0), (-0.1, 0.88 * side, 0)],
                [0.03, 0.025, 0.018, 0.008], blue, k=0.04)
        w.ellipsoid((-0.08, 0.45 * side, 0), (0.17, 0.42, 0.012), blue, k=0.04)

        def wing_paint(P, N, C, side=side):
            return mix(C, DARK * 2, smooth(0.6, 0.75, P[:, 1] * side) * smooth(-0.05, -0.15, P[:, 0]) +
                       smooth(0.75, 0.85, P[:, 1] * side) * 0.8)
        wings.append(dict(mesh=w.mesh(target=900, colour_fn=wing_paint), side=side,
                          pivot=(0.02, 0.08 * side, h + 0.24)))
    return dict(torso=torso, head=head, neck_pivot=pv, thigh=thigh, shank=shank, ls=ls, hip=h, wings=wings,
                graze=np.radians(105))


# ── eastern box turtle ──────────────────────────────────────────────────────

def box_turtle(rgb):
    shell = np.asarray(rgb, float)
    yellow = np.array([0.88, 0.66, 0.18])
    h = 0.02
    cap = Sculpt()
    cap.ellipsoid((0, 0, h + 0.010), (0.075, 0.053, 0.034), shell, k=0.01)       # high dome (shell height 5.3 cm)
    cap.ellipsoid((0, 0, h + 0.004), (0.078, 0.055, 0.008), shell * 0.9, k=0.006)   # marginal rim
    cap.ellipsoid((0, 0, h - 0.004), (0.072, 0.05, 0.006), yellow * 0.75, k=0.004)  # plastron
    vert = [(-0.045, 0), (-0.022, 0), (0.0, 0), (0.022, 0), (0.045, 0)]
    cost = [(x, sg * 0.032) for x in (-0.035, -0.012, 0.012, 0.035) for sg in (1, -1)]
    scutes = np.array(vert + cost)

    def keel(P):   # a faint mid-line keel and the scute seams pressed in
        dx = P[:, None, :2] - scutes[None]
        d = np.sort(np.linalg.norm(dx, axis=2), axis=1)
        seam = smooth(0.004, 0.0, d[:, 1] - d[:, 0])
        return 0.0012 * seam - 0.002 * smooth(0.012, 0.0, np.abs(P[:, 1])) * smooth(h + 0.02, h + 0.05, P[:, 2])
    cap.displace(keel)

    def cap_paint(P, N, C):   # each scute: dark ground, yellow streaks radiating from its growth centre
        dx = P[:, None, :2] - scutes[None]
        dist = np.linalg.norm(dx, axis=2)
        k = np.argmin(dist, 1)
        v = dx[np.arange(len(P)), k]
        ang = np.arctan2(v[:, 1], v[:, 0])
        rays = smooth(0.5, 0.9, np.sin(ang * 5 + k) ** 2) * smooth(0.002, 0.008, dist[np.arange(len(P)), k])
        d2 = np.sort(dist, 1)
        seam = smooth(0.003, 0.0, d2[:, 1] - d2[:, 0])
        top = smooth(h + 0.0, h + 0.01, P[:, 2])
        C = mix(C, yellow, rays * 0.75 * top)
        return mix(C, DARK * 1.5, seam * top * 0.7)
    torso = cap.mesh(target=2600, colour_fn=cap_paint)
    pv = np.array([0.07, 0, h + 0.005])
    skin = np.array([0.42, 0.30, 0.18])
    n = Sculpt()
    n.cone((-0.03, 0, 0), (0.015, 0, 0.004), 0.011, 0.01, skin, k=0.006)
    n.ellipsoid((0.025, 0, 0.006), (0.017, 0.012, 0.011), skin, k=0.006)
    n.cone((0.03, 0, 0.003), (0.042, 0, -0.001), 0.007, 0.004, skin * 0.8, k=0.003)   # hooked beak

    def head_paint(P, N, C):
        return mix(C, np.array([0.9, 0.5, 0.15]), smooth(0.6, 0.95, np.sin(P[:, 0] * 900) * np.sin(P[:, 1] * 900 + 1)))
    eyes = [Sculpt().ellipsoid((0.033, 0.009 * sg, 0.01), (0.0028,) * 3, np.array([0.8, 0.2, 0.1])).mesh(target=40)
            for sg in (1, -1)]
    head = merge([n.mesh(target=600, colour_fn=head_paint)] + eyes)
    l = h / 0.95 / 2
    leg = Sculpt().cone((0, 0, 0.004), (0.004, 0, -l), 0.009, 0.007, skin, k=0.004)
    foot = Sculpt().ellipsoid((0.006, 0, -l + 0.002), (0.011, 0.008, 0.004), skin * 0.85, k=0.003)
    thigh = leg.mesh(target=160)
    return dict(torso=torso, head=head, neck_pivot=pv, thigh=thigh, shank=foot.mesh(target=120), ls=(l, l), hip=h,
                graze=np.radians(35))


# ── a person walking ────────────────────────────────────────────────────────

def human(rgb):
    shirt = np.asarray(rgb, float)
    jeans = np.array([0.22, 0.27, 0.38])
    skin = np.array([0.72, 0.55, 0.42])
    hair = np.array([0.20, 0.15, 0.11])
    hip = 0.9
    s = Sculpt()
    s.ellipsoid((0, 0, hip + 0.04), (0.10, 0.17, 0.11), jeans, k=0.04)                    # pelvis
    s.ellipsoid((0.0, 0, hip + 0.30), (0.11, 0.17, 0.22), shirt, k=0.08)                  # trunk
    s.ellipsoid((0.02, 0, hip + 0.44), (0.11, 0.2, 0.11), shirt, k=0.06)                  # chest, shoulders
    for sg in (1, -1):
        s.chain([(0.0, 0.2 * sg, hip + 0.50), (0.0, 0.22 * sg, hip + 0.22), (0.05, 0.22 * sg, hip - 0.02)],
                [0.045, 0.038, 0.03], shirt, k=0.03)                                       # arms
        s.ellipsoid((0.06, 0.22 * sg, hip - 0.07), (0.035, 0.022, 0.05), skin, k=0.02)    # hands
    s.cone((0.01, 0, hip + 0.52), (0.015, 0, hip + 0.62), 0.05, 0.045, skin, k=0.03)     # neck
    s.ellipsoid((0.02, 0, hip + 0.73), (0.095, 0.08, 0.115), skin, k=0.03)                # head
    s.ellipsoid((0.0, 0, hip + 0.77), (0.1, 0.085, 0.1), hair, k=0.02)                    # hair
    s.cone((0.10, 0, hip + 0.73), (0.125, 0, hip + 0.70), 0.015, 0.012, skin, k=0.01)    # nose
    for sg in (1, -1):
        s.ellipsoid((0.0, 0.085 * sg, hip + 0.72), (0.02, 0.012, 0.03), skin, k=0.01)     # ears

    def paint(P, N, C):
        face = smooth(0.2, 0.7, N[:, 0]) * smooth(hip + 0.63, hip + 0.66, P[:, 2]) * smooth(hip + 0.82, hip + 0.78, P[:, 2])
        return mix(C, skin, face * smooth(0.0, 0.06, P[:, 0]))
    eyes = [Sculpt().ellipsoid((0.105, 0.035 * sg, hip + 0.745), (0.008,) * 3, DARK).mesh(target=40) for sg in (1, -1)]
    torso = merge([s.mesh(target=4200, colour_fn=paint)] + eyes)
    l = hip / 0.95 / 2
    th = Sculpt().cone((0, 0, 0.04), (0, 0, -l), 0.075, 0.055, jeans, k=0.03).mesh(target=BUDGET["thigh"])
    sh = Sculpt()
    sh.cone((0, 0, 0), (0, 0, -l + 0.07), 0.055, 0.04, jeans, k=0.02)
    sh.ellipsoid((0.04, 0, -l + 0.04), (0.13, 0.05, 0.045), np.array([0.3, 0.22, 0.15]), k=0.02)   # boot
    return dict(torso=torso, thigh=th, shank=sh.mesh(target=500), ls=(l, l), hip=hip)

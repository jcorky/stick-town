"""Low-poly procedural bodies for animals and people (facing +x, z-up, feet at z=0).

Bodies are rigs (torso + legs pivoting at the hips) so the viewer can swing the legs by gait (gait.py, §25).
Each individual gets slight size/colour variation from its seed.
"""

from __future__ import annotations

import numpy as np

from ..mesh import Mesh, MeshBuilder, box


def ellipsoid(c, r, rgb, nu=10, nv=6):
    u = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    v = np.linspace(0, np.pi, nv + 1)
    U, V = np.meshgrid(u, v)
    P = np.stack([np.cos(U) * np.sin(V) * r[0], np.sin(U) * np.sin(V) * r[1], np.cos(V) * r[2]], -1).reshape(-1, 3) + c
    idx = []
    for i in range(nv):
        for j in range(nu):
            a, b = i * nu + j, i * nu + (j + 1) % nu
            idx += [(a, a + nu, b), (b, a + nu, b + nu)]
    mb = MeshBuilder()
    mb.add(P, rgb, idx)
    return mb.build()


def rig(key, rgb, scale=1.0):
    """Body split for gait animation: dict(torso=Mesh, legs=[dict(thigh, shank, hip, knee, l1, l2)],
    neck=dict(mesh, pivot, graze) or None, tail=dict(mesh, pivot, flag) or None, hip=hip height h (m),
    kind='quad'|'biped'|'hop'|'none', lie=trunk drop when lying, as a fraction of h). Legs are ordered LF, RF, LH, RH (bipeds L, R).
    Thigh and shank hang straight down from their own origins (hip, knee); together they are h / 0.95 long, so
    the rest pose (gait.rest_pose) is slightly flexed. knee = +1 bends forward (stifle, human knee), −1 backward
    (a deer's carpus, a bird's intertarsal joint)."""
    from .gait import REACH
    rgb = np.asarray(rgb)
    parts, legs, hip, kind = [], [], 0.0, "none"
    neck = None  # dict(mesh relative to the pivot, pivot xyz, graze=head-down pitch in radians)
    tail = None  # dict(mesh relative to the pivot, pivot xyz, flag=raise angle in radians)
    wings = []   # [dict(mesh relative to the root, pivot xyz, side ±1)] for fliers (§33)

    def leg(x, y, h, w, col, knee):
        L = h * REACH
        l1 = l2 = L / 2
        legs.append(dict(thigh=box((0, 0, -l1 / 2), (w * 1.25, w * 1.25, l1), col),
                         shank=box((0, 0, -l2 / 2), (w, w, l2), np.asarray(col) * 0.9),
                         hip=(x, y, h), knee=knee, l1=l1, l2=l2))
    if key in ("white_tailed_deer", "coyote"):
        L = 0.75 if key == "white_tailed_deer" else 0.5
        h = 0.95 if key == "white_tailed_deer" else 0.5
        parts += [ellipsoid((0, 0, h), (L, 0.22 * L / 0.75 + 0.05, 0.25 * L / 0.75 + 0.03), rgb)]
        pv = np.array([L * 0.7, 0, h + 0.05])
        neck = dict(mesh=Mesh.merge([ellipsoid(np.array([L * 0.8, 0, h + 0.3 * L]) - pv, (0.12, 0.07, 0.25 * L), rgb),
                                     ellipsoid(np.array([L * 1.05, 0, h + 0.55 * L]) - pv,
                                               (0.2 * L / 0.75 + 0.05, 0.07, 0.08), rgb * 0.9)]),
                    pivot=tuple(pv), graze=np.radians(110))
        for x, knee in ((L * 0.6, -1.0), (-L * 0.6, 1.0)):  # fore (carpus bends back), then hind (stifle forward)
            for y in (0.1, -0.1):                            # left (+y), then right
                leg(x, y, h, 0.06, rgb * 0.8, knee)
        if key == "white_tailed_deer":  # the white flag: raised when fleeing (§29)
            tp = np.array([-L * 0.9, 0, h + 0.08])
            tail = dict(mesh=ellipsoid(np.array([-L * 1.0, 0, h + 0.05]) - tp, (0.12, 0.05, 0.08), (0.95, 0.95, 0.92)),
                        pivot=tuple(tp), flag=np.radians(100))
        else:
            parts.append(ellipsoid((-L * 1.0, 0, h + 0.05), (0.12, 0.05, 0.08), rgb * 0.8))
        if key == "coyote":
            parts.append(ellipsoid((-L * 1.2, 0, h - 0.1), (0.25, 0.06, 0.07), rgb * 0.75))
        hip, kind = h, "quad"
    elif key == "gray_squirrel":
        parts += [ellipsoid((0, 0, 0.1), (0.12, 0.05, 0.06), rgb),
                  ellipsoid((0.12, 0, 0.14), (0.05, 0.04, 0.04), rgb),
                  ellipsoid((-0.15, 0, 0.2), (0.06, 0.05, 0.14), rgb * 1.1)]
        hip, kind = 0.1, "hop"
    elif key == "wild_turkey":
        parts += [ellipsoid((0, 0, 0.55), (0.32, 0.2, 0.22), rgb),
                  ellipsoid((-0.3, 0, 0.6), (0.12, 0.25, 0.08), rgb * 0.8)]
        pv = np.array([0.25, 0, 0.65])
        neck = dict(mesh=Mesh.merge([ellipsoid(np.array([0.3, 0, 0.82]) - pv, (0.04, 0.04, 0.16), (0.55, 0.65, 0.75)),
                                     ellipsoid(np.array([0.33, 0, 0.98]) - pv, (0.06, 0.04, 0.05), (0.7, 0.15, 0.15))]),
                    pivot=tuple(pv), graze=np.radians(120))
        for y in (0.08, -0.08):
            leg(0.02, y, 0.36, 0.03, (0.6, 0.35, 0.3), -1.0)  # the visible "knee" is the intertarsal joint
        hip, kind = 0.36, "biped"
    elif key == "armadillo":
        parts += [ellipsoid((0, 0, 0.14), (0.25, 0.12, 0.12), rgb),
                  ellipsoid((0.27, 0, 0.1), (0.08, 0.04, 0.04), rgb * 0.9),
                  ellipsoid((-0.33, 0, 0.08), (0.15, 0.025, 0.025), rgb * 0.9)]
        for x, knee in ((0.14, -1.0), (-0.14, 1.0)):
            for y in (0.08, -0.08):
                leg(x, y, 0.08, 0.04, rgb * 0.7, knee)
        hip, kind = 0.08, "quad"
    elif key == "raccoon":  # shoulder 0.27 m (SC DNR 9–10 in, NCpedia 12 in), ringed tail ~45 % of total length
        h = 0.27
        parts += [ellipsoid((0, 0, h + 0.03), (0.24, 0.11, 0.12), rgb)]
        for i in range(6):  # ringed tail, alternating dark and light
            parts.append(ellipsoid((-0.25 - 0.045 * i, 0, h + 0.06 - 0.01 * i), (0.03, 0.045, 0.045),
                                   rgb * (0.45 if i % 2 else 1.15)))
        pv = np.array([0.2, 0, h + 0.06])
        neck = dict(mesh=Mesh.merge([ellipsoid(np.array([0.29, 0, h + 0.07]) - pv, (0.08, 0.07, 0.065), rgb * 1.1),
                                     ellipsoid(np.array([0.31, 0, h + 0.085]) - pv, (0.05, 0.075, 0.02), rgb * 0.3),
                                     ellipsoid(np.array([0.37, 0, h + 0.06]) - pv, (0.035, 0.025, 0.025), rgb * 0.9)]),
                    pivot=tuple(pv), graze=np.radians(70))
        for x, knee in ((0.15, -1.0), (-0.15, 1.0)):
            for y in (0.07, -0.07):
                leg(x, y, h, 0.04, rgb * 0.35, knee)
        hip, kind = h, "quad"
    elif key == "box_turtle":  # carapace ~15 × 10 cm, shell height 5.3 cm (ADW; Maryville College)
        h = 0.02
        parts += [ellipsoid((0, 0, h + 0.01), (0.075, 0.05, 0.03), rgb),              # domed carapace
                  ellipsoid((0, 0, h + 0.002), (0.077, 0.052, 0.006), (0.75, 0.6, 0.25))]  # yellow rim
        pv = np.array([0.07, 0, h + 0.005])
        neck = dict(mesh=ellipsoid(np.array([0.095, 0, h + 0.012]) - pv, (0.025, 0.017, 0.016), (0.55, 0.4, 0.2)),
                    pivot=tuple(pv), graze=np.radians(35))
        for x, knee in ((0.045, -1.0), (-0.045, 1.0)):
            for y in (0.04, -0.04):
                leg(x, y, h, 0.018, (0.45, 0.32, 0.15), knee)
        hip, kind = h, "quad"
    elif key == "great_blue_heron":  # stands ~1.1–1.2 m (TWRA 46 in); hip 0.55 m is a design value
        h = 0.55
        parts += [ellipsoid((0, 0, h + 0.2), (0.22, 0.1, 0.12), rgb),
                  ellipsoid((-0.25, 0, h + 0.17), (0.1, 0.07, 0.04), rgb * 0.8)]
        pv = np.array([0.14, 0, h + 0.27])
        neck = dict(mesh=Mesh.merge([ellipsoid(np.array([0.2, 0, h + 0.42]) - pv, (0.04, 0.035, 0.16), rgb * 1.1),
                                     ellipsoid(np.array([0.25, 0, h + 0.6]) - pv, (0.05, 0.04, 0.04), (0.92, 0.92, 0.9)),
                                     ellipsoid(np.array([0.24, 0, h + 0.63]) - pv, (0.05, 0.042, 0.012), (0.1, 0.1, 0.12)),
                                     ellipsoid(np.array([0.36, 0, h + 0.6]) - pv, (0.08, 0.012, 0.012), (0.85, 0.65, 0.2))]),
                    pivot=tuple(pv), graze=np.radians(105))
        for y in (0.05, -0.05):
            leg(0.02, y, h, 0.018, (0.35, 0.3, 0.25), -1.0)
        hip, kind = h, "biped"
        # wings: a broad flat blade per side, root at the shoulder; span 0.9 m (wingspan 1.7–2.0 m, Audubon)
        for side in (1.0, -1.0):
            root = np.array([0.02, 0.08 * side, h + 0.24])
            wings.append(dict(mesh=ellipsoid((0, 0.45 * side, 0), (0.2, 0.45, 0.015), rgb * 0.9), pivot=tuple(root),
                              side=side))
    else:  # human
        parts += [box((0, 0, 1.2), (0.25, 0.42, 0.6), rgb),
                  ellipsoid((0, 0, 1.62), (0.11, 0.1, 0.13), (0.72, 0.55, 0.42))]
        for y in (0.09, -0.09):
            leg(0, y, 0.9, 0.13, (0.25, 0.25, 0.3), 1.0)
        hip, kind = 0.9, "biped"
    torso = Mesh.merge(parts)
    torso.positions *= scale
    for part in (neck, tail, *wings):
        if part is not None:
            part["mesh"].positions *= scale
            part["pivot"] = tuple(c * scale for c in part["pivot"])
    for lg in legs:
        lg["thigh"].positions *= scale
        lg["shank"].positions *= scale
        lg["hip"] = tuple(c * scale for c in lg["hip"])
        lg["l1"] *= scale
        lg["l2"] *= scale
    drop = {"quad": 0.62, "biped": 0.4}.get(kind, 0.0) if key not in ("human", "great_blue_heron", "box_turtle") else 0.0
    return dict(torso=torso, legs=legs, neck=neck, tail=tail, wings=wings, hip=hip * scale, kind=kind, lie=drop)


def _pitch(P, th):
    """Rotate points by a forward-positive pitch θ about the lateral axis (foot below swings toward +x)."""
    c, s = np.cos(th), np.sin(th)
    return P @ np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]], np.float32).T


def posed_legs(r, angles=None):
    """Leg meshes in body coordinates for hip/knee angles [(θ_hip, θ_knee)] (default: the rest pose)."""
    from .gait import rest_pose
    out = []
    for i, lg in enumerate(r["legs"]):
        th1, th2 = angles[i] if angles is not None else rest_pose(r["hip"], lg["l1"], lg["l2"], lg["knee"])
        hip = np.asarray(lg["hip"], np.float32)
        knee = hip + _pitch(np.array([[0, 0, -lg["l1"]]], np.float32), th1)[0]
        out.append(Mesh(_pitch(lg["thigh"].positions, th1) + hip, lg["thigh"].colors, lg["thigh"].indices))
        out.append(Mesh(_pitch(lg["shank"].positions, th1 + th2) + knee, lg["shank"].colors, lg["shank"].indices))
    return out


def body(key, rgb, scale=1.0):
    """The rig merged into one static mesh in its rest pose (previews, the asset library)."""
    r = rig(key, rgb, scale)
    parts = [r["torso"]] + posed_legs(r)
    for n in (r["neck"], r["tail"]):
        if n is not None:
            parts.append(Mesh(n["mesh"].positions + np.asarray(n["pivot"], np.float32), n["mesh"].colors,
                              n["mesh"].indices))
    from .gait import WING_FOLD
    for w in r["wings"]:  # folded: span squeezed toward the body
        P = w["mesh"].positions * np.array([1, WING_FOLD, 1], np.float32)
        parts.append(Mesh(P + np.asarray(w["pivot"], np.float32), w["mesh"].colors, w["mesh"].indices))
    return Mesh.merge(parts)

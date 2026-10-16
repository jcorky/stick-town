"""Procedural bodies for animals and people (facing +x, z-up, feet at z=0), sculpted from blended forms.

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
    neck=dict(mesh, pivot, graze) or None, tail=dict(mesh, pivot, flag) or None, wings=[dict(mesh, pivot, side)],
    hip=hip height h (m), kind='quad'|'biped'|'hop'|'none', lie=trunk drop when lying, as a fraction of h).
    Legs are ordered LF, RF, LH, RH (bipeds L, R). Thigh and shank hang straight down from their own origins (hip,
    knee); l1 + l2 = h / 0.95, so the rest pose (gait.rest_pose) is slightly flexed. knee = +1 bends forward
    (stifle, human knee), −1 backward (a deer's carpus, a bird's intertarsal joint).
    Every part is a sculpture of blended anatomical forms (anatomy.py, sculpt.py; TECHNIQUES §36)."""
    from . import anatomy as A
    rgb = np.asarray(rgb, float)
    legs, neck, tail, wings = [], None, None, []
    build = {"white_tailed_deer": A.deer, "coyote": A.coyote, "raccoon": A.raccoon, "armadillo": A.armadillo}
    if key in build:
        d = build[key](rgb)
        q = d["q"]
        for x, fore, knee in ((q.shoulder_x, True, -1.0), (q.hip_x, False, 1.0)):
            l1, l2 = d["splits"][fore]
            for y in (q.leg_y, -q.leg_y):        # left (+y), then right
                legs.append(dict(thigh=d["thigh_fore" if fore else "thigh_hind"],
                                 shank=d["shank_fore" if fore else "shank_hind"],
                                 hip=(x, y, q.h), knee=knee, l1=l1, l2=l2))
        torso, hip, kind = d["torso"], q.h, "quad"
        neck = dict(mesh=d["head"], pivot=tuple(d["neck_pivot"]), graze=d["graze"])
        tail = dict(mesh=d["tail"], pivot=tuple(d["tail_pivot"]), flag=d["flag"])
    elif key == "gray_squirrel":
        torso, hip, kind = A.squirrel(rgb)["body"], 0.1, "hop"
    elif key in ("wild_turkey", "great_blue_heron", "box_turtle", "human"):
        d = {"wild_turkey": A.turkey, "great_blue_heron": A.heron, "box_turtle": A.box_turtle, "human": A.human}[key](rgb)
        torso, hip = d["torso"], d["hip"]
        l1, l2 = d["ls"]
        if key == "box_turtle":
            kind = "quad"
            for x, knee in ((0.045, -1.0), (-0.045, 1.0)):
                for y in (0.04, -0.04):
                    legs.append(dict(thigh=d["thigh"], shank=d["shank"], hip=(x, y, hip), knee=knee, l1=l1, l2=l2))
        else:
            kind = "biped"
            x, y, knee = {"wild_turkey": (0.02, 0.08, -1.0), "great_blue_heron": (0.02, 0.05, -1.0),
                          "human": (0.0, 0.09, 1.0)}[key]
            for yy in (y, -y):
                legs.append(dict(thigh=d["thigh"], shank=d["shank"], hip=(x, yy, hip), knee=knee, l1=l1, l2=l2))
        if d.get("head") is not None:
            neck = dict(mesh=d["head"], pivot=tuple(d["neck_pivot"]), graze=d["graze"])
        wings = [dict(w) for w in d.get("wings", [])]
    else:
        raise KeyError(key)
    S = np.float32(scale)

    def sc(m):
        out = Mesh(m.positions * S, m.colors, m.indices)
        out.nrm = m.nrm
        return out
    torso = sc(torso)
    for part in (neck, tail, *wings):
        if part is not None:
            part["mesh"] = sc(part["mesh"])
            part["pivot"] = tuple(float(c) * scale for c in part["pivot"])
    for lg in legs:
        lg["thigh"], lg["shank"] = sc(lg["thigh"]), sc(lg["shank"])
        lg["hip"] = tuple(float(c) * scale for c in lg["hip"])
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
        for m, th, at in ((lg["thigh"], th1, hip), (lg["shank"], th1 + th2, knee)):
            M = Mesh(_pitch(m.positions, th) + at, m.colors, m.indices)
            M.nrm = None if m.nrm is None else _pitch(m.nrm, th)
            out.append(M)
    return out


def body(key, rgb, scale=1.0):
    """The rig merged into one static mesh in its rest pose (previews, the asset library)."""
    r = rig(key, rgb, scale)
    from .sculpt import merge
    parts = [r["torso"]] + posed_legs(r)
    for n in (r["neck"], r["tail"]):
        if n is not None:
            M = Mesh(n["mesh"].positions + np.asarray(n["pivot"], np.float32), n["mesh"].colors, n["mesh"].indices)
            M.nrm = n["mesh"].nrm
            parts.append(M)
    from .gait import WING_FOLD
    for w in r["wings"]:  # folded: span squeezed toward the body
        P = w["mesh"].positions * np.array([1, WING_FOLD, 1], np.float32)
        M = Mesh(P + np.asarray(w["pivot"], np.float32), w["mesh"].colors, w["mesh"].indices)
        M.nrm = w["mesh"].nrm
        parts.append(M)
    return merge(parts)

"""Southern vernacular buildings and everyday props.

Kinds: shotgun house, dogtrot, barn, farmhouse (with wraparound porch), church.
Raised on brick piers, metal roofs, porches, screen doors — the details that
make a place read as the rural/small-town South. Local frame: z-up, the
building's front faces +x; `door` is in local coords for desire-path routing.
"""

from __future__ import annotations

import numpy as np

from ..mesh import Mesh, box
from ..rng import rng as make_rng

SIDING = [(0.93, 0.92, 0.88), (0.86, 0.80, 0.60), (0.62, 0.78, 0.80), (0.92, 0.75, 0.70),
          (0.75, 0.82, 0.62), (0.88, 0.88, 0.80), (0.60, 0.55, 0.48)]
ROOF = [(0.62, 0.64, 0.66), (0.55, 0.20, 0.16), (0.24, 0.34, 0.26), (0.40, 0.41, 0.43)]


def gable(x0, x1, y0, y1, z0, rise, color, overhang=0.35, end_rgb=(0.9, 0.9, 0.86)):
    """Gable roof running along x with ridge at y-centre."""
    yc = (y0 + y1) / 2
    x0, x1, y0, y1 = x0 - overhang, x1 + overhang, y0 - overhang, y1 + overhang
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, yc, z0 + rise], [x0, yc, z0 + rise],
                  [x0, y1, z0], [x1, y1, z0]], float)
    faces = [(0, 1, 2), (0, 2, 3), (4, 3, 2), (4, 2, 5)]
    P, I = [], []
    for k, f in enumerate(faces):
        P += [v[i] for i in f]
        I.append((3 * k, 3 * k + 1, 3 * k + 2))
    # gable-end triangles
    for xe, order in ((x0 + overhang, (0, 2, 1)), (x1 - overhang, (0, 1, 2))):
        tri = np.array([[xe, y0 + overhang, z0], [xe, y1 - overhang, z0], [xe, yc, z0 + rise - 0.05]])
        b = len(P)
        P += list(tri[list(order)])
        I.append((b, b + 1, b + 2))
    cols = [color] * 12 + [None] * 6
    C = np.array([c if c is not None else end_rgb for c in cols], float)
    return Mesh(np.array(P, np.float32), C.astype(np.float32), np.array(I, np.uint32))


def _piers(x0, x1, y0, y1, h, r):
    out = []
    for x in np.linspace(x0 + 0.2, x1 - 0.2, max(2, int((x1 - x0) / 2.4) + 1)):
        for y in (y0 + 0.2, y1 - 0.2):
            out.append(box((x, y, h / 2 - 0.2), (0.4, 0.4, h + 0.4), (0.55, 0.28, 0.20) if r.uniform() < 0.8 else (0.6, 0.6, 0.58)))
    return out


def _windows(x0, x1, y, z, n, facing):
    out = []
    for x in np.linspace(x0 + 1.0, x1 - 1.0, n):
        out.append(box((x, y + 0.03 * facing, z), (0.8, 0.06, 1.3), (0.12, 0.14, 0.16)))
        out.append(box((x - 0.5, y + 0.05 * facing, z), (0.12, 0.05, 1.4), (0.18, 0.25, 0.20)))  # shutter
        out.append(box((x + 0.5, y + 0.05 * facing, z), (0.12, 0.05, 1.4), (0.18, 0.25, 0.20)))
    return out


def porch(xf, y0, y1, depth, floor_z, roof_rgb, r):
    parts = [box((xf + depth / 2, (y0 + y1) / 2, floor_z - 0.05), (depth, y1 - y0, 0.12), (0.55, 0.50, 0.44))]
    for y in np.linspace(y0 + 0.15, y1 - 0.15, max(2, int((y1 - y0) / 2.2) + 1)):
        parts.append(box((xf + depth - 0.12, y, floor_z + 1.3), (0.14, 0.14, 2.6), (0.94, 0.94, 0.90)))
    # shed roof
    parts.append(box((xf + depth / 2, (y0 + y1) / 2, floor_z + 2.7), (depth + 0.4, y1 - y0 + 0.4, 0.08), roof_rgb))
    # steps
    for k in range(int(floor_z / 0.18)):
        parts.append(box((xf + depth + 0.3 + 0.28 * k, (y0 + y1) / 2, floor_z - 0.18 * (k + 1) + 0.09),
                         (0.28, 1.4, 0.18), (0.6, 0.58, 0.55)))
    return parts


def generate_building(kind="shotgun", seed=0):
    r = make_rng("building", kind, seed)
    siding = SIDING[int(r.integers(len(SIDING)))]
    roof = ROOF[int(r.integers(len(ROOF)))]
    parts = []
    pier_h = r.uniform(0.6, 1.0)
    if kind == "shotgun":
        L, W, H = r.uniform(12, 16), r.uniform(3.6, 4.4), 3.2
        x0, x1, y0, y1 = -L, 0.0, -W / 2, W / 2
        parts += _piers(x0, x1, y0, y1, pier_h, r)
        parts.append(box(((x0 + x1) / 2, 0, pier_h + H / 2), (L, W, H), siding))
        parts.append(gable(-L, 0, y0, y1, pier_h + H, W * 0.45, roof, end_rgb=siding))
        parts += _windows(x0, x1, y1, pier_h + 1.6, max(2, int(L / 4)), 1)
        parts += _windows(x0, x1, y0, pier_h + 1.6, max(2, int(L / 4)), -1)
        parts.append(box((0.03, 0, pier_h + 1.1), (0.06, 0.9, 2.1), (0.30, 0.22, 0.16)))
        parts += porch(0.0, y0, y1, 2.0, pier_h, roof, r)
        door = (3.0, 0.0)
        fp = (x0, y0, 2.0, y1)
    elif kind == "dogtrot":
        Wc, D, H = r.uniform(5, 6.5), r.uniform(5, 6), 2.8
        hall = r.uniform(2.8, 3.6)
        for yc in (-(hall / 2 + Wc / 2), hall / 2 + Wc / 2):
            parts.append(box((-D / 2, yc, pier_h + H / 2), (D, Wc, H), (0.55, 0.42, 0.30)))  # log pens
        y0, y1 = -(hall / 2 + Wc), hall / 2 + Wc
        parts += _piers(-D, 0, y0, y1, pier_h, r)
        parts.append(box((-D / 2, 0, pier_h - 0.05), (D, hall, 0.12), (0.5, 0.45, 0.38)))  # breezeway floor
        # roof along y (rotate gable)
        g = gable(y0, y1, 0, D, pier_h + H, D * 0.5, roof, end_rgb=(0.55, 0.42, 0.30))
        Rz = np.array([[0, -1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], float)
        g = g.transformed(Rz)  # ridge now runs along y over x∈[-D, 0]
        parts.append(g)
        parts += porch(0.0, y0, y1, 2.2, pier_h, roof, r)
        door = (3.0, 0.0)
        fp = (-D, y0, 2.2, y1)
    elif kind == "barn":
        L, W, H = r.uniform(12, 18), r.uniform(9, 12), 4.5
        col = (0.55, 0.16, 0.12) if r.uniform() < 0.5 else (0.50, 0.47, 0.42)  # red or weathered
        parts.append(box((-L / 2, 0, H / 2), (L, W, H), col))
        parts.append(gable(-L, 0, -W / 2, W / 2, H, W * 0.42, roof, end_rgb=col))
        parts.append(box((0.03, 0, 1.9), (0.06, 3.6, 3.8), (0.35, 0.25, 0.18)))
        door = (2.0, 0.0)
        fp = (-L, -W / 2, 0, W / 2)
    elif kind == "church":
        L, W, H = r.uniform(14, 18), r.uniform(8, 10), 5.0
        parts += _piers(-L, 0, -W / 2, W / 2, pier_h, r)
        parts.append(box((-L / 2, 0, pier_h + H / 2), (L, W, H), (0.95, 0.95, 0.93)))
        parts.append(gable(-L, 0, -W / 2, W / 2, pier_h + H, W * 0.55, roof, end_rgb=(0.95, 0.95, 0.93)))
        parts.append(box((-1.5, 0, pier_h + H + 2.5), (2.4, 2.4, 5.0), (0.95, 0.95, 0.93)))  # steeple base
        sp = gable(-2.7, -0.3, -1.2, 1.2, pier_h + H + 5.0, 3.5, roof, overhang=0)
        parts.append(sp)
        parts += _windows(-L, 0, W / 2, pier_h + 2.5, 4, 1)
        parts += _windows(-L, 0, -W / 2, pier_h + 2.5, 4, -1)
        parts += porch(0.0, -2, 2, 2.0, pier_h, roof, r)
        door = (3.0, 0.0)
        fp = (-L, -W / 2, 2.0, W / 2)
    else:  # farmhouse
        L, W, H = r.uniform(10, 13), r.uniform(8, 10), 3.0
        parts += _piers(-L, 0, -W / 2, W / 2, pier_h, r)
        parts.append(box((-L / 2, 0, pier_h + H / 2), (L, W, H), siding))
        parts.append(gable(-L, 0, -W / 2, W / 2, pier_h + H, W * 0.4, roof, end_rgb=siding))
        top = pier_h + H + W * 0.4 + 0.8  # exterior end chimney, brick, ground to above ridge
        parts.append(box((-L - 0.35, W / 5, top / 2), (0.7, 1.3, top), (0.55, 0.28, 0.20)))
        parts += _windows(-L, 0, W / 2, pier_h + 1.5, 3, 1)
        parts += _windows(-L, 0, -W / 2, pier_h + 1.5, 3, -1)
        parts += porch(0.0, -W / 2, W / 2, 2.6, pier_h, roof, r)
        door = (3.0, 0.0)
        fp = (-L, -W / 2, 2.6, W / 2)
    return Mesh.merge(parts), dict(door=door, footprint=fp, kind=kind)


def mailbox(r):
    return Mesh.merge([box((0, 0, 0.55), (0.1, 0.1, 1.1), (0.45, 0.35, 0.25)),
                       box((0, 0, 1.15), (0.5, 0.22, 0.24), (0.15, 0.15, 0.16) if r.uniform() < 0.6 else (0.85, 0.85, 0.85)),
                       box((0.05, 0.13, 1.2), (0.03, 0.02, 0.18), (0.8, 0.1, 0.1))])


def clothesline(r, length=8.0):
    parts = []
    for x in (0.0, length):
        parts += [box((x, 0, 1.0), (0.08, 0.08, 2.0), (0.5, 0.5, 0.5)), box((x, 0, 1.95), (0.06, 1.2, 0.06), (0.5, 0.5, 0.5))]
    for y in (-0.5, 0, 0.5):
        parts.append(box((length / 2, y, 1.94), (length, 0.01, 0.01), (0.85, 0.85, 0.85)))
    for k in range(int(r.integers(2, 6))):  # laundry
        x = r.uniform(0.8, length - 0.8)
        y = r.choice([-0.5, 0, 0.5])
        c = SIDING[int(r.integers(len(SIDING)))]
        parts.append(box((x, y, 1.6), (r.uniform(0.4, 0.9), 0.02, r.uniform(0.4, 0.8)), c))
    return Mesh.merge(parts)


def fence(points, r, post_every=2.5, height=1.1):
    parts = []
    for a, b in zip(points[:-1], points[1:]):
        a, b = np.asarray(a, float), np.asarray(b, float)
        L = np.linalg.norm(b - a)
        ang = np.arctan2(b[1] - a[1], b[0] - a[0])
        for t in np.linspace(0, 1, max(2, int(L / post_every) + 1)):
            p = a + (b - a) * t
            parts.append(box((p[0], p[1], p[2] + height / 2), (0.1, 0.1, height), (0.42, 0.36, 0.28)))
        for zz in (0.45, 0.9):
            m = (a + b) / 2
            parts.append(box((m[0], m[1], m[2] + zz), (L, 0.02, 0.02), (0.55, 0.55, 0.55), rot_z=ang))
    return Mesh.merge(parts)

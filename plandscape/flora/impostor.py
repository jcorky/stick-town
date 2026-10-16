"""Far-LOD tree impostors: the tree baked from two sides onto two crossed, alpha-tested cards.

The classic cross-billboard (SpeedTree-style "billboard LOD"; ez-tree only thins rings and segments, see
catalog/notes/ez-tree.md): the full tree is rendered orthographically, unlit (albedo), without fog and with the viewer's colour
arithmetic (render(viewer_colour=True)), from azimuth 0° (looking +y)
and 90° (looking +x) into the two halves of one RGBA atlas. Two vertical quads through the trunk axis, in the
x-z and y-z planes, carry those views. With R the crown's horizontal radius and H the height, the renderer
maps a point to atlas pixels by

    span = max(2R / (0.95 w), H / (0.95 h)),   u_px = w/2 + s / span,   v_px = h/2 − (z − H/2) / span

(s = x or y along the card), so the quad corners (±R, 0) and (±R, H) get exactly those UVs and the baked
tree lands where the mesh tree stands. Transparent texels take the colour of the nearest opaque one (edge
padding), so mipmaps don't fringe the cards with sky. 4 triangles replace ~5–30k. See TECHNIQUES §23.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from ..mesh import Mesh
from ..render import render

HALF = (96, 160)        # px per view (w, h); the atlas is 2w × h
SUN = (0.35, -0.45, 0.8)


def _extent(tm):
    P = np.concatenate([m.positions for m in (tm.bark, tm.foliage) if m is not None and len(m.positions)])
    R = float(np.max(np.hypot(P[:, 0], P[:, 1]))) * 1.02
    H = float(P[:, 2].max()) * 1.01
    return R, H


def _span(R, H, w, h):
    return max(2 * R / (0.95 * w), H / (0.95 * h))


def bake(tm, half=HALF):
    """RGBA atlas (h, 2w, 4) uint8: the tree seen along +y (left half) and along +x (right half)."""
    R, H = _extent(tm)
    w, h = half
    fit = ((-R, -R, 0.0), (R, R, H))
    meshes = [m for m in (tm.bark, tm.foliage) if m is not None]
    views = [render(meshes, None, size=(w, h), azimuth=az, elevation=0.0, fit=fit, sun=SUN, max_tris=2_000_000,
                    keep_first=len(meshes), alpha=True, shading=False, viewer_colour=True) for az in (0.0, 90.0)]
    rgba = np.concatenate(views, 1)
    a = rgba[..., 3] > 127
    if a.any() and not a.all():  # edge padding: transparent texels copy the nearest opaque colour
        _, (ii, jj) = ndimage.distance_transform_edt(~a, return_indices=True)
        rgba[..., :3] = rgba[ii, jj, :3]
    rgba[..., 3] = np.where(a, 255, 0)
    return rgba


def mesh(tm, texture_key, mean_rgb, half=HALF):
    """Two crossed quads with atlas UVs; vertex colour = the atlas mean, so COLOR_0 = c / μ = 1 and the
    viewer shows the atlas as baked."""
    R, H = _extent(tm)
    w, h = half
    sp = _span(R, H, w, h)
    u = lambda s: (w / 2 + s / sp) / w  # noqa: E731  (0..1 inside one half)
    v = lambda z: (h / 2 - (z - H / 2) / sp) / h  # noqa: E731
    P, UV = [], []
    for k, (ax, ay) in enumerate(((1.0, 0.0), (0.0, 1.0))):  # card 0 in x-z (seen along +y), card 1 in y-z
        # azimuth 90° looks along +x with screen-right = (0, −1, 0): s runs along −y on card 1
        sgn = 1.0 if k == 0 else -1.0
        for s, z in ((-R, 0.0), (R, 0.0), (R, H), (-R, H)):
            P.append((ax * s * sgn, ay * s * sgn, z))
            UV.append(((u(s) + k) / 2, v(z)))
    P = np.array(P, np.float32)
    idx = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]], np.uint32)
    col = np.tile(np.asarray(mean_rgb, np.float32), (8, 1))
    m = Mesh(P, col, idx, np.array(UV, np.float32), texture_key)
    # the atlas is unlit albedo; rounded normals let the viewer light the cards like a crown (after §18):
    # n = normalize(0.6 · side · card axis + up_z), up_z = 0.5 at the top corners, 0.1 at the bottom
    n = []
    for k, (ax, ay) in enumerate(((1.0, 0.0), (0.0, 1.0))):
        sgn = 1.0 if k == 0 else -1.0
        for s_, z in ((-1, 0), (1, 0), (1, 1), (-1, 1)):
            n.append((0.6 * s_ * sgn * ax, 0.6 * s_ * sgn * ay, 0.5 if z else 0.1))
    n = np.array(n, np.float32)
    m.nrm = n / np.linalg.norm(n, axis=1, keepdims=True)
    return m

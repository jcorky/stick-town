"""Sculpted bodies: smooth-blended anatomical forms meshed into one continuous skin (TECHNIQUES §36).

A body part is a set of primitives — ellipsoids and round cones (tapered capsules) — each a signed distance
function (SDF), combined by a polynomial smooth minimum so muscles, necks and haunches flow into each other:

    smin(a, b; k) = min(a, b) − h² k / 4,    h = max(k − |a − b|, 0) / k        (Quílez)
    colour = mix(c_b, c_a, ½ + ½ (b − a)/k)  clipped to [0, 1]  (the same blend, so colour seams vanish)

Ellipsoid (bound-exact approximation):   d = k₀(k₀ − 1)/k₁,  k₀ = |p/r|,  k₁ = |p/r²|
Round cone a→b, radii r₁→r₂ (exact):     Quílez's sdRoundCone

Meshing is naive surface nets: on a grid of spacing h, every cell whose corners change sign gets one vertex
(the mean of its edge crossings), and every grid edge that changes sign makes a quad of the four cells around
it. Each vertex is then projected onto the true surface by Newton steps p ← p − d(p) ∇d/|∇d|², and normals are
the normalised SDF gradient: a smooth, watertight, evenly sampled skin with no faceting. Pure numpy.
"""

from __future__ import annotations

import numpy as np

from ..mesh import Mesh

DETAIL = 0.5   # scales every triangle budget (mesh(target=…)): 0.5 keeps a deer near 6k triangles, scenes < 15 MB


def rot(yaw=0.0, pitch=0.0, roll=0.0):
    """Rotation matrix: roll about x, then pitch about y (nose down positive), then yaw about z."""
    cr, sr, cp, sp, cy, sy = np.cos(roll), np.sin(roll), np.cos(pitch), np.sin(pitch), np.cos(yaw), np.sin(yaw)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


class Sculpt:
    def __init__(self):
        self.prims = []
        self.disp = []

    def displace(self, fn):
        """Add fn(P) to the field after blending: small reliefs (bands, scutes, feather rows). Normals come from
        the field's gradient, so relief finer than the grid still shades, like a bump map."""
        self.disp.append(fn)
        return self

    # ── primitives ──
    def ellipsoid(self, c, r, rgb, k=0.02, R=None, sub=False):
        """Ellipsoid centred c with semi-axes r (in its own frame, rotated by R); k = blend radius (m).
        sub=True carves it out instead (a smooth subtraction)."""
        self.prims.append(("e", np.asarray(c, float), np.asarray(r, float), None if R is None else np.asarray(R),
                           np.asarray(rgb, float), k, sub))
        return self

    def cone(self, a, b, ra, rb, rgb, k=0.02, sub=False):
        """Round cone (tapered capsule) from a (radius ra) to b (radius rb)."""
        self.prims.append(("c", np.asarray(a, float), np.asarray(b, float), (float(ra), float(rb)),
                           np.asarray(rgb, float), k, sub))
        return self

    def chain(self, pts, radii, rgb, k=0.02):
        """Round cones along a polyline: necks, tails, limbs."""
        for i in range(len(pts) - 1):
            self.cone(pts[i], pts[i + 1], radii[i], radii[i + 1], rgb, k)
        return self

    def spline(self, pts, radii, rgb, k=0.02, per=3):
        """A chain along the Catmull–Rom spline through `pts`: a smooth curve (an S-neck, a plume) instead of
        a polyline's kinks."""
        C, rad = catmull(pts, radii, per)
        return self.chain(C, rad, rgb, k)

    # ── evaluation ──
    @staticmethod
    def _d_ellipsoid(P, c, r, R):
        q = P - c
        if R is not None:
            q = q @ R          # into the ellipsoid's frame (R maps local → world)
        k0 = np.linalg.norm(q / r, axis=-1)
        k1 = np.linalg.norm(q / (r * r), axis=-1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)

    @staticmethod
    def _d_cone(P, a, b, r1, r2):
        ba = b - a
        l2 = float(ba @ ba)
        rr = r1 - r2
        a2 = l2 - rr * rr
        il2 = 1.0 / max(l2, 1e-12)
        pa = P - a
        y = pa @ ba
        z = y - l2
        w = pa * l2 - y[:, None] * ba
        x2 = (w * w).sum(-1)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        d3 = (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1
        d1 = np.sqrt(x2 + z2) * il2 - r2
        d2 = np.sqrt(x2 + y2) * il2 - r1
        out = np.where(np.sign(z) * a2 * z2 > k, d1, np.where(np.sign(y) * a2 * y2 < k, d2, d3))
        return out

    def field(self, P, colour=False):
        P = np.asarray(P, float)
        d = np.full(len(P), 1e9)
        col = np.zeros((len(P), 3)) if colour else None
        first = True
        for p in self.prims:
            if p[0] == "e":
                di = self._d_ellipsoid(P, p[1], p[2], p[3])
            else:
                di = self._d_cone(P, p[1], p[2], *p[3])
            rgb, k, sub = p[4], max(p[5], 1e-6), p[6]
            if first and not sub:
                d, first = di, False
                if colour:
                    col[:] = rgb
                continue
            if sub:  # smooth subtraction: max(d, −di) softened
                h = np.clip(0.5 - 0.5 * (d + di) / k, 0, 1)
                d = d * (1 - h) + (-di) * h + k * h * (1 - h)
                if colour:
                    col = col * (1 - h[:, None]) + rgb * 0.6 * h[:, None]   # carved hollows read darker
                continue
            h = np.clip(0.5 + 0.5 * (di - d) / k, 0, 1)    # weight of the existing field
            dn = di * (1 - h) + d * h - k * h * (1 - h)
            if colour:
                col = rgb * (1 - h[:, None]) + col * h[:, None]
            d = dn
        for fn in self.disp:
            d = d + fn(P)
        return (d, col) if colour else d

    def grad(self, P, eps):
        e = np.eye(3) * eps
        g = np.stack([(self.field(P + e[i]) - self.field(P - e[i])) / (2 * eps) for i in range(3)], -1)
        return g

    def bounds(self):
        lo, hi = np.full(3, 1e9), np.full(3, -1e9)
        for p in self.prims:
            if p[6]:
                continue
            if p[0] == "e":
                r = np.max(p[2])
                lo, hi = np.minimum(lo, p[1] - r), np.maximum(hi, p[1] + r)
            else:
                r = max(p[3])
                lo = np.minimum(lo, np.minimum(p[1], p[2]) - r)
                hi = np.maximum(hi, np.maximum(p[1], p[2]) + r)
        return lo, hi

    # ── meshing ──
    def mesh(self, h=None, cells=56, colour_fn=None, newton=3, target=None):
        """Surface-nets mesh with grid spacing h (default: the longest extent / cells). With `target`, the
        spacing is chosen for about that many triangles: a coarse pass measures the area A, then
        h = √(2A / target) (surface nets make two triangles per h² of surface)."""
        lo, hi = self.bounds()
        if target is not None:
            target = max(24, target * DETAIL)
            probe = self.mesh(cells=20, newton=1)
            P = probe.positions.astype(float)
            I = probe.indices
            area = 0.5 * np.linalg.norm(np.cross(P[I[:, 1]] - P[I[:, 0]], P[I[:, 2]] - P[I[:, 0]]), axis=1).sum()
            h = float(np.sqrt(2 * area / target))
        if h is None:
            h = float(np.max(hi - lo)) / cells
        lo, hi = lo - 2 * h, hi + 2 * h
        n = np.ceil((hi - lo) / h).astype(int) + 1
        xs = [lo[i] + np.arange(n[i]) * h for i in range(3)]
        G = np.stack(np.meshgrid(*xs, indexing="ij"), -1)
        D = self.field(G.reshape(-1, 3)).reshape(n)
        inside = D < 0
        # cells with a sign change
        corners = [(i, j, k) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
        nc = n - 1
        cs = np.stack([inside[i:i + nc[0], j:j + nc[1], k:k + nc[2]] for i, j, k in corners], -1)
        active = cs.any(-1) & ~cs.all(-1)
        ci = np.argwhere(active)
        if not len(ci):
            return Mesh.empty()
        vid = -np.ones(nc, np.int64)
        vid[tuple(ci.T)] = np.arange(len(ci))
        # vertex = mean of the crossings on the cell's 12 edges
        edges = [((0, 0, 0), (1, 0, 0)), ((0, 1, 0), (1, 1, 0)), ((0, 0, 1), (1, 0, 1)), ((0, 1, 1), (1, 1, 1)),
                 ((0, 0, 0), (0, 1, 0)), ((1, 0, 0), (1, 1, 0)), ((0, 0, 1), (0, 1, 1)), ((1, 0, 1), (1, 1, 1)),
                 ((0, 0, 0), (0, 0, 1)), ((1, 0, 0), (1, 0, 1)), ((0, 1, 0), (0, 1, 1)), ((1, 1, 0), (1, 1, 1))]
        acc = np.zeros((len(ci), 3))
        cnt = np.zeros(len(ci))
        for a, b in edges:
            ia, ib = ci + a, ci + b
            da, db = D[tuple(ia.T)], D[tuple(ib.T)]
            m = (da < 0) != (db < 0)
            t = np.where(m, da / np.where(m, da - db, 1.0), 0.0)
            pa = lo + ia * h
            pb = lo + ib * h
            acc += np.where(m[:, None], pa + t[:, None] * (pb - pa), 0.0)
            cnt += m
        V = acc / np.maximum(cnt, 1)[:, None]
        # quads: every grid edge with a sign change joins the 4 cells around it
        F = []
        for ax in range(3):
            u, v = [a for a in range(3) if a != ax]
            sl0 = [slice(None)] * 3
            sl1 = [slice(None)] * 3
            sl0[ax] = slice(0, n[ax] - 1)
            sl1[ax] = slice(1, n[ax])
            ch = inside[tuple(sl0)] != inside[tuple(sl1)]
            e = np.argwhere(ch)
            e = e[(e[:, u] >= 1) & (e[:, v] >= 1) & (e[:, u] < n[u] - 1) & (e[:, v] < n[v] - 1)]
            if not len(e):
                continue
            flip = inside[tuple(e.T)]
            def cell(du, dv):
                c = e.copy()
                c[:, u] -= du
                c[:, v] -= dv
                return vid[tuple(c.T)]
            q = np.stack([cell(1, 1), cell(0, 1), cell(0, 0), cell(1, 0)], 1)
            q = np.where(flip[:, None], q, q[:, ::-1])
            if ax == 1:  # keep a consistent winding across the three axes
                q = q[:, ::-1]
            F.append(q)
        Q = np.concatenate(F)
        Q = Q[(Q >= 0).all(1)]
        # split each quad along its shorter diagonal
        d02 = np.linalg.norm(V[Q[:, 0]] - V[Q[:, 2]], axis=1)
        d13 = np.linalg.norm(V[Q[:, 1]] - V[Q[:, 3]], axis=1)
        s = d02 <= d13
        T = np.concatenate([np.where(s[:, None], Q[:, [0, 1, 2]], Q[:, [0, 1, 3]]),
                            np.where(s[:, None], Q[:, [0, 2, 3]], Q[:, [1, 2, 3]])])
        # project onto the true surface, then normals from the field's gradient
        for _ in range(newton):
            d = self.field(V)
            g = self.grad(V, h * 0.25)
            V = V - (d / np.maximum((g * g).sum(1), 1e-9))[:, None] * g
        N = self.grad(V, h * 0.25)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        _, C = self.field(V, colour=True)
        if colour_fn is not None:
            C = colour_fn(V, N, C)
        # orient: outward normals and triangle winding must agree
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        if (fn * N[T].mean(1)).sum() < 0:
            T = T[:, ::-1]
        T = _drop_specks(T, len(V))
        m = Mesh(V.astype(np.float32), np.clip(C, 0, 1).astype(np.float32), T.astype(np.uint32))
        m.nrm = N.astype(np.float32)
        return m


def _drop_specks(T, n):
    """Surface nets can leave a few-vertex island where a tip thins below the grid: drop components under 16
    vertices that are also under a tenth of its largest piece (vertices stay, unreferenced)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    if not len(T):
        return T
    I = np.r_[T[:, 0], T[:, 1], T[:, 2]]
    J = np.r_[T[:, 1], T[:, 2], T[:, 0]]
    _, lab = connected_components(coo_matrix((np.ones(len(I)), (I, J)), shape=(n, n)), directed=False)
    used = np.unique(T)
    size = np.bincount(lab[used], minlength=lab.max() + 1)
    small = (size < 16) & (size < 0.1 * size.max())
    return T[~small[lab[T[:, 0]]]] if small.any() else T


def merge(meshes):
    """Mesh.merge that keeps authored normals (sculptures carry SDF-gradient normals)."""
    meshes = [m for m in meshes if m is not None and m.n_tris]
    out = Mesh.merge(meshes)
    if all(m.nrm is not None for m in meshes):
        out.nrm = np.concatenate([m.nrm for m in meshes]).astype(np.float32)
    keys = {k for m in meshes for k in (m.attrs or {})}
    if keys:   # custom attributes (coat.py's _COAT): parts without one get zero rows ("not yet set")
        out.attrs = {k: np.concatenate([(m.attrs or {}).get(k, np.zeros((len(m.positions), 4), np.uint8))
                                        for m in meshes]) for k in keys}
    return out


def catmull(pts, radii, per=4):
    """Points and radii sampled `per` times per span along the Catmull–Rom spline through `pts` (ends mirrored);
    radius linear in the spline parameter."""
    P = np.asarray(pts, float)
    R = np.asarray(radii, float)
    Q = np.r_[[2 * P[0] - P[1]], P, [2 * P[-1] - P[-2]]]
    t = np.linspace(0, 1, per, endpoint=False)
    C, rad = [], []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = Q[i:i + 4]
        T = t[:, None]
        C.append(0.5 * (2 * p1 + (p2 - p0) * T + (2 * p0 - 5 * p1 + 4 * p2 - p3) * T ** 2 +
                        (3 * p1 - p0 - 3 * p2 + p3) * T ** 3))
        rad.append(R[i] + (R[i + 1] - R[i]) * t)
    return np.concatenate(C + [P[-1:]]), np.r_[np.concatenate(rad), R[-1]]


def tube(pts, radii, rgb, sides=8, per=4, tip=0.5, colour_fn=None):
    """A swept tube for parts thinner than any grid can afford (antler tines, quills): a Catmull–Rom spline
    through `pts`, rings of `sides` vertices carried along it by parallel transport (no twist), radius linear
    in arc parameter. The far end closes in a cone `tip`·r long (0 = flat, larger = rounder or sharper); the base
    in a flat fan. Normals are the ring's radial directions, tilted by the taper dr/ds."""
    C, rad = catmull(pts, radii, per)
    tang = np.gradient(C, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    a = np.cross(tang[0], [0, 0, 1.0] if abs(tang[0][2]) < 0.9 else [1.0, 0, 0])
    a /= np.linalg.norm(a)
    U = [a]
    for k in range(1, len(C)):   # parallel transport: remove the new tangent's component, renormalise
        u = U[-1] - tang[k] * (U[-1] @ tang[k])
        U.append(u / np.linalg.norm(u))
    U = np.array(U)
    V = np.cross(tang, U)
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ds = np.linalg.norm(np.diff(C, axis=0), axis=1)
    slope = np.r_[(rad[1] - rad[0]) / ds[0], np.diff(rad) / ds]           # dr/ds
    radial = np.cos(ang)[None, :, None] * U[:, None] + np.sin(ang)[None, :, None] * V[:, None]
    pos = C[:, None] + rad[:, None, None] * radial
    nrm = radial - slope[:, None, None] * tang[:, None]
    n = len(C)
    pos = pos.reshape(-1, 3)
    nrm = nrm.reshape(-1, 3)
    end = C[-1] + tang[-1] * rad[-1] * tip
    pos = np.r_[pos, [C[0], end]]
    nrm = np.r_[nrm, [-tang[0], tang[-1]]]
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    idx = []
    for k in range(n - 1):
        for j in range(sides):
            a0, a1 = k * sides + j, k * sides + (j + 1) % sides
            idx += [(a0, a1, a1 + sides), (a0, a1 + sides, a0 + sides)]
    b, e = n * sides, n * sides + 1
    for j in range(sides):
        j1 = (j + 1) % sides
        idx += [(b, j1, j), ((n - 1) * sides + j, (n - 1) * sides + j1, e)]
    col = np.tile(np.asarray(rgb, np.float32), (len(pos), 1))
    if colour_fn is not None:
        col = np.clip(colour_fn(pos, nrm, col), 0, 1)
    m = Mesh(pos.astype(np.float32), col.astype(np.float32), np.asarray(idx, np.uint32))
    m.nrm = nrm.astype(np.float32)
    return m


def leaf(length, width, thick, cup=0.35, shape="oval", nu=10, nv=5, rgb=(1, 1, 1), colour_fn=None):
    """A cupped ear (or any thin blade) as an explicit closed shell, for parts thinner than a grid can resolve.
    Local frame: base at the origin, length along +z, width along y, the hollow facing +x. Half-width
    w(u) = W (1 − u)^0.35 (0.6 + 0.4 sin πu) for an oval ear, W (1 − u)^0.9 (1 + 0.25 sin πu) for a pointed one;
    the front sheet is hollowed by x = −cup·W (1 − v²) sin πu and the back sheet lies thick·(1 − 0.7u)·√(1 − v²)
    behind it, so the two meet along the rim."""
    W = width / 2
    u = np.linspace(0, 1, nu + 1)[:, None]
    v = np.linspace(-1, 1, 2 * nv + 1)[None, :]
    if shape == "pointed":
        w = W * (1 - u) ** 0.9 * (1 + 0.25 * np.sin(np.pi * u))
    else:
        w = W * (1 - u) ** 0.35 * (0.6 + 0.4 * np.sin(np.pi * u))
    xf = -cup * W * (1 - v ** 2) * np.sin(np.pi * np.minimum(u, 0.95))
    xb = xf - thick * (1 - 0.7 * u) * np.sqrt(np.clip(1 - v ** 2, 0, 1))
    y = v * w
    z = u * length + 0 * v
    F = np.stack([xf, y, z], -1).reshape(-1, 3)
    B = np.stack([xb, y, z], -1).reshape(-1, 3)
    n, m = nu + 1, 2 * nv + 1
    inner = [(i, j) for i in range(nu) for j in range(1, m - 1)]   # the back sheet shares rim and tip with the front
    bidx = {ij: n * m + k for k, ij in enumerate(inner)}
    P = np.r_[F, B[[i * m + j for i, j in inner]]]

    def fi(i, j):
        return i * m + j

    def bi(i, j):
        return bidx.get((i, j), fi(i, j))
    idx = []
    for i in range(nu):
        for j in range(m - 1):
            idx += [(fi(i, j), fi(i + 1, j), fi(i, j + 1)), (fi(i, j + 1), fi(i + 1, j), fi(i + 1, j + 1))]   # front
            idx += [(bi(i, j), bi(i, j + 1), bi(i + 1, j)), (bi(i, j + 1), bi(i + 1, j + 1), bi(i + 1, j))]   # back
    for j in range(m - 1):   # close the base between the sheets (it sits inside the head)
        idx += [(fi(0, j), fi(0, j + 1), bi(0, j)), (fi(0, j + 1), bi(0, j + 1), bi(0, j))]
    idx = np.asarray(idx, np.uint32)[:, [0, 2, 1]]
    idx = idx[(idx[:, 0] != idx[:, 1]) & (idx[:, 1] != idx[:, 2]) & (idx[:, 0] != idx[:, 2])]   # shared rim corners
    m_ = Mesh(P.astype(np.float32), np.tile(np.asarray(rgb, np.float32), (len(P), 1)), idx)
    m_.nrm = m_.geometric_normals()
    if colour_fn is not None:
        m_.colors = np.clip(colour_fn(m_.positions, m_.nrm, m_.colors), 0, 1).astype(np.float32)
    return m_


def place(m, R, t):
    """m rotated by R then moved to t, normals carried along."""
    out = Mesh((m.positions @ np.asarray(R, np.float32).T + np.asarray(t, np.float32)).astype(np.float32), m.colors,
               m.indices)
    out.nrm = None if m.nrm is None else (m.nrm @ np.asarray(R, np.float32).T).astype(np.float32)
    out.attrs = m.attrs
    return out

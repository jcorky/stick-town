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
        m = Mesh(V.astype(np.float32), np.clip(C, 0, 1).astype(np.float32), T.astype(np.uint32))
        m.nrm = N.astype(np.float32)
        return m


def merge(meshes):
    """Mesh.merge that keeps authored normals (sculptures carry SDF-gradient normals)."""
    meshes = [m for m in meshes if m is not None and m.n_tris]
    out = Mesh.merge(meshes)
    if all(m.nrm is not None for m in meshes):
        out.nrm = np.concatenate([m.nrm for m in meshes]).astype(np.float32)
    return out

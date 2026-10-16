"""Procedural trees via space colonisation (Runions, Lane & Prusinkiewicz 2007).

Pipeline per tree:
  1. sample attraction points inside a species crown envelope
  2. grow a trunk/leader, then colonise the points to grow branches
  3. assign radii with the pipe model (r_parent^n = Σ r_child^n)
  4. sweep tubes with root flare/buttressing, bark colour and north-side moss
  5. place foliage (broadleaf blades, pine needle tufts, cypress sprays, palm fronds),
     flowers, Spanish moss and cypress knees

`detail` sets the leaf budget. Leaf cards are scaled up to keep crown cover
constant when the budget is below a real tree's leaf count; at detail="cm"
leaves approach true size (each blade a few cm), which is the 1 cm target.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .. import textures
from ..mesh import Mesh, MeshBuilder
from ..rng import rng as make_rng
from .species import SPECIES, Species

LEAF_BUDGET = {"low": 2000, "med": 9000, "high": 40000, "cm": 250000}
FOLD_COVER = 0.92  # a folded card's projected area relative to flat (cos of the mean fold angle)
TWIG_CULL = {"low": 0.03, "med": 0.015, "high": 0.006, "cm": 0.0}  # twigs thinner than this hide in foliage
R_TIP = 0.012  # m, radius of the branchlets the foliage hangs on, the same for every species (see grow_skeleton)


@dataclass
class Skeleton:
    pos: np.ndarray
    parent: np.ndarray
    radius: np.ndarray
    trunk: np.ndarray


@dataclass
class TreeModel:
    species: Species
    seed: tuple
    height: float
    skeleton: Skeleton
    bark: Mesh
    foliage: Mesh

    @property
    def n_tris(self):
        return self.bark.n_tris + self.foliage.n_tris


def _norm(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-9)


def _perp_frame(t):
    t = _norm(np.atleast_2d(t))
    ref = np.where(np.abs(t[:, 2:3]) < 0.9, [[0, 0, 1.0]], [[1.0, 0, 0]])
    u = _norm(np.cross(t, ref))
    w = np.cross(t, u)
    return u, w


# ── crown envelopes ─────────────────────────────────────────────────────────

def _sample_crown(sp: Species, H: float, n: int, r) -> np.ndarray:
    R = sp.crown_width * H / 2.0
    zb = sp.crown_base * H
    hc = H - zb
    out = []
    if sp.crown == "pine_open":
        n_cl = max(14, n // 18)
        cv = r.uniform(0.05, 1.0, n_cl) ** 0.8
        crad = np.sqrt(r.uniform(0, 1, n_cl)) * (1.0 - 0.75 * cv ** 2)
        ca = r.uniform(0, 2 * np.pi, n_cl)
        centres = np.c_[crad * R * np.cos(ca), crad * R * np.sin(ca), zb + cv * hc * 0.95]
        idx = r.integers(0, n_cl, n)
        pts = centres[idx] + r.normal(0, [R * 0.22, R * 0.22, hc * 0.05], (n, 3))
        return pts
    while sum(len(o) for o in out) < n:
        m = n * 3
        u = r.uniform(-1, 1, (m, 2))
        v = r.uniform(0, 1, m)
        rr = np.hypot(u[:, 0], u[:, 1])
        if sp.crown == "spreading":
            ok = (rr ** 2 + ((v - 0.4) / 0.6) ** 2 <= 1) & ((rr > 0.45) | (r.uniform(0, 1, m) < 0.25))
        elif sp.crown == "round":
            ok = (rr ** 2 + ((v - 0.5) / 0.5) ** 2 <= 1) & ((rr > 0.3) | (r.uniform(0, 1, m) < 0.4))
        elif sp.crown == "conical":
            ok = rr <= (1.0 - v) * 1.05 + 0.04
        elif sp.crown == "columnar":
            ok = rr ** 2 + ((v - 0.55) / 0.55) ** 2 <= 1
        elif sp.crown == "layered":
            tier = np.abs(((v * 3.0) % 1.0) - 0.5) < 0.18
            ok = (rr <= 1.0 - 0.35 * v) & tier
        else:
            ok = rr <= 1
        pts = np.c_[u[ok] * R, zb + v[ok] * hc]
        out.append(pts)
    return np.concatenate(out)[:n]


# ── skeleton growth ─────────────────────────────────────────────────────────

def grow_skeleton(sp: Species, H: float, r, max_iter: int = 220) -> Skeleton:
    D = float(np.clip(H / 45.0, 0.12, 0.55))
    di, dk = D * 14.0, D * 2.0
    lean = r.normal(0, np.radians(3.5 if sp.crown != "spreading" else 7.0), 2)
    trunk_top = max(sp.crown_base + 0.08 * (1 - sp.crown_base), sp.leader) * H
    pos = [np.zeros(3)]
    parent = [-1]
    trunk = [True]
    d = _norm(np.array([np.sin(lean[0]), np.sin(lean[1]), 1.0]))
    for _ in range(int(trunk_top / D * 1.6) + 4):
        if pos[-1][2] >= trunk_top:
            break
        wob = 0.012 if sp.leader > 0.8 else 0.03  # excurrent conifers/poplars run straight
        d = _norm(d + r.normal(0, wob, 3) + [0, 0, sp.tropism * 0.3])
        if d[2] < 0.75:  # trunks never wander sideways or downward
            d = _norm(d * [1, 1, 0] * 0.6 + [0, 0, 0.8])
        pos.append(pos[-1] + d * D)
        parent.append(len(pos) - 2)
        trunk.append(True)
    pts = _sample_crown(sp, H, sp.attract, r)
    nodes = np.array(pos)
    up = np.array([0, 0, 1.0]) * sp.tropism
    for _ in range(max_iter):
        if len(pts) == 0:
            break
        tree = cKDTree(nodes)
        dist, idx = tree.query(pts, distance_upper_bound=di)
        ok = np.isfinite(dist)
        if not ok.any():
            break
        dirs = _norm(pts[ok] - nodes[idx[ok]])
        acc = np.zeros_like(nodes)
        cnt = np.zeros(len(nodes))
        np.add.at(acc, idx[ok], dirs)
        np.add.at(cnt, idx[ok], 1)
        rep = np.zeros_like(nodes)
        rep[idx[ok]] = dirs  # one representative point per node
        g = np.nonzero(cnt)[0]
        step = acc[g] / cnt[g, None]
        mag = np.linalg.norm(step, axis=1)
        # a node surrounded on all sides (e.g. a pine leader) would cancel to zero
        # and never branch — let it branch toward one of its points instead
        step = np.where(mag[:, None] < 0.25, rep[g], step)
        if len(g) == 0:
            break
        step = _norm(_norm(step) + up + r.normal(0, 0.08, step.shape))
        new = nodes[g] + step * D
        dd, _ = tree.query(new)
        keep = dd > 0.35 * D
        g, new = g[keep], new[keep]
        if len(g) == 0:
            break
        nodes = np.vstack([nodes, new])
        parent.extend(g.tolist())
        trunk.extend([False] * len(g))
        kill = cKDTree(new).query_ball_point(pts, dk, return_length=True)
        pts = pts[kill == 0]
    parent = np.array(parent)
    # pipe model radii
    n = sp.pipe_n
    acc = np.zeros(len(nodes))
    rad = np.zeros(len(nodes))
    for i in range(len(nodes) - 1, -1, -1):
        rad[i] = acc[i] ** (1.0 / n) if acc[i] > 0 else 1.0
        if parent[i] >= 0:
            acc[parent[i]] += rad[i] ** n
    dbh = r.uniform(*sp.dbh) * (0.6 + 0.4 * H / sp.height[1])
    rad *= (dbh / 2.0) / rad[0]
    # A skeleton has ~10² tips, a tree ~10⁴ twigs, so pure pipe radii leave tips at r0 · N^(−1/n) ≈ 8–12 % of the
    # trunk (4–6 cm on a sourced 1.2 m sweetgum). Remap linearly so the trunk keeps d.b.h./2 and the thinnest
    # tips become R_TIP, order preserved (TECHNIQUES §24):  r' = R_TIP + (r − r_min)(r0 − R_TIP)/(r0 − r_min)
    r0, rmin = rad[0], rad.min()
    if r0 > rmin > R_TIP:
        rad = R_TIP + (rad - rmin) * (r0 - R_TIP) / (r0 - rmin)
    # taper the leader so excurrent trunks narrow smoothly toward the top
    tz = nodes[:, 2] / H
    rad = np.where(np.array(trunk), np.maximum(rad, dbh / 2 * (1 - 0.85 * tz) ** 1.4), rad)
    rad = np.maximum(rad, 0.004)
    return Skeleton(nodes, parent, rad, np.array(trunk))


# ── bark ────────────────────────────────────────────────────────────────────

def _chains(sk: Skeleton, min_r: float):
    """Split the skeleton into chains: follow each node's thickest child; every other child starts
    a new chain at its parent. Returns lists of (node ids, parent node id or -1 for the root)."""
    pos, par, rad = sk.pos, sk.parent, sk.radius
    kids = [[] for _ in range(len(pos))]
    for i in range(1, len(pos)):
        kids[par[i]].append(i)
    out, todo = [], [(0, -1)]
    while todo:
        start, from_ = todo.pop()
        chain, n = [start], start
        while True:
            ks = [k for k in kids[n] if rad[k] >= min_r]
            if not ks:
                break
            main = max(ks, key=lambda k: rad[k])
            todo += [(k, n) for k in ks if k != main]
            chain.append(main)
            n = main
        out.append((chain, from_))
    return out


def _bark_mesh(sp: Species, sk: Skeleton, r, min_r: float = 0.0) -> Mesh:
    """Swept tubes along chains with shared rings (after ez-tree; TECHNIQUES §4).

    One ring per skeleton node, shared by the segments either side; frames carried by parallel
    transport u_k = normalize(u_{k-1} - (u_{k-1}·t_k) t_k), so seams don't twist at every node;
    side count and U wraps fixed per chain; terminal tips taper to 0.5 r; rings resampled to one per
    ds = clip(8 r, 0.3, 1.5) m of run unless the chain bends more than 12° (cos > 0.978)."""
    pos, rad = sk.pos, sk.radius
    phase = r.uniform(0, 2 * np.pi)
    nlobes = 5 + int(r.integers(0, 3))
    mb = MeshBuilder(textures.bark_key(sp.key))
    base = np.array(sp.bark_rgb)
    tile = textures.TILE_M["bark"]
    arc = np.zeros(len(pos))
    for i in range(1, len(pos)):
        arc[i] = arc[sk.parent[i]] + np.linalg.norm(pos[i] - pos[sk.parent[i]])
    has_kids = np.zeros(len(pos), bool)
    has_kids[sk.parent[sk.parent >= 0]] = True
    moss = np.array([0.30, 0.40, 0.18])
    for chain, from_ in _chains(sk, min_r):
        ids = np.array(chain)
        P = pos[ids].astype(np.float64)
        R = rad[ids].astype(np.float64).copy()
        T = sk.trunk[ids].copy()
        V = arc[ids].copy()
        if from_ < 0:  # root chain: start below grade so the flare sinks into the ground
            P = np.vstack([[0, 0, -0.5], P])
            R = np.r_[R[0], R]
            T = np.r_[True, T]
            V = np.r_[-0.5, V]
        else:  # side chain starts inside its parent, slightly fatter (branch collar)
            P = np.vstack([pos[from_], P])
            R = np.r_[R[0] * 1.08, R]
            T = np.r_[False, T]
            V = np.r_[arc[from_], V]
        if not has_kids[ids[-1]] and len(R) > 2:
            R[-1] = max(0.004, 0.5 * R[-1])  # twig tips taper (0.3 read as thorns in winter)
        if len(P) > 2:  # keep a ring every ds = clip(8 r, 0.3, 1.5) m of run, or where the chain bends > 12°
            seg = _norm(np.diff(P, axis=0))
            keep, run, last = [0], 0.0, seg[0]
            for k in range(1, len(P) - 1):
                run += np.linalg.norm(P[k] - P[k - 1])
                if run >= np.clip(8 * R[k], 0.3, 1.5) or np.dot(seg[k], last) < 0.978 or T[k] != T[k + 1]:
                    keep.append(k)
                    run, last = 0.0, seg[k]
            keep.append(len(P) - 1)
            P, R, T, V = P[keep], R[keep], T[keep], V[keep]
        m = len(P)
        if m < 2:
            continue
        tan = np.empty_like(P)
        tan[1:-1] = P[2:] - P[:-2]
        tan[0], tan[-1] = P[1] - P[0], P[-1] - P[-2]
        tan = _norm(tan)
        U = np.empty_like(P)
        U[0] = _perp_frame(tan[0])[0][0]
        for k in range(1, m):  # parallel transport
            u = U[k - 1] - np.dot(U[k - 1], tan[k]) * tan[k]
            nu = np.linalg.norm(u)
            U[k] = u / nu if nu > 1e-6 else _perp_frame(tan[k])[0][0]
        W = np.cross(tan, U)
        r0 = R[0]
        sides = 10 if r0 > 0.12 else 8 if r0 > 0.05 else 5 if r0 > 0.02 else 3
        nv = sides + 1
        ang = np.linspace(0, 2 * np.pi, nv)
        dirs = U[:, None, :] * np.cos(ang)[None, :, None] + W[:, None, :] * np.sin(ang)[None, :, None]
        z = P[:, 2:3]
        flare = 1 + T[:, None] * sp.flare * np.exp(-np.maximum(z, 0) / 0.45) * \
            (1 + 0.45 * np.cos(nlobes * ang[None, :] + phase))
        ring = P[:, None, :] + dirs * (R[:, None] * flare)[..., None]
        k = np.arange(sides)
        quad = np.stack([k, k + 1, k + nv, k + 1, k + 1 + nv, k + nv], -1).reshape(-1, 3)
        idx = (quad[None] + (np.arange(m - 1) * nv)[:, None, None]).reshape(-1, 3)
        reps = max(1.0, round(2 * np.pi * r0 / tile))  # constant per chain: no texel-density jumps
        uv = np.stack([np.broadcast_to(ang / (2 * np.pi) * reps, (m, nv)),
                       np.broadcast_to(V[:, None] / tile, (m, nv))], -1).reshape(-1, 2)
        zz = np.broadcast_to(z, (m, nv))
        furrow = 0.82 + 0.18 * np.sin(ang[None, :] * 9 + zz * 1.7) ** 2
        col = base[None, None, :] * (furrow * r.uniform(0.9, 1.1))[..., None]
        north = np.clip(dirs[..., 1], 0, 1) * np.exp(-np.maximum(zz, 0) / 2.5)
        col = col * (1 - 0.55 * north[..., None]) + moss * 0.55 * north[..., None]
        mb.add(ring.reshape(-1, 3), col.reshape(-1, 3), idx, uv)
    return mb.build()


# ── foliage ─────────────────────────────────────────────────────────────────

def _leaf_colour(sp, season, r, n):
    base = np.array(sp.leaf_rgb)
    cols = base * r.uniform(0.75, 1.2, (n, 1)) * (1 + r.normal(0, 0.04, (n, 3)))
    if season == "spring":
        cols = cols * 1.15 + np.array([0.05, 0.08, 0.0])
    if season == "fall" and sp.deciduous and sp.fall_rgb is not None:
        mix = r.uniform(0.3, 1.0, (n, 1))
        if sp.key == "sweetgum":  # famously multicoloured
            pal = np.array([sp.fall_rgb, (0.78, 0.55, 0.12), (0.35, 0.10, 0.25), (0.60, 0.25, 0.08)])
            alt = pal[r.integers(0, len(pal), n)]
        else:
            alt = np.array(sp.fall_rgb) * r.uniform(0.8, 1.15, (n, 1))
        cols = cols * (1 - mix) + alt * mix
    return np.clip(cols, 0, 1)


def _foliage_mesh(sp, sk, H, season, detail, r, moisture) -> Mesh:
    tex = {"broadleaf": textures.leaf_key(sp.key), "needle": textures.needle_key()}.get(sp.leaf)
    mb = MeshBuilder(tex)
    n_cards = 0
    pos, par, rad = sk.pos, sk.parent, sk.radius
    has_child = np.zeros(len(pos), bool)
    has_child[par[par >= 0]] = True
    twig_r = np.percentile(rad, 35)
    cand = np.nonzero((~has_child | (rad <= twig_r)) & ~sk.trunk)[0]
    if sp.leaf == "needle":
        cand = np.nonzero(~has_child & ~sk.trunk)[0]
    leafless = sp.deciduous and season == "winter"
    budget = LEAF_BUDGET[detail]
    crown_c = np.array([0, 0, (sp.crown_base + 1) / 2 * H])
    R = max(sp.crown_width * H / 2, 0.5)
    shell = 4 * np.pi * R * max(H * (1 - sp.crown_base) / 2, 0.5) * 1.2
    if len(cand) and not leafless:
        if sp.leaf == "broadleaf":
            # leaf-cluster cards: each quad shows a photographed sprig of ~15 leaves (alpha-masked)
            u0, v0, u1, v1, cov = textures.card_box(mb.texture)
            aspect = (u1 - u0) / max(v1 - v0, 1e-3)
            per = max(1, budget // 3 // len(cand))  # 4 triangles per folded card
            nl = per * len(cand)
            L = float(np.clip(np.sqrt(shell * 3.2 / (nl * aspect * max(cov, 0.2) * FOLD_COVER)),
                              sp.leaf_size / 0.3, sp.leaf_size * 60))
            # cards sit on their twig: a point along parent→node, plus a little spread (was N(0, 0.35 L))
            tw = np.repeat(cand, per)
            along = r.uniform(0.35, 1.0, (nl, 1))
            anchor = pos[par[tw]] + (pos[tw] - pos[par[tw]]) * along + r.normal(0, L * 0.12, (nl, 3))
            outward = _norm(anchor - crown_c + r.normal(0, 0.5, (nl, 3)))
            axis = _norm(outward + [0, 0, 0.15] + r.normal(0, 0.45, (nl, 3)))
            side = _norm(np.cross(axis, _norm([0, 0, 1] + r.normal(0, 0.6, (nl, 3)))))
            nrm = _norm(np.cross(side, axis))
            Ls = L * r.uniform(0.75, 1.2, (nl, 1))
            left = (u0 - 0.5) / (v1 - v0) * Ls   # the twig enters at the texture's bottom centre
            right = (u1 - 0.5) / (v1 - v0) * Ls
            # fold the card along its twig into a shallow V, so it still has width when seen edge-on
            th = r.uniform(0.35, 0.65, (nl, 1)) * np.where(r.uniform(0, 1, (nl, 1)) < 0.5, 1, -1)
            wl = -side * np.cos(th) + nrm * np.sin(np.abs(th))
            wr = side * np.cos(th) + nrm * np.sin(np.abs(th))
            tip = anchor + axis * Ls
            P = np.stack([anchor - wl * left, anchor, anchor + wr * right,
                          tip - wl * left, tip, tip + wr * right], 1).reshape(-1, 3)
            flip = r.uniform(0, 1, nl) < 0.5  # mirror half the cards so sprigs don't all lean one way
            ul, ur = np.where(flip, u1, u0), np.where(flip, u0, u1)
            uc = np.full(nl, 0.5)
            UV = np.stack([np.c_[ul, np.full(nl, v1)], np.c_[uc, np.full(nl, v1)], np.c_[ur, np.full(nl, v1)],
                           np.c_[ul, np.full(nl, v0)], np.c_[uc, np.full(nl, v0)], np.c_[ur, np.full(nl, v0)]],
                          1).reshape(-1, 2)
            ao = np.clip(np.linalg.norm(anchor - crown_c, axis=1) / R, 0.55, 1.1)[:, None]
            col = _leaf_colour(sp, season, r, nl) * ao
            C = np.repeat(col, 6, 0)
            base = (np.arange(nl) * 6)[:, None]
            idx = np.concatenate([base + [0, 1, 4], base + [0, 4, 3], base + [1, 2, 5], base + [1, 5, 4]])
            mb.add(P, C, idx, UV)
            n_cards = len(P)
        elif sp.leaf == "needle":
            # pines carry needles in brush-like tufts along the outer shoots: two crossed needle cards per tuft
            shoots = np.nonzero(~sk.trunk & (rad <= np.percentile(rad[~sk.trunk], 70)))[0]
            shoots = shoots if len(shoots) else cand
            u0, v0, u1, v1, cov = textures.card_box(mb.texture)
            aspect = (u1 - u0) / max(v1 - v0, 1e-3)
            ntuft = max(1, budget // 4)
            pick = r.choice(shoots, ntuft, replace=True)
            tip = pos[pick] + r.normal(0, 0.18, (ntuft, 3))
            fwd = _norm(pos[pick] - pos[par[pick]] + _norm(pos[pick] - crown_c) * 0.8)
            axis = _norm(fwd * 0.8 + r.normal(0, 0.35, (ntuft, 3)) + [0, 0, 0.35])
            Lc = float(np.clip(np.sqrt(shell * 0.9 / (ntuft * 2 * aspect * max(cov, 0.1))),
                               sp.leaf_size * 1.4, sp.leaf_size * 8)) * r.uniform(0.8, 1.15, (ntuft, 1))
            s1, s2 = _perp_frame(axis)
            left = (u0 - 0.5) / (v1 - v0) * Lc
            right = (u1 - 0.5) / (v1 - v0) * Lc
            quads = []
            for sd in (s1, s2):
                quads.append(np.stack([tip + sd * left, tip + sd * right, tip + sd * right + axis * Lc,
                                       tip + sd * left + axis * Lc], 1))
            P = np.concatenate(quads, 0).reshape(-1, 3)
            n = 2 * ntuft
            uvq = np.array([[u0, v1], [u1, v1], [u1, v0], [u0, v0]], np.float32)
            col = np.tile(_leaf_colour(sp, season, r, ntuft), (2, 1))
            base = (np.arange(n) * 4)[:, None]
            mb.add(P, np.repeat(col, 4, 0), np.concatenate([base + [0, 1, 2], base + [0, 2, 3]]), np.tile(uvq, (n, 1)))
            n_cards = len(P)
        elif sp.leaf == "scale_spray":
            per = max(1, budget // max(len(cand), 1))
            nl = per * len(cand)
            L = float(np.clip(np.sqrt(shell * 1.3 / (nl * 0.08)), 0.12, 0.7))
            anchor = np.repeat(pos[cand], per, 0) + r.normal(0, L * 0.4, (nl, 3))
            axis = _norm(_norm(anchor - crown_c) + [0, 0, -0.6] + r.normal(0, 0.35, (nl, 3)))
            side = _norm(np.cross(axis, [0, 0, 1]))
            w = L * 0.22
            P = np.stack([anchor - side * w / 2, anchor + side * w / 2,
                          anchor + axis * L + side * w / 4, anchor + axis * L - side * w / 4], 1).reshape(-1, 3)
            col = np.repeat(_leaf_colour(sp, season, r, nl), 4, 0)
            base = (np.arange(nl) * 4)[:, None]
            mb.add(P, col, np.concatenate([base + [0, 1, 2], base + [0, 2, 3]]))
        # flowers
        fl = sp.flowers
        if fl and fl.get("season") == season:
            nf = min(len(cand) * 2, budget // 3)
            at = pos[r.choice(cand, nf)] + r.normal(0, 0.08, (nf, 3))
            s = fl["size"] * (1.0 if detail == "cm" else 1.8)
            ang = np.linspace(0, 2 * np.pi, 5, endpoint=False)
            ring = np.c_[np.cos(ang), np.sin(ang), np.zeros(5)] * s
            P = (at[:, None, :] + ring[None] + [0, 0, 0.02]).reshape(-1, 3)
            P = np.concatenate([P, at + [0, 0, 0.03]])
            centre = len(at) * 5 + np.arange(nf)
            k = np.arange(5)
            idx = np.stack([np.repeat(centre, 5), (np.arange(nf)[:, None] * 5 + k).ravel(),
                            (np.arange(nf)[:, None] * 5 + (k + 1) % 5).ravel()], 1)
            col = np.tile(fl["rgb"], (len(P), 1)) * r.uniform(0.9, 1.05, (len(P), 1))
            mb.add(P, col, idx)
    # Spanish moss on near-horizontal limbs
    if sp.moss > 0 and moisture > 0.3:
        t = _norm(pos[1:] - pos[par[1:]])
        horiz = (np.abs(t[:, 2]) < 0.55) & (rad[1:] > 0.02) & (rad[1:] < 0.35)
        ids = np.nonzero(horiz)[0] + 1
        p = sp.moss * 0.35 * min(1.0, moisture * 1.4)
        ids = ids[r.uniform(0, 1, len(ids)) < p]
        segs = 6
        for i in ids:
            for _ in range(int(r.integers(2, 6))):
                top = pos[i] + r.normal(0, 0.15, 3) - [0, 0, rad[i]]
                L = r.uniform(0.3, 1.4)
                zz = np.linspace(0, L, segs)
                wig = r.normal(0, 0.04, (segs, 2)).cumsum(0)
                w = 0.06 * (1 - zz / L * 0.7)
                left = np.c_[top[0] + wig[:, 0] - w, top[1] + wig[:, 1], top[2] - zz]
                right = np.c_[top[0] + wig[:, 0] + w, top[1] + wig[:, 1], top[2] - zz]
                P = np.stack([left, right], 1).reshape(-1, 3)
                k = np.arange(segs - 1) * 2
                idx = np.concatenate([np.c_[k, k + 1, k + 2], np.c_[k + 1, k + 3, k + 2]])
                mb.add(P, np.array([0.56, 0.60, 0.52]) * r.uniform(0.85, 1.1), idx)
    m = mb.build()
    if n_cards and m.n_tris:
        m.nrm = _crown_normals(m.positions, m.geometric_normals(), n_cards, crown_c)
    return m


def _crown_normals(P, ng, n_cards, crown_c, k=0.65):
    """Rounded canopy normals (after ez-tree): leaf cards shade like the crown's volume, not like flat sheets.
    n = normalize(k·r̂ + (1 − k)·s·n_face), r̂ = outward from the crown centre, s flips n_face to r̂'s side."""
    n = ng.astype(np.float64).copy()
    rad = _norm(P[:n_cards] - crown_c)
    f = ng[:n_cards]
    s_ = np.where((f * rad).sum(1, keepdims=True) < 0, -1.0, 1.0)
    n[:n_cards] = _norm(k * rad + (1 - k) * s_ * f)
    return n.astype(np.float32)


def _knees(r, n_max=18, texture=None) -> Mesh:
    mb = MeshBuilder(texture)
    for _ in range(int(r.integers(5, n_max))):
        a, d = r.uniform(0, 2 * np.pi), r.uniform(1.0, 4.0)
        c = np.array([np.cos(a) * d, np.sin(a) * d, -0.2])
        h, rr = r.uniform(0.2, 0.8), r.uniform(0.06, 0.16)
        ang = np.linspace(0, 2 * np.pi, 7, endpoint=False)
        ring = c + np.c_[np.cos(ang) * rr, np.sin(ang) * rr, np.zeros(7)]
        P = np.vstack([ring, c + [0, 0, h]])
        k = np.arange(7)
        uv = np.r_[np.c_[np.arange(7) / 7 * rr * 6, np.zeros(7)], [[0.5 * rr * 6, h]]]
        mb.add(P, np.array([0.45, 0.36, 0.30]) * r.uniform(0.85, 1.1), np.c_[k, (k + 1) % 7, np.full(7, 7)], uv)
    return mb.build()


# ── palms ───────────────────────────────────────────────────────────────────

def _palm(sp, H, season, r):
    bark = MeshBuilder()
    fol = MeshBuilder()
    nseg, sides = 16, 9
    bend = r.normal(0, 0.06, 2)
    zz = np.linspace(0, H, nseg + 1)
    cx = bend[0] * (zz / H) ** 2 * H
    cy = bend[1] * (zz / H) ** 2 * H
    rad = r.uniform(*sp.dbh) / 2 * (1 + 0.25 * np.exp(-zz / 0.6))
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    P = np.stack([np.c_[cx[i] + np.cos(ang) * rad[i], cy[i] + np.sin(ang) * rad[i],
                        np.full(sides, zz[i] - (0.3 if i == 0 else 0))] for i in range(nseg + 1)]).reshape(-1, 3)
    boot = (zz / H > 0.25)[:, None] & ((np.arange(sides)[None, :] + np.arange(nseg + 1)[:, None]) % 2 == 0)
    col = np.where(boot[..., None], np.array([0.40, 0.33, 0.24]), np.array(sp.bark_rgb)).reshape(-1, 3)
    k = np.arange(sides)
    k1 = (k + 1) % sides
    quad = np.stack([k, k1, k + sides, k1, k1 + sides, k + sides], -1).reshape(-1, 3)
    idx = (quad[None] + (np.arange(nseg) * sides)[:, None, None]).reshape(-1, 3)
    bark.add(P, col, idx)
    top = np.array([cx[-1], cy[-1], H])
    nf = int(r.integers(20, 32))
    for f in range(nf + int(r.integers(0, 7))):
        dead = f >= nf
        az = r.uniform(0, 2 * np.pi)
        el = r.uniform(-1.2, -0.8) if dead else r.uniform(-0.35, 1.2)
        d = np.array([np.cos(az) * np.cos(el), np.sin(az) * np.cos(el), np.sin(el)])
        pet = top + d * r.uniform(1.0, 1.8)
        side = _norm(np.cross(d, [0, 0, 1]))
        L = sp.leaf_size * r.uniform(0.65, 0.9)
        nr = 22
        th = np.linspace(-1.75, 1.75, nr)
        rib = _norm(d[None] * np.cos(th)[:, None] * 0.9 + side[None] * np.sin(th)[:, None]
                    + [0, 0, 0.25 if not dead else -0.2])
        droop = np.array([0, 0, -0.45 * L])
        mid = pet + rib * L * 0.55
        tipp = pet + rib * L + droop * (np.abs(np.sin(th))[:, None] * 0.6 + 0.4)
        base_c = np.array([0.55, 0.42, 0.26]) if dead else np.array(sp.leaf_rgb) * r.uniform(0.85, 1.15)
        # petiole
        u = _norm(np.cross(d, [0, 0, 1])) * 0.025
        fol.add([top - u, top + u, pet + u, pet - u], base_c * 0.9, [[0, 1, 2], [0, 2, 3]])
        for j in range(nr - 1):
            fol.add([pet, mid[j], tipp[j], mid[j + 1]], base_c * r.uniform(0.85, 1.1),
                    [[0, 1, 3], [1, 2, 3]])
    return bark.build(), fol.build()


# ── public API ──────────────────────────────────────────────────────────────

def generate_tree(species: str, seed=0, season="summer", detail="med",
                  moisture=0.5, height=None, age=1.0) -> TreeModel:
    """Generate one unique tree. (species, seed) fully determines the result."""
    sp = SPECIES[species]
    r = make_rng("tree", species, seed)
    H = height if height is not None else r.uniform(*sp.height) * float(np.clip(age, 0.15, 1.2))
    if sp.crown == "palm":
        bark, fol = _palm(sp, H, season, r)
        sk = Skeleton(np.array([[0, 0, 0], [0, 0, H]], float), np.array([-1, 0]),
                      np.array([sp.dbh[0] / 2] * 2), np.array([True, True]))
        return TreeModel(sp, (species, seed), H, sk, bark, fol)
    sk = grow_skeleton(sp, H, r)
    bare = sp.deciduous and season == "winter"  # nothing hides the twigs: keep them at every detail
    bark = _bark_mesh(sp, sk, r, min(TWIG_CULL[detail], TWIG_CULL["high"]) if bare else TWIG_CULL[detail])
    if sp.knees and moisture > 0.65:
        bark = Mesh.merge([bark, _knees(r, texture=bark.texture)])
    fol = _foliage_mesh(sp, sk, H, season, detail, r, moisture)
    return TreeModel(sp, (species, seed), H, sk, bark, fol)

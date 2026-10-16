"""How a tree answers the wind: the trunk, its limbs, their branches, and the leaves, each its own oscillator.

All four levels are linear, damped, single-degree-of-freedom oscillators driven by the field of field.py. A
linear system driven by a sum of sinusoids answers with the same sinusoids, each scaled by the transfer
function's gain and delayed by its phase:

    H(f) = 1 / (1 − r² + 2iζr),   r = f / f_n,    |H| = 1/√((1 − r²)² + (2ζr)²),   ψ = atan2(2ζr, 1 − r²)

so the viewer can evaluate the motion statelessly at any time (no integration, no state, scrubbable).

Drag. A crown of frontal area A loads like a bluff body that streamlines as the wind rises (Vogel 1989):
    F(U) = ½ ρ C_d0 A U² (1 + U/U_0)^b,   b < 0 the Vogel exponent: F ∝ U² in light air, U^{2+b} in strong
Fluctuations are linearised about the mean Ū: δF_along = (2+b) F̄ u'/Ū, δF_across = F̄ v'/Ū (the force
vector turns with the wind).

Trunk. f_0 is Rayleigh's quotient on the static shape δ of the whole tree under its own weight applied
sideways, ω² = g Σ m δ / Σ m δ² (stem and limb main chains flex; twigs under 3 cm ride rigidly). The mode
shape the viewer uses is φ(z) = 1 − cos(π z/2H); generalised mass m* = Σ m_i φ_i², force F* = Σ F_i φ_i,
k* = (2π f_0)² m*, and the top's static deflection Q = F*/k*.

Limbs and branches. Each skeleton segment is an Euler–Bernoulli beam of green wood, I = π r⁴/4. The drag of
the leaves beyond a segment bends it: M = Σ F_j |p_j − p_base|, κ = M/(E I). Integrating κ outward from the
trunk gives each node's static deflection δ_i. A limb's frequency is its Rayleigh quotient on that shape,
    ω² = Σ F_j δ_j / Σ m_j δ_j²
(exact for one degree of freedom; an upper bound otherwise). Second-order branches get their own δ and ω
relative to the point where they leave their limb.

Leaves. Cards tip into the wind (reconfiguration) and flutter; see leaf_flutter. See docs/TECHNIQUES.md §34.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from .field import RHO_AIR

# ── material and aerodynamic constants (quotes and URLs in catalog/wind_sources.json) ──
# green-wood modulus of elasticity (MPa) and specific gravity (oven-dry weight / green volume), USDA Wood
# Handbook FPL-GTR-113 Table 4-3a, "Green" rows. Dogwood and redbud are not tabulated: hardwood mean (design).
WOOD = {"live_oak": (10900, 0.80), "white_oak": (8600, 0.60), "water_oak": (10700, 0.56),
        "sweetgum": (8300, 0.46), "tulip_poplar": (8400, 0.40), "southern_magnolia": (7700, 0.46),
        "loblolly_pine": (9700, 0.47), "longleaf_pine": (11000, 0.54), "bald_cypress": (8100, 0.42)}
WOOD_DEFAULT = (9200, 0.54)  # design: mean of the hardwood rows above
MC_GREEN = 0.8         # moisture content of green wood (fraction of dry mass): design value
LEAF_FRACTION = 0.09   # fresh foliage mass / wood mass: calibrated so leafless trunks sway 18 % faster (Jackson 2019)
CD_20 = 0.185          # crown drag coefficient at 20 m/s, midpoint of Vollsinger et al. 2005's 0.15–0.22
U0 = 4.0               # m/s, speed scale of streamlining in drag() (design)
VOGEL_B = -1.0         # Vogel exponent: ≈ −1 for hardwood crowns and the tuliptree leaf, −1.1 loblolly (Gosselin 2019)
CD0 = CD_20 * (1 + 20.0 / U0) ** (-VOGEL_B)  # so drag() gives exactly C_d = 0.185 at 20 m/s
ZETA_LEAFY, ZETA_BARE = 0.086, 0.039   # trunk damping in leaf / bare (Jackson et al. 2019 pull tests)
ZETA_BRANCH = 0.06     # limbs and branches: 4.5–7.5 % measured on a silver maple branch (James 2014)
TWIG_R = 0.03          # m: thinner twigs flex locally (branch and leaf modes), not with the stem (design)
U_REF = 4.0            # m/s, the reference speed every stored deflection is computed at
D_MAX = 1.0            # m, quantisation range of stored branch deflections (uint8)
L_MAX = 0.6            # m, quantisation range of leaf-card lever arms
F1_MAX, F2_MAX = 8.0, 16.0  # Hz, quantisation ranges of limb / branch frequencies


def drag(U, A, cd=None):
    """Crown drag with reconfiguration, one smooth law: F = ½ρ C_d0 A U² (1 + U/U0)^b. Quadratic in light air,
    ∝ U^{2+b} once the crown streamlines; the slope never jumps (a kinked law shows as a dip in gustiness)."""
    U = np.asarray(U, float)
    return 0.5 * RHO_AIR * (CD0 if cd is None else cd) * A * U ** 2 * (1 + U / U0) ** VOGEL_B


def drag_slope(U):
    """β = d ln F / d ln U = 2 + b (U/U0) / (1 + U/U0)."""
    U = np.asarray(U, float)
    return 2 + VOGEL_B * (U / U0) / (1 + U / U0)


def transfer(f, fn, zeta):
    """Gain |H| and phase lag ψ of a damped oscillator at forcing frequency f."""
    r = np.asarray(f, float) / np.maximum(fn, 1e-6)
    den = np.hypot(1 - r ** 2, 2 * zeta * r)
    return 1 / den, np.arctan2(2 * zeta * r, 1 - r ** 2)


def mode_shape(z, H):
    """First bending mode of a cantilever, approximated by φ(z) = 1 − cos(π z / 2H) (Rayleigh's choice; within
    4 % of the exact frequency for a uniform beam, where (z/H)² is 27 % high)."""
    return 1 - np.cos(np.pi * np.clip(np.asarray(z, float) / H, 0, 1) / 2)


def wood(species_key):
    E, sg = WOOD.get(species_key, WOOD_DEFAULT)
    return E * 1e6, sg * 1000 * (1 + MC_GREEN)


@dataclass
class TreeWind:
    H: float          # m, model height
    dbh: float        # m
    f0: float         # Hz, first trunk mode
    zeta: float
    area: float       # m², crown frontal area
    zc: float         # m, height of the crown's centre of pressure
    m_eff: float      # kg, generalised mass of mode 1
    Q_ref: float      # m, top static deflection at U_REF (canopy-top wind)
    mass: float       # kg, wood + leaves

    def to_json(self):
        return {k: round(float(v), 5) for k, v in self.__dict__.items()}


# ── geometry of a tree model ──

def _seg_mass(sk, rho):
    par = sk.parent
    L = np.zeros(len(sk.pos))
    L[1:] = np.linalg.norm(sk.pos[1:] - sk.pos[par[1:]], axis=1)
    return rho * np.pi * sk.radius ** 2 * L, L


def _components(m):
    """Connected components of a mesh (one per leaf card, moss strand, flower)."""
    n = len(m.positions)
    if not len(m.indices):
        return np.arange(n), n
    i = m.indices
    rows = np.r_[i[:, 0], i[:, 1], i[:, 2]]
    cols = np.r_[i[:, 1], i[:, 2], i[:, 0]]
    g = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    k, lab = connected_components(g, directed=False)
    return lab, k


def leaf_cards(foliage, sk):
    """Per foliage vertex: its card id, the card's anchor (the vertex nearest the skeleton), the skeleton node
    it hangs from, and its lever arm from the anchor. Plus each card's node and one-sided area."""
    P = foliage.positions.astype(np.float64)
    lab, k = _components(foliage)
    tree = cKDTree(sk.pos)
    dist, node = tree.query(P)
    anchor = np.zeros(k, int)
    order = np.lexsort((dist, lab))            # within each card, nearest-to-skeleton first
    first = np.r_[True, lab[order][1:] != lab[order][:-1]]
    anchor[lab[order][first]] = order[first]
    av = anchor[lab]
    lever = np.linalg.norm(P - P[av], axis=1)
    i = foliage.indices
    tri_a = 0.5 * np.linalg.norm(np.cross(P[i[:, 1]] - P[i[:, 0]], P[i[:, 2]] - P[i[:, 0]]), axis=1)
    area = np.bincount(lab[i[:, 0]], tri_a, minlength=k)
    return lab, node[av], lever, node[anchor], area


def frontal_area(foliage, bark, cell=0.25):
    """Silhouette area of the crown (and stem) seen along x and along y, averaged: occupancy of `cell` m
    squares by triangle centroids and vertices."""
    pts = [m.positions for m in (foliage, bark) if m is not None and len(m.positions)]
    if not pts:
        return 0.0
    P = np.concatenate(pts)
    for m in (foliage, bark):
        if m is not None and len(m.indices):
            P = np.concatenate([P, m.positions[m.indices].mean(1)])
    out = []
    for ax in (0, 1):
        q = np.floor(P[:, [ax, 2]] / cell).astype(np.int64)
        out.append(len(np.unique(q[:, 0] * 100003 + q[:, 1])) * cell * cell)
    return float(np.mean(out))


def mechanics(tm, season="summer"):
    """Trunk parameters and per-node branch mechanics of a tree model.

    Returns (TreeWind, nodes) where nodes is a dict of per-skeleton-node arrays:
      d1, d2   static deflection (m) at U_REF of the limb mode / of the branch relative to its limb
      f1, f2   natural frequency (Hz) of the node's limb / branch
      limb     limb id (−1 on the trunk), axis (unit limb direction), F (N, drag at U_REF), m (kg)
    """
    sk = tm.skeleton
    pos, par, rad, trunk = sk.pos, sk.parent, sk.radius, sk.trunk
    n = len(pos)
    H = float(tm.height)
    fol = tm.foliage
    E_GREEN, rho = wood(tm.species.key)
    wood_m, seg_L = _seg_mass(sk, rho)
    leaf_area = np.zeros(n)
    if fol is not None and len(fol.positions):
        _, _, _, cnode, area = leaf_cards(fol, sk)
        np.add.at(leaf_area, cnode, area)
    A = frontal_area(fol, tm.bark)
    Fref = float(drag(U_REF, A))
    # drag per node ∝ its leaf area; a leafless (winter) tree catches wind on its twigs: ∝ r·L
    leafy = leaf_area.sum() > 0 and not (tm.species.deciduous and season == "winter")  # moss is not leaves
    w = leaf_area + 1e-3 * rad * seg_L * (~trunk) if leafy else rad * seg_L * (~trunk)
    F = Fref * w / max(w.sum(), 1e-9)
    m = wood_m + (LEAF_FRACTION * wood_m.sum() * w / max(w.sum(), 1e-9) if leafy else 0.0)
    phi = mode_shape(pos[:, 2], H)
    m_eff = float((m * phi ** 2).sum())
    F_eff = float((F * phi).sum())
    tz = np.nonzero(trunk)[0]
    tz = tz[np.argsort(pos[tz, 2])]
    dbh = 2 * float(np.interp(1.3, pos[tz, 2], rad[tz])) if len(tz) > 1 else 2 * float(rad[0])
    zc = float((F * pos[:, 2]).sum() / max(F.sum(), 1e-9))

    # tree topology: children lists, limb = subtree rooted at a non-trunk child of a trunk node
    kids = [[] for _ in range(n)]
    for i in range(1, n):
        kids[par[i]].append(i)
    limb = np.full(n, -1)
    level2_root = np.full(n, -1)  # the node where a branch leaves its limb's main chain
    bfs = [0]
    for i in bfs:
        bfs.extend(kids[i])
    order = np.array(bfs)
    main_child = np.full(n, -1)
    for i in range(n):
        ks = [k for k in kids[i] if not trunk[k]]
        if ks:
            main_child[i] = max(ks, key=lambda k: rad[k])
    on_main = np.zeros(n, bool)
    nl = 0
    for i in order:
        if trunk[i]:
            continue
        p = par[i]
        if trunk[p]:
            limb[i] = nl
            nl += 1
            on_main[i] = True
        else:
            limb[i] = limb[p]
            on_main[i] = on_main[p] and main_child[p] == i
            if not on_main[i]:
                level2_root[i] = level2_root[p] if level2_root[p] >= 0 else p
    # elastic similarity (McMahon & Kronauer 1976): a branch reaching L metres beyond a point is at least
    # d = c L^{3/2} thick there, with c calibrated on this tree's own trunk, c = DBH / H^{3/2}. The drawn
    # radii taper to a fixed 1.2 cm tip (flora/tree.py R_TIP), too thin to carry metres of twig.
    reach = np.zeros(n)
    for i in order[::-1]:
        if i:
            reach[par[i]] = max(reach[par[i]], reach[i] + seg_L[i])
    c_el = dbh / H ** 1.5
    r_mech = np.where(trunk, rad, np.maximum(rad, 0.5 * c_el * reach ** 1.5))
    r_seg = np.where(np.arange(n) > 0, 0.5 * (r_mech + r_mech[np.maximum(par, 0)]), r_mech)
    EI = E_GREEN * np.pi * r_seg ** 4 / 4
    # moments: M at a segment's base (the parent end) from every load beyond it, walking each loaded node down
    # to the root. Branch segments use the lever |p_j − p_base|; trunk segments the height above the base
    # (a horizontal load on a vertical stem).
    def curvature(load):
        M = np.zeros(n)
        for j in np.nonzero(load > 0)[0]:
            i = j
            while i > 0:
                b_ = pos[par[i]]
                M[i] += load[j] * (max(pos[j, 2] - b_[2], 0.0) if trunk[i] else np.linalg.norm(pos[j] - b_))
                i = par[i]
        return M / EI

    def integrate(kappa, from_trunk):
        """Rotation and deflection integrated outward: from the root (whole tree) or from the trunk (limbs)."""
        th_, de_ = np.zeros(n), np.zeros(n)
        for i in order:
            if i == 0 or (trunk[i] and not from_trunk):
                continue
            p = par[i]
            th = th_[p] + kappa[i] * seg_L[i]
            de_[i] = de_[p] + seg_L[i] * 0.5 * (th_[p] + th)
            th_[i] = th
        return de_
    arc = np.zeros(n)
    for i in order:
        if i and not trunk[i]:
            arc[i] = arc[par[i]] + seg_L[i]
    # first mode: Rayleigh's quotient on the whole tree's static shape under its own weight applied sideways,
    # ω² = g Σ m δ / Σ m δ². Stem and limbs flex together, which is why broadleaves sway slower than a bare
    # cantilever (Jackson et al. 2019)
    # (sub-branches ride rigidly on their limbs here: their own flex is the branch modes', not the stem's)
    dg = integrate(curvature(m * 9.81) * (trunk | (on_main & (r_seg > TWIG_R))), True)
    f0 = float(np.sqrt(9.81 * (m * dg).sum() / max((m * dg ** 2).sum(), 1e-12)) / (2 * np.pi))
    k_eff = (2 * np.pi * f0) ** 2 * m_eff
    tw = TreeWind(H, dbh, f0, ZETA_LEAFY if leafy else ZETA_BARE, A, zc, m_eff, F_eff / max(k_eff, 1e-9),
                  float(m.sum()))
    delta = integrate(curvature(F), False)
    delta = np.minimum(delta, 0.35 * arc)
    # split into the limb's own mode (deflection of the limb's main chain at the branch's root) + the branch
    d1 = np.where(level2_root >= 0, delta[np.maximum(level2_root, 0)], delta)
    d2 = delta - d1
    mm = m + 1e-6
    # limb and branch frequencies: Rayleigh again, on each one's static shape under its own weight sideways
    dw = integrate(curvature(m * 9.81), False)
    w1 = np.where(level2_root >= 0, dw[np.maximum(level2_root, 0)], dw)
    w2 = dw - w1

    def rayleigh(ids, d):
        d = (w1 if d is d1 else w2)[ids]
        num = float(9.81 * (mm[ids] * d).sum())
        den = float((mm[ids] * d ** 2).sum())
        return np.sqrt(num / den) / (2 * np.pi) if den > 0 and num > 0 else 0.0
    f1 = np.zeros(n)
    axis = np.zeros((n, 3))
    for L in range(nl):
        ids = np.nonzero(limb == L)[0]
        f1[ids] = np.clip(rayleigh(ids, d1), 0.2, F1_MAX)
        root = ids[0]
        tip = ids[np.argmax(arc[ids] * on_main[ids])]
        v = pos[tip] - pos[par[root]]
        axis[ids] = v / max(np.linalg.norm(v), 1e-9)
    f2 = np.zeros(n)
    for r2 in np.unique(level2_root[level2_root >= 0]):
        ids = np.nonzero(level2_root == r2)[0]
        f2[ids] = np.clip(rayleigh(ids, d2), 0.4, F2_MAX)
    nodes = dict(d1=d1, d2=d2, f1=f1, f2=f2, limb=limb, branch=level2_root, axis=axis, F=F, m=m,
                 leaf_area=leaf_area)
    return tw, nodes

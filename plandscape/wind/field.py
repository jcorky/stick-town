"""One deterministic wind field for the whole scene: mean profile, gusts, and their travel downwind.

Every consumer reads this field: trunks, branches, leaves, grass, and (later) scent and noise for the animals'
senses. It is a sum of sinusoids, so the viewer can evaluate it statelessly, per vertex, at any time and get
exactly what Python gets (viewer/wind.js mirrors `Wind.gust`). See docs/TECHNIQUES.md §34.

Mean wind. The scene's Beaufort force sets the open-country speed U10 at 10 m (z0 = 0.03 m). It is carried up
to a blending height z_b = 60 m, where the forest and the open field share one wind, and back down over the
canopy with the forest's own roughness:

    U(z) = (u*/κ) ln((z − d)/z0)        z ≥ h      d = 2h/3, z0 = 0.123 h (FAO-56), u* fixed by U(z_b)
    U(z) = U(h) exp(a (z/h − 1))        z < h      a = canopy attenuation coefficient

Gusts. The streamwise fluctuation u' has the Kaimal spectrum
    f S_u(f) / u*² = 102 n / (1 + 33 n)^{5/3},     n = f z / U(z)
sampled in 10 log-spaced bands of 3 waves each (frequency log-uniform in the band), amplitude a_k ∝ √(2 S(f_k) Δf_k),
phase φ_k from rng("wind", …),
then scaled so Σ a_k²/2 = σ_u² with the measured σ_u = 1.7 u* over canopies (2.4 u* over flat open ground).
The lateral v' has Kaimal's v-shape, f S_v / u*² = 17 n / (1 + 9.5 n)^{5/3}, scaled to σ_v = 0.8 σ_u.

Frozen turbulence (Taylor 1938). The gust pattern travels downwind at the convection speed U_c, so a gust that
hits one tree reaches the next one ξ metres downwind ξ/U_c seconds later:
    u'(ξ, η, t) = Σ a_k cos(2π f_k (t − ξ/U_c) − ℓ_k η + φ_k)
ξ is distance along the wind, η across it. Each component also tilts across the wind with a lateral wavenumber
ℓ_k = 2π f_k c_k / U_c, c_k drawn from a Cauchy distribution of scale γ (three tilts per band, so one
realisation already breaks into patches instead of fronts). Averaged over the draws, two points η
apart then keep the coherence E[cos(ℓ_k η)] = exp(−γ 2π f η / U_c): exactly Davenport's exponential coherence
exp(−C_y f η / U) with C_y = 2πγ. Small gusts decorrelate across the wind quickly, large ones sweep whole stands.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..rng import rng as make_rng

KAPPA = 0.41          # von Kármán constant
Z0_OPEN = 0.03        # m, roughness of open country (the 10 m reference exposure)
Z_BLEND = 60.0        # m, blending height (design value: forest and field winds agree above it)
RHO_AIR = 1.2         # kg/m³

# Beaufort force → knots band (NOAA SPC table) → 10 m mean speed in m/s at the band's midpoint (1 kn = 0.5144 m/s);
# force 12 ("64+") is taken at 66 kn
KNOTS = {0: (0, 1), 1: (1, 3), 2: (4, 6), 3: (7, 10), 4: (11, 16), 5: (17, 21), 6: (22, 27), 7: (28, 33),
         8: (34, 40), 9: (41, 47), 10: (48, 55), 11: (56, 63), 12: (64, 68)}
BEAUFORT = {k: round(0.5144 * (a + b) / 2, 2) for k, (a, b) in KNOTS.items()}
LAND = {0: "Calm, smoke rises vertically", 1: "Smoke drift indicates wind direction, still wind vanes",
        2: "Wind felt on face, leaves rustle, vanes begin to move",
        3: "Leaves and small twigs constantly moving, light flags extended",
        4: "Dust, leaves, and loose paper lifted, small tree branches move",
        5: "Small trees in leaf begin to sway", 6: "Larger tree branches moving, whistling in wires",
        7: "Whole trees moving, resistance felt walking against wind",
        8: "Twigs breaking off trees, generally impedes progress",
        9: "Slight structural damage occurs, slate blows off roofs",
        10: "Seldom experienced on land, trees broken or uprooted", 11: "Violent storm", 12: "Hurricane"}
CANOPY_A = 1.05       # in-canopy attenuation a: "1.0 - 1.1 for larch and small evergreen trees" (Stull)
D_FRAC, Z0_FRAC = 2 / 3, 0.123   # d = 2/3 h, z0 = 0.123 h (FAO-56)
SIGMA_U = {"forest": 1.7, "open": 2.4}  # σ_u / u*: roughness sublayer over canopies / flat terrain
SIGMA_V = 0.8         # σ_v / σ_u
CONVECTION = 1.0      # U_c / U(h): gust patterns travel at the mean canopy-top speed (Taylor)
DAVENPORT_CY = 7.0    # lateral coherence decay C_y (design value)
N_BAND = 10           # frequency bands
N_SUB = 3             # waves per band, each with its own lateral tilt: patches, not plane fronts
F_LO, F_HI = 0.01, 1.2   # Hz: from 100 s weather swells to sub-second buffets


def kaimal_u(f, z, U, ustar):
    n = f * z / U
    return 102 * n / (1 + 33 * n) ** (5 / 3) * ustar ** 2 / f


def kaimal_v(f, z, U, ustar):
    n = f * z / U
    return 17 * n / (1 + 9.5 * n) ** (5 / 3) * ustar ** 2 / f


def log_speed(z, ustar, d, z0):
    return ustar / KAPPA * np.log(np.maximum(z - d, z0 * 1.0001) / z0)


@dataclass
class Wind:
    force: float = 3.0            # Beaufort
    from_deg: float = 180.0       # meteorological: the direction it blows FROM, clockwise from north
    canopy_h: float = 18.0        # m, mean canopy height of the scene (0.3 m for open grass)
    seed: int = 0
    n: int = N_BAND * N_SUB
    comps: dict = field(default=None, repr=False)

    def __post_init__(self):
        f = float(self.force)
        lo, hi = int(np.floor(f)), int(np.ceil(f))
        self.U10 = float(np.interp(f, [lo, hi], [BEAUFORT[max(0, min(12, lo))], BEAUFORT[max(0, min(12, hi))]])
                         if hi != lo else BEAUFORT[max(0, min(12, lo))])
        a = np.radians(self.from_deg)
        self.dir = np.array([-np.sin(a), -np.cos(a)])     # unit vector the air moves toward (x east, y north)
        self.perp = np.array([-self.dir[1], self.dir[0]])  # 90° to the left of the flow
        h = max(self.canopy_h, 0.3)
        self.d, self.z0 = D_FRAC * h, max(Z0_FRAC * h, Z0_OPEN)
        ustar_open = KAPPA * self.U10 / np.log(10 / Z0_OPEN)
        Ub = log_speed(Z_BLEND, ustar_open, 0.0, Z0_OPEN)
        self.ustar = KAPPA * Ub / np.log((Z_BLEND - self.d) / self.z0)
        self.Uh = float(log_speed(h, self.ustar, self.d, self.z0)) if h > self.d + self.z0 else self.U10
        self.Uh = max(self.Uh, 0.05)
        self.h = h
        self.Uc = CONVECTION * self.Uh
        if self.comps is None:
            self.comps = self._components()

    # ── mean profile ──
    def mean_speed(self, z, cover=1.0):
        """Mean speed at height z above ground. `cover` 0..1 is the local canopy fraction: in the open the
        log law of open country holds all the way down; under full canopy the exponential in-canopy profile."""
        z = np.asarray(z, float)
        above = log_speed(np.maximum(z, self.d + self.z0 * 1.01), self.ustar, self.d, self.z0)
        inside = self.Uh * np.exp(CANOPY_A * (np.minimum(z, self.h) / self.h - 1))
        forest = np.where(z >= self.h, above, inside)
        ustar_open = KAPPA * self.U10 / np.log(10 / Z0_OPEN)
        open_ = log_speed(np.maximum(z, Z0_OPEN * 1.01), ustar_open, 0.0, Z0_OPEN)
        c = np.clip(cover, 0, 1)
        return (1 - c) * open_ + c * forest

    # ── gusts ──
    def _components(self):
        r = make_rng("wind", self.seed, "components")
        nb = self.n // N_SUB
        fb = np.geomspace(F_LO, F_HI, nb + 1)                 # band edges
        lo, hi = np.repeat(fb[:-1], N_SUB), np.repeat(fb[1:], N_SUB)
        fk = np.exp(r.uniform(np.log(lo), np.log(hi)))      # each wave's frequency, log-uniform in its band
        df = (hi - lo) / N_SUB
        zr = self.h + 2.0  # reference: just above the canopy, where the crowns catch the wind
        Ur = float(log_speed(zr, self.ustar, self.d, self.z0)) if self.h > 1 else self.U10
        au = np.sqrt(2 * kaimal_u(fk, zr, Ur, self.ustar) * df)
        av = np.sqrt(2 * kaimal_v(fk, zr, Ur, self.ustar) * df)
        # Kaimal's shape, scaled to the measured intensity: σ_u = 1.7 u* over a canopy (2.4 in the open), σ_v = 0.8 σ_u
        su = SIGMA_U["forest" if self.h >= 2 else "open"] * self.ustar
        au *= su / np.sqrt((au ** 2).sum() / 2)
        av *= SIGMA_V * su / np.sqrt((av ** 2).sum() / 2)
        gamma = DAVENPORT_CY / (2 * np.pi)
        c = np.clip(gamma * np.tan(np.pi * (r.uniform(0, 1, (2, self.n)) - 0.5)), -8, 8)  # Cauchy(0, γ)
        ell = 2 * np.pi * fk * c / self.Uc
        c = dict(f=fk, au=au / Ur, av=av / Ur, pu=r.uniform(0, 2 * np.pi, self.n),
                 pv=r.uniform(0, 2 * np.pi, self.n), lu=ell[0], lv=ell[1])
        return {k: v.astype(np.float32).astype(np.float64) for k, v in c.items()}  # what the GPU holds

    def phases(self, x, y, t):
        """θ_k for u' and v' at (x, y, t): (..., n) arrays."""
        x, y, t = (np.asarray(v, float)[..., None] for v in (x, y, t))
        xi = x * self.dir[0] + y * self.dir[1]
        eta = x * self.perp[0] + y * self.perp[1]
        c = self.comps
        w = 2 * np.pi * c["f"] * (t - xi / self.Uc)
        return w - c["lu"] * eta + c["pu"], w - c["lv"] * eta + c["pv"]

    def gust(self, x, y, t):
        """Relative fluctuations (u'/U, v'/U) at (x, y, t): the same numbers the viewer computes."""
        tu, tv = self.phases(x, y, t)
        c = self.comps
        return (np.cos(tu) * c["au"]).sum(-1), (np.cos(tv) * c["av"]).sum(-1)

    def at(self, x, y, z, t, cover=1.0):
        """Wind vector (vx, vy) in m/s at a point: mean profile × (1 + u'/U) along the wind, v' across it."""
        U = self.mean_speed(z, cover)
        gu, gv = self.gust(x, y, t)
        a = U * np.maximum(1 + gu, 0.0)  # the along-wind speed never reverses in this model
        b = U * gv
        return a * self.dir[0] + b * self.perp[0], a * self.dir[1] + b * self.perp[1]

    def to_json(self):
        c = self.comps
        return dict(force=self.force, from_deg=self.from_deg, U10=float(self.U10), Uh=float(self.Uh),
                    Uc=float(self.Uc), canopy_h=self.h, d=float(self.d), z0=float(self.z0),
                    ustar=float(self.ustar), a=CANOPY_A, dir=[float(v) for v in self.dir],
                    **{k: [float(np.float32(v)) for v in c[k]] for k in ("f", "au", "av", "pu", "pv", "lu", "lv")})

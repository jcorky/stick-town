"""How an animal notices the player, and what it does about it (TECHNIQUES §35).

Three senses feed one alarm level. Each gives a salience s ∈ [0, 1]; they combine as independent cues,
S = 1 − Π(1 − s_i), scaled by experience, S' = min(1, S e^{σ − η}) (σ sensitisation, η habituation). The alarm
follows S' up quickly and lets go slowly:  da/dt = (S' − a)/τ_r  if S' > a,  else −a/τ_d.
Above A_ALERT the animal stops and shows its alarm display; above A_FLEE, or aware and inside its flight-initiation
distance, it flees. viewer/life.js mirrors every function here (tests compare them).

Sight    s_v = acuity · fov(θ) · motion(v) · posture · light · e^{−d/R_v} · T_cover
Hearing  L = L_src − 20 log10(d) − 0.05 d_fol  (spherical spreading, VDI 2714 foliage loss),
         masked by vegetation noise in the wind, L_w = max(25, 55.2 + 23 log10(U/5.1)) dBA;  s_h = clip((L − L_w + H)/10, 0, 1)
Smell    the player's scent is a Gaussian plume carried by the wind field (Briggs 1973 class D, open country):
         c ∝ exp(−y²/2σ_y²) exp(−h²/2σ_z²) / (U σ_y σ_z),  σ_y = 0.08x(1+0.0001x)^{−½},  σ_z = 0.06x(1+0.0015x)^{−½}
         s_o = 0.75 clip(1 + ln(c / c_o), 0, 1), c_o = c(R_o, 0, U): full at the design scent range R_o on the
         plume axis, nothing below c_o / e; capped at 0.75 so scent alone alerts but does not stampede.
FID      D = D_0 · (0.6 + 0.4 min(v/1.31, 2.5)) · (0.7 + 0.3 max(cos β, 0)) · e^{σ − η}
         faster and more direct approaches flush animals farther away (Stankowich & Coss 2006); habituated ones
         let people closer (Samia et al. 2015). D_0 per species from catalog/perception_sources.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

WALK = 1.31            # m/s, usual outdoor walking pace (meta-analysis, PMC7806575)
A_ALERT, A_FLEE = 0.3, 0.8
ALARM_RISE, ALARM_TAU = 1.0, 20.0       # s to follow a cue up, s to let it go (design)
FOLIAGE_DB = 0.05      # dB per metre of foliage (VDI 2714)
CLAP_DB = 85.2         # dB, loudest hand clap (taken at 1 m; design distance)
WIND_DB0, WIND_DB_LOG, QUIET_DB = 55.2, 23.0, 25.0   # vegetation noise 55.2 dBA at 5.1 m/s, 23 log U (Bolin 2006)
STEP_DB = {"walk": 55.0, "run": 65.0, "crouch": 42.0}             # design: footstep levels at 1 m not found
GROUND_DB = {"litter": 6.0, "grass": 0.0, "trail": -4.0, "water": 10.0}  # design
POSTURE = {"stand": 1.0, "crouch": 0.5}  # design: crouching effect not quantified in the literature found
SOURCE_SIGMA = 0.5     # m, initial plume width (a person, design)
NOSE_H = 1.0           # m, release / sampling height (design)
COVER_K = 0.08         # 1/m of full cover along the sight line (design)
SMELL_MAX = 0.75       # scent alone alerts but does not stampede: suspicious game slips away or "will circle
                       # downwind" (TPWD); flight needs a second cue or closeness (design cap)

# per species: (FID D_0 m, sight range R_v m, acuity, field of view deg, hearing bonus dB, scent range R_o m,
#               twilight-sighted, alert display, flight)
SENSES = {
    "white_tailed_deer": dict(fid=45.0, rv=70.0, acuity=1.0, fov=310.0, hear=5.0, ro=250.0, twilight=True,
                              display="stomps and snorts", flight="run"),
    "wild_turkey": dict(fid=35.0, rv=90.0, acuity=3.5, fov=270.0, hear=0.0, ro=15.0, twilight=False,
                        display="putts", flight="run"),
    "gray_squirrel": dict(fid=9.2, rv=30.0, acuity=1.0, fov=300.0, hear=0.0, ro=30.0, twilight=False,
                          display="kuks and flags its tail", flight="climb"),
    "coyote": dict(fid=50.0, rv=60.0, acuity=1.0, fov=250.0, hear=5.0, ro=250.0, twilight=True,
                   display="stares", flight="run"),
    "raccoon": dict(fid=8.0, rv=20.0, acuity=0.6, fov=200.0, hear=3.0, ro=120.0, twilight=True,
                    display="freezes", flight="climb"),
    "armadillo": dict(fid=3.0, rv=4.0, acuity=0.2, fov=180.0, hear=0.0, ro=40.0, twilight=True,
                      display="jumps straight up", flight="run"),
    "box_turtle": dict(fid=2.0, rv=6.0, acuity=0.4, fov=180.0, hear=-10.0, ro=10.0, twilight=False,
                       display="pulls in its head", flight="withdraw"),
    "great_blue_heron": dict(fid=60.0, rv=100.0, acuity=2.0, fov=300.0, hear=0.0, ro=0.0, twilight=True,
                             display="stretches its neck", flight="fly"),
    "human": dict(fid=0.0, rv=60.0, acuity=1.0, fov=180.0, hear=0.0, ro=0.0, twilight=False,
                  display="looks over", flight="none"),
}
HABIT_STEP, SENSITISE_STEP, FEED_STEP, MEMORY_MAX = 0.15, 0.3, 0.3, 1.5   # design: per-encounter rates not found


def fov_gain(theta, fov_deg):
    """1 inside the field of view, 0.15 behind the animal (it still turns its head now and then)."""
    return np.where(np.abs(theta) <= np.radians(fov_deg) / 2, 1.0, 0.15)


def motion_gain(v):
    """A still person is seen far less than a moving one (deer rods are motion detectors)."""
    return 0.25 + 0.75 * np.clip(np.asarray(v, float) / WALK, 0, 1.5) / 1.5


def light_gain(intensity, twilight):
    """Daylight 0.05..1; twilight-sighted species keep 0.9 of their sight between dusk and dawn."""
    i = np.clip(intensity, 0.05, 1.0)
    return np.maximum(i, 0.9) if twilight and i < 0.6 else i


def sight(sp, d, theta, v, posture="stand", intensity=1.0, cover_tau=0.0):
    s = SENSES[sp]
    return float(np.clip(s["acuity"] * fov_gain(theta, s["fov"]) * motion_gain(v) * POSTURE[posture]
                         * light_gain(intensity, s["twilight"]) * np.exp(-d / s["rv"]) * np.exp(-cover_tau), 0, 1))


def wind_noise(U):
    """A-weighted vegetation noise (dBA) at local wind speed U: Bolin's log fit, floored for still air."""
    return max(QUIET_DB, WIND_DB0 + WIND_DB_LOG * np.log10(max(U, 0.05) / 5.1))


def level(L_src, d, d_foliage=0.0):
    return L_src - 20 * np.log10(max(d, 1.0)) - FOLIAGE_DB * d_foliage


def hearing(sp, L_src, d, d_foliage, U):
    return float(np.clip((level(L_src, d, d_foliage) - wind_noise(U) + SENSES[sp]["hear"]) / 10.0, 0, 1))


def sigmas(x):
    x = np.maximum(np.asarray(x, float), 0.0)
    return (SOURCE_SIGMA + 0.08 * x / np.sqrt(1 + 0.0001 * x), SOURCE_SIGMA + 0.06 * x / np.sqrt(1 + 0.0015 * x))


def plume(x, y, U):
    """Relative ground-level concentration x m downwind and y m across, wind speed U (reflected Gaussian)."""
    sy, sz = sigmas(x)
    c = np.exp(-0.5 * (y / sy) ** 2) * np.exp(-0.5 * (NOSE_H / sz) ** 2) / (np.maximum(U, 0.3) * sy * sz)
    return np.where(np.asarray(x) > 0, c, 0.0)


def smell(sp, x, y, U):
    """Salience of the plume at (x downwind, y across). Compared at equal wind (the plume's shape decides the
    range; a lighter wind does not let a squirrel smell farther), so U only matters through x and y."""
    ro = SENSES[sp]["ro"]
    if ro <= 0:
        return 0.0
    c = plume(x, y, U) / plume(ro, 0.0, U)
    return float(np.clip(1 + np.log(max(c, 1e-12)), 0, 1)) * SMELL_MAX


def combine(*s):
    return 1 - float(np.prod([1 - x for x in s]))


def fid(sp, v, cos_beta, sens=0.0, habit=0.0):
    s = SENSES[sp]
    return s["fid"] * (0.6 + 0.4 * min(v / WALK, 2.5)) * (0.7 + 0.3 * max(cos_beta, 0.0)) * np.exp(sens - habit)


@dataclass
class Mind:
    """One animal's running state toward the player."""
    sp: str
    alarm: float = 0.0
    habit: float = 0.0
    sens: float = 0.0
    state: str = "calm"           # calm | alert | flee | eat
    cues: dict = field(default_factory=dict)

    def step(self, dt, S, d, D):
        s = min(1.0, S * np.exp(self.sens - self.habit))
        rate = (s - self.alarm) / ALARM_RISE if s > self.alarm else -self.alarm / ALARM_TAU
        self.alarm = float(np.clip(self.alarm + dt * rate, 0, 1))
        prev = self.state
        if self.state == "flee":
            if self.alarm < A_ALERT and d > 1.5 * D:
                self.state = "calm"
        elif self.alarm >= A_FLEE or (self.alarm >= A_ALERT and d < D):
            self.state = "flee"
        elif self.alarm >= A_ALERT:
            self.state = "alert"
        elif self.state == "alert" and self.alarm < 0.5 * A_ALERT:
            self.state = "calm"
            self.habit = min(MEMORY_MAX, self.habit + HABIT_STEP)  # a look that came to nothing
        return prev != self.state

    def startle(self, amount):
        """A sudden threat (a clap, a charge): instant alarm and lasting sensitisation."""
        self.alarm = float(min(1.0, self.alarm + amount))
        self.sens = min(MEMORY_MAX, self.sens + SENSITISE_STEP * amount)

    def fed(self):
        self.habit = min(MEMORY_MAX, self.habit + FEED_STEP)


def to_json():
    return dict(WALK=WALK, A_ALERT=A_ALERT, A_FLEE=A_FLEE, ALARM_RISE=ALARM_RISE, ALARM_TAU=ALARM_TAU,
                FOLIAGE_DB=FOLIAGE_DB, CLAP_DB=CLAP_DB, WIND_DB0=WIND_DB0, WIND_DB_LOG=WIND_DB_LOG,
                QUIET_DB=QUIET_DB, STEP_DB=STEP_DB, GROUND_DB=GROUND_DB, POSTURE=POSTURE, SOURCE_SIGMA=SOURCE_SIGMA,
                NOSE_H=NOSE_H, COVER_K=COVER_K, SMELL_MAX=SMELL_MAX, SENSES=SENSES, HABIT_STEP=HABIT_STEP,
                SENSITISE_STEP=SENSITISE_STEP, FEED_STEP=FEED_STEP, MEMORY_MAX=MEMORY_MAX)

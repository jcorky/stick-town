"""Southern tree species as growth parameters.

Sizes are typical mature ranges in round numbers and should be checked against
USFS *Silvics of North America* (Agriculture Handbook 654, public domain) and
USDA PLANTS before being treated as reference data. The `verified` flag tracks
which entries have been checked; the next session is asked to do this.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Species:
    key: str
    common: str
    scientific: str
    height: tuple            # metres (min, max) mature
    dbh: tuple               # trunk diameter at breast height, metres
    crown: str               # envelope: spreading|round|conical|pine_open|columnar|layered|palm
    crown_base: float        # crown base as fraction of height
    crown_width: float       # crown diameter / height
    leader: float            # fraction of height the trunk leader persists (excurrent ≈ 0.9)
    leaf: str                # broadleaf|needle|scale_spray|palm
    leaf_size: float         # metres (blade length; needle length for pines)
    leaf_rgb: tuple
    bark_rgb: tuple
    deciduous: bool
    fall_rgb: tuple | None = None
    flare: float = 0.4       # root flare strength
    pipe_n: float = 2.3      # pipe-model exponent (da Vinci ≈ 2)
    tropism: float = 0.15    # upward bias of growth
    attract: int = 900       # attraction points (detail/complexity)
    moisture: tuple = (0.2, 0.8)   # preferred soil moisture window 0..1
    max_slope: float = 30.0
    provinces: tuple = ()
    moss: float = 0.0        # Spanish moss tendency (Tillandsia usneoides)
    knees: bool = False
    verified: bool = False
    notes: str = ""
    flowers: dict = field(default_factory=dict)


ALL = "coastal_plain floodplain piedmont cumberland_plateau ridge_and_valley".split()

SPECIES: dict[str, Species] = {s.key: s for s in [
    Species("live_oak", "Southern live oak", "Quercus virginiana", (12, 22), (0.8, 1.8),
            "spreading", 0.12, 1.9, 0.18, "broadleaf", 0.07, (0.20, 0.32, 0.13), (0.30, 0.27, 0.24),
            False, flare=0.9, tropism=-0.02, attract=1400, moisture=(0.3, 0.8), max_slope=15,
            provinces=("coastal_plain", "floodplain"), moss=0.9,
            notes="Low, sprawling limbs that may touch the ground; evergreen."),
    Species("loblolly_pine", "Loblolly pine", "Pinus taeda", (25, 33), (0.4, 0.8),
            "pine_open", 0.6, 0.35, 0.95, "needle", 0.18, (0.22, 0.36, 0.14), (0.36, 0.24, 0.18),
            False, flare=0.25, tropism=0.25, attract=1300, moisture=(0.25, 0.75),
            provinces=("coastal_plain", "piedmont", "floodplain", "cumberland_plateau"),
            notes="Self-prunes; tall clear bole; plated reddish bark; needles in 3s."),
    Species("longleaf_pine", "Longleaf pine", "Pinus palustris", (24, 32), (0.4, 0.75),
            "pine_open", 0.68, 0.32, 0.95, "needle", 0.32, (0.24, 0.38, 0.15), (0.40, 0.28, 0.20),
            False, flare=0.2, tropism=0.25, attract=900, moisture=(0.05, 0.45),
            provinces=("coastal_plain", "piedmont"),
            notes="Sparse open crown, very long needles in tufts; fire-maintained savanna."),
    Species("bald_cypress", "Bald cypress", "Taxodium distichum", (24, 36), (0.9, 1.8),
            "conical", 0.35, 0.45, 0.85, "scale_spray", 0.012, (0.30, 0.42, 0.18), (0.48, 0.38, 0.32),
            True, fall_rgb=(0.62, 0.30, 0.12), flare=1.8, attract=800, moisture=(0.75, 1.0),
            provinces=("coastal_plain", "floodplain"), moss=0.8, knees=True,
            notes="Buttressed base, knees in standing water; deciduous conifer."),
    Species("southern_magnolia", "Southern magnolia", "Magnolia grandiflora", (15, 24), (0.4, 0.9),
            "conical", 0.08, 0.55, 0.7, "broadleaf", 0.17, (0.12, 0.26, 0.09), (0.45, 0.45, 0.42),
            False, flare=0.3, attract=1100, moisture=(0.35, 0.8), provinces=tuple(ALL),
            flowers={"rgb": (0.95, 0.94, 0.88), "size": 0.22, "season": "summer"},
            notes="Dense pyramidal crown to the ground; big glossy leaves."),
    Species("sweetgum", "Sweetgum", "Liquidambar styraciflua", (18, 30), (0.4, 0.9),
            "conical", 0.35, 0.5, 0.75, "broadleaf", 0.13, (0.25, 0.42, 0.15), (0.38, 0.34, 0.30),
            True, fall_rgb=(0.55, 0.12, 0.18), attract=900, moisture=(0.35, 0.9), provinces=tuple(ALL),
            notes="Star leaves; mixed red/purple/yellow fall colour; gumballs on ground."),
    Species("tulip_poplar", "Tulip poplar", "Liriodendron tulipifera", (27, 38), (0.6, 1.2),
            "columnar", 0.45, 0.35, 0.9, "broadleaf", 0.13, (0.28, 0.45, 0.16), (0.42, 0.40, 0.36),
            True, fall_rgb=(0.80, 0.65, 0.18), tropism=0.3, attract=900, moisture=(0.45, 0.85),
            provinces=("piedmont", "cumberland_plateau", "ridge_and_valley"),
            notes="Arrow-straight trunk; coves and moist slopes."),
    Species("white_oak", "White oak", "Quercus alba", (20, 30), (0.6, 1.2),
            "round", 0.35, 0.9, 0.5, "broadleaf", 0.15, (0.22, 0.36, 0.14), (0.55, 0.53, 0.49),
            True, fall_rgb=(0.50, 0.22, 0.14), attract=1100, moisture=(0.25, 0.7),
            provinces=("piedmont", "cumberland_plateau", "ridge_and_valley"),
            notes="Pale flaky bark; wide crown in the open; acorn mast."),
    Species("water_oak", "Water oak", "Quercus nigra", (15, 24), (0.4, 0.9),
            "round", 0.3, 0.8, 0.5, "broadleaf", 0.08, (0.20, 0.34, 0.13), (0.30, 0.29, 0.27),
            True, fall_rgb=(0.45, 0.38, 0.18), attract=1000, moisture=(0.5, 0.95),
            provinces=("coastal_plain", "floodplain", "piedmont"), moss=0.4,
            notes="Common street and bottomland oak; spatulate leaves."),
    Species("flowering_dogwood", "Flowering dogwood", "Cornus florida", (5, 9), (0.12, 0.25),
            "layered", 0.25, 1.1, 0.3, "broadleaf", 0.09, (0.26, 0.42, 0.16), (0.32, 0.28, 0.25),
            True, fall_rgb=(0.55, 0.10, 0.12), tropism=-0.05, attract=600, moisture=(0.3, 0.75),
            provinces=tuple(ALL), flowers={"rgb": (0.97, 0.96, 0.92), "size": 0.09, "season": "spring"},
            notes="Understory; horizontal tiers; white bracts in spring."),
    Species("eastern_redbud", "Eastern redbud", "Cercis canadensis", (6, 9), (0.12, 0.25),
            "round", 0.3, 1.1, 0.3, "broadleaf", 0.10, (0.25, 0.42, 0.15), (0.28, 0.25, 0.24),
            True, fall_rgb=(0.80, 0.70, 0.20), attract=550, moisture=(0.2, 0.7), provinces=tuple(ALL),
            flowers={"rgb": (0.78, 0.36, 0.62), "size": 0.04, "season": "spring"},
            notes="Heart-shaped leaves; magenta bloom on bare wood in early spring."),
    Species("sabal_palmetto", "Cabbage palmetto", "Sabal palmetto", (10, 18), (0.3, 0.45),
            "palm", 1.0, 0.35, 1.0, "palm", 1.6, (0.24, 0.38, 0.18), (0.46, 0.42, 0.36),
            False, attract=0, moisture=(0.3, 0.9), max_slope=10, provinces=("coastal_plain",),
            notes="Gulf/Atlantic coast; boots of old leaf bases on trunk."),
]}


SEASON_TINT = {"spring": 1.08, "summer": 1.0, "fall": 0.95, "winter": 0.9}

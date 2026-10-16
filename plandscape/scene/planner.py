"""Prompt → ScenePlan.

A deterministic keyword planner so the system works offline and reproducibly.
`refine` is the hook for an LLM pass (e.g. Claude) that rewrites a free-form
prompt into the same JSON schema; the planner then validates it. The plan is
the single source of truth for composition, so it's saved next to every output.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from ..rng import derive_seed

REGIONS = [
    (("monte sano", "huntsville", "cumberland", "plateau", "sequatchie", "lookout mountain"), "cumberland_plateau"),
    (("delta", "mississippi river", "bayou", "atchafalaya", "floodplain", "bottomland", "river bottom"), "floodplain"),
    (("smoky", "appalachian", "blue ridge", "ridge and valley", "chattanooga", "birmingham", "mountain"), "ridge_and_valley"),
    (("piedmont", "atlanta", "charlotte", "greenville", "red clay", "athens"), "piedmont"),
    (("mobile", "gulf", "coast", "low country", "lowcountry", "savannah", "charleston", "panhandle",
      "pensacola", "tallahassee", "coastal", "beach", "marsh"), "coastal_plain"),
]

BIOMES = {
    "pine_savanna": ("longleaf", "savanna", "pine flat", "wiregrass", "pine barren"),
    "swamp": ("swamp", "cypress", "bayou", "slough", "tupelo"),
    "hardwood": ("hardwood", "oak-hickory", "forest", "woods", "cove", "hollow", "holler"),
    "pasture": ("pasture", "field", "farm", "hay", "cattle"),
    "old_field": ("old field", "abandoned", "overgrown", "broomsedge"),
    "lawn": ("yard", "lawn", "neighborhood", "neighbourhood", "town", "porch", "suburb", "park"),
    "pine_plantation": ("loblolly", "pine plantation", "pine stand", "timber"),
}

BIOME_TREES = {
    "pine_savanna": {"longleaf_pine": 0.75, "live_oak": 0.05, "sabal_palmetto": 0.05, "flowering_dogwood": 0.05, "water_oak": 0.1},
    "pine_plantation": {"loblolly_pine": 0.85, "sweetgum": 0.1, "eastern_redbud": 0.05},
    "swamp": {"bald_cypress": 0.6, "water_oak": 0.2, "sweetgum": 0.1, "live_oak": 0.1},
    "hardwood": {"white_oak": 0.25, "tulip_poplar": 0.2, "sweetgum": 0.15, "water_oak": 0.1,
                 "flowering_dogwood": 0.15, "eastern_redbud": 0.1, "loblolly_pine": 0.05},
    "pasture": {"live_oak": 0.3, "water_oak": 0.3, "sweetgum": 0.2, "loblolly_pine": 0.2},
    "old_field": {"loblolly_pine": 0.4, "sweetgum": 0.3, "eastern_redbud": 0.15, "water_oak": 0.15},
    "lawn": {"live_oak": 0.25, "southern_magnolia": 0.2, "water_oak": 0.2, "flowering_dogwood": 0.15,
             "eastern_redbud": 0.1, "loblolly_pine": 0.1},
}

BIOME_DENSITY = {"pine_savanna": 0.25, "pine_plantation": 0.7, "swamp": 0.6, "hardwood": 0.8,
                 "pasture": 0.08, "old_field": 0.3, "lawn": 0.12}

BUILDINGS = {"shotgun": "shotgun", "dogtrot": "dogtrot", "barn": "barn", "church": "church",
             "farmhouse": "farmhouse", "farm house": "farmhouse", "house": "farmhouse", "cabin": "dogtrot"}

FAUNA_WORDS = {"deer": "white_tailed_deer", "squirrel": "gray_squirrel", "turkey": "wild_turkey",
               "armadillo": "armadillo", "coyote": "coyote", "people": "human", "person": "human",
               "kids": "human", "walker": "human", "hiker": "human"}

TIMES = {"dawn": 6.3, "sunrise": 6.5, "morning": 8.5, "noon": 12.5, "midday": 12.5, "afternoon": 15.5,
         "golden hour": 18.6, "dusk": 19.2, "sunset": 19.0, "evening": 19.5, "twilight": 19.6, "night": 22.5,
         "midnight": 0.5}

SEASONS = {"spring": "spring", "summer": "summer", "fall": "fall", "autumn": "fall", "winter": "winter",
           "april": "spring", "july": "summer", "october": "fall", "december": "winter"}


@dataclass
class ScenePlan:
    prompt: str
    seed: int
    province: str = "piedmont"
    biome: str = "hardwood"
    trees: dict = field(default_factory=dict)
    tree_density: float = 0.5
    buildings: list = field(default_factory=list)
    paths: bool = True
    creek: bool = True
    fauna: dict = field(default_factory=dict)
    hour: float = 9.0
    season: str = "summer"
    size_m: float = 128.0
    res_m: float = 1.0
    detail: str = "low"
    notes: list = field(default_factory=list)

    def to_json(self):
        return json.dumps(asdict(self), indent=2)


def _has(text, words):
    return any(re.search(r"\b" + re.escape(w) + r"s?\b", text) for w in words)


def plan(prompt: str, seed: int | None = None, size_m: float = 128.0, detail: str = "low") -> ScenePlan:
    t = prompt.lower()
    seed = derive_seed("prompt", prompt) % 1_000_000 if seed is None else seed
    p = ScenePlan(prompt=prompt, seed=seed, size_m=size_m, detail=detail)
    for words, prov in REGIONS:
        if _has(t, words):
            p.province = prov
            p.notes.append(f"region→{prov}")
            break
    biome = None
    for b, words in BIOMES.items():
        if _has(t, words):
            biome = b
            break
    if biome is None:
        biome = {"floodplain": "swamp", "coastal_plain": "pine_savanna", "piedmont": "hardwood",
                 "cumberland_plateau": "hardwood", "ridge_and_valley": "hardwood"}[p.province]
        p.notes.append(f"biome defaulted from province→{biome}")
    p.biome = biome
    p.trees = dict(BIOME_TREES[biome])
    # explicitly named species get boosted
    from ..flora.species import SPECIES
    for key, sp in SPECIES.items():
        names = {sp.common.lower(), key.replace("_", " "), sp.common.lower().split()[-1]}
        if any(n in t for n in names if len(n) > 3):
            p.trees[key] = p.trees.get(key, 0) + 0.6
    s = sum(p.trees.values())
    p.trees = {k: round(v / s, 3) for k, v in p.trees.items()}
    p.tree_density = BIOME_DENSITY[biome]
    if _has(t, ("dense", "thick", "deep")):
        p.tree_density = min(1.0, p.tree_density * 1.6)
    if _has(t, ("sparse", "open", "clearing", "few trees")):
        p.tree_density *= 0.5
    for w, k in BUILDINGS.items():
        if w == "house" and p.buildings:
            continue  # "shotgun house" is one building, not two
        if _has(t, (w,)) and k not in p.buildings:
            p.buildings.append(k)
    if biome == "lawn" and not p.buildings:
        p.buildings.append("farmhouse")
    p.paths = not _has(t, ("pristine", "untouched", "no path"))
    p.creek = not _has(t, ("dry", "no creek", "drought"))
    for w, k in FAUNA_WORDS.items():
        m = re.search(r"(\d+|a few|several|a|an|one|two|three|four|five|six)?\s*" + w + r"(\s+(?:flock|herd|family|group|pack))?", t)
        if m:
            q = m.group(1) or "a few"
            if m.group(2):  # "a turkey flock" is a group, not one bird
                q = "several"
            n = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "a few": 3, "several": 5}.get(q, None) or int(q)
            p.fauna[k] = p.fauna.get(k, 0) + n
    if not p.fauna and not _has(t, ("empty", "no animals", "lifeless")):
        p.fauna = {"gray_squirrel": 3, "white_tailed_deer": 2}
        if p.buildings or p.paths:
            p.fauna["human"] = 1
        p.notes.append("no animals named → default squirrels/deer so the place feels alive")
    for w, h in TIMES.items():
        if _has(t, (w,)):
            p.hour = h
            break
    for w, s_ in SEASONS.items():
        if _has(t, (w,)):
            p.season = s_
            break
    return p


def refine(prompt: str, llm=None) -> ScenePlan:
    """Optional LLM pass: `llm(prompt, schema_json) -> dict`; falls back to `plan`."""
    base = plan(prompt)
    if llm is None:
        return base
    data = llm(prompt, base.to_json())
    for k, v in (data or {}).items():
        if hasattr(base, k):
            setattr(base, k, v)
    return base

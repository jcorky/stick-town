"""Prompt → ScenePlan.

A deterministic keyword planner so the system works offline and reproducibly.
`refine` adds an optional LLM pass (`claude_llm`, Anthropic Messages API over urllib) that fills the same
schema from a free-form prompt; `validate` keeps only values the generators can honour, with the keyword plan
as fallback and baseline. See docs/TECHNIQUES.md §27. The plan is
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
      "pensacola", "tallahassee", "coastal", "beach", "marsh", "black belt", "prairie"), "coastal_plain"),
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

# where a biome lives when the prompt names no region (longleaf savanna is Coastal Plain; cypress swamp, floodplain)
BIOME_PROVINCE = {"pine_savanna": "coastal_plain", "swamp": "floodplain"}

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
               "kids": "human", "walker": "human", "hiker": "human", "raccoon": "raccoon",
               "box turtle": "box_turtle", "turtle": "box_turtle", "heron": "great_blue_heron"}

TIMES = {"dawn": 6.3, "sunrise": 6.5, "morning": 8.5, "noon": 12.5, "midday": 12.5, "afternoon": 15.5,
         "golden hour": 18.6, "dusk": 19.2, "sunset": 19.0, "evening": 19.5, "twilight": 19.6, "night": 22.5,
         "midnight": 0.5}

# wind words → Beaufort force; directions → where the wind blows FROM (degrees clockwise from north)
WIND_WORDS = {"dead calm": 0, "calm": 1, "still": 1, "light air": 1, "light breeze": 2, "breeze": 3, "breezy": 4,
              "gentle breeze": 3, "fresh breeze": 5, "gusty": 5, "windy": 6, "blustery": 6, "strong wind": 7,
              "gale": 8, "storm": 9, "stormy": 9, "thunderstorm": 9, "hurricane": 12}
WIND_DIRS = {"north": 0, "northeast": 45, "east": 90, "southeast": 135, "south": 180, "southwest": 225,
             "west": 270, "northwest": 315}
# design defaults: the Gulf's southerlies in the warm months, fronts from the northwest in winter
WIND_SEASON = {"spring": 200.0, "summer": 180.0, "fall": 45.0, "winter": 315.0}

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
    wind_force: float = 3.0      # Beaufort (TECHNIQUES §34)
    wind_from: float = -1.0      # degrees clockwise from north it blows from; < 0 means the season's default
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
    biome, best = None, 0  # the longest matching phrase wins: "old field" over "field", "pine plantation" over "pine"
    for b, words in BIOMES.items():
        for w_ in words:
            if len(w_) > best and _has(t, (w_,)):
                biome, best = b, len(w_)
    if biome is None:
        biome = {"floodplain": "swamp", "coastal_plain": "pine_savanna", "piedmont": "hardwood",
                 "cumberland_plateau": "hardwood", "ridge_and_valley": "hardwood"}[p.province]
        p.notes.append(f"biome defaulted from province→{biome}")
    p.biome = biome
    if not any(n.startswith("region→") for n in p.notes) and biome in BIOME_PROVINCE:  # savannas are coastal
        p.province = BIOME_PROVINCE[biome]
        p.notes.append(f"province from biome→{p.province}")
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
    tf = t  # matched phrases are blanked out so "box turtle" is not counted again as "turtle"
    for w in sorted(FAUNA_WORDS, key=len, reverse=True):
        k = FAUNA_WORDS[w]
        m = re.search(r"(\d+|a few|several|a|an|one|two|three|four|five|six)?\s*" + w + r"(\s+(?:flock|herd|family|group|pack))?", tf)
        if m:
            tf = tf[:m.start()] + " " * (m.end() - m.start()) + tf[m.end():]
            q = m.group(1) or "a few"
            if m.group(2):  # "a turkey flock" is a group, not one bird
                q = "several"
            n = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "a few": 3, "several": 5}.get(q, None) or int(q)
            p.fauna[k] = p.fauna.get(k, 0) + n
    order = list(dict.fromkeys(FAUNA_WORDS.values()))  # keep the table's species order (agent ids stay stable)
    p.fauna = {k: p.fauna[k] for k in order if k in p.fauna}
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
    for w in sorted(WIND_WORDS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(w) + r"\b", t):
            p.wind_force = float(WIND_WORDS[w])
            p.notes.append(f"wind→Beaufort {WIND_WORDS[w]}")
            break
    for w in sorted(WIND_DIRS, key=len, reverse=True):  # "north wind", "from the southwest", "a westerly"
        if re.search(r"\b(?:" + w + r"(?:ern|erly)?\s+(?:wind|breeze|gale)|from\s+the\s+" + w + r"|" + w + r"erly)\b", t):
            p.wind_from = float(WIND_DIRS[w])
            break
    if p.wind_from < 0:
        p.wind_from = WIND_SEASON[p.season]
    return p


SEASON_SET = ("spring", "summer", "fall", "winter")
BUILDING_KINDS = tuple(sorted(set(BUILDINGS.values())))
MAX_BUILDINGS, MAX_PER_SPECIES = 4, 12


def validate(data: dict, base: ScenePlan) -> ScenePlan:
    """Merge an LLM's plan into `base`, keeping only values the generators can honour.

    Every field is checked against the real vocabularies (provinces, biomes, species, building kinds, fauna,
    seasons) and ranges; a rejected value keeps the keyword planner's and is noted in `notes`. The seed, size,
    resolution and detail never come from the LLM, so a scene stays reproducible from its prompt."""
    from ..fauna.agents import FAUNA
    from ..flora.species import SPECIES
    from ..terrain.heightfield import PROVINCES
    p = ScenePlan(**asdict(base))
    p.notes = list(base.notes)

    def reject(k, v):
        p.notes.append(f"refine: kept planner value for {k} (got {v!r})")

    def num(v):  # a JSON number (bools are ints in Python, not here)
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def word(v, allowed):
        return isinstance(v, str) and v in allowed
    for k, v in (data or {}).items():
        if k in ("prompt", "seed", "size_m", "res_m", "detail", "notes"):
            continue
        if k == "province":
            p.province = v if word(v, PROVINCES) else (reject(k, v) or p.province)
        elif k == "biome":
            p.biome = v if word(v, BIOMES) else (reject(k, v) or p.biome)
        elif k == "trees":
            ok = isinstance(v, dict) and v and all(word(s_, SPECIES) and num(w) and w > 0 for s_, w in v.items())
            if ok:
                tot = float(sum(v.values()))
                p.trees = {s_: round(w / tot, 3) for s_, w in v.items()}
            else:
                reject(k, v)
        elif k == "tree_density":
            p.tree_density = float(v) if num(v) and 0 <= v <= 1 else (reject(k, v) or p.tree_density)
        elif k == "buildings":
            if isinstance(v, list) and all(word(b, BUILDING_KINDS) for b in v) and len(v) <= MAX_BUILDINGS:
                p.buildings = list(v)
            else:
                reject(k, v)
        elif k in ("paths", "creek"):
            setattr(p, k, v) if isinstance(v, bool) else reject(k, v)
        elif k == "fauna":
            ok = isinstance(v, dict) and all(word(a, FAUNA) and num(n) and int(n) == n and 0 <= n <= MAX_PER_SPECIES
                                             for a, n in v.items())
            if ok:
                p.fauna = {a: int(n) for a, n in v.items() if n > 0}
            else:
                reject(k, v)
        elif k == "hour":
            p.hour = float(v) % 24 if num(v) and 0 <= v <= 24 else (reject(k, v) or p.hour)
        elif k == "season":
            p.season = v if word(v, SEASON_SET) else (reject(k, v) or p.season)
        elif k == "wind_force":
            p.wind_force = float(v) if num(v) and 0 <= v <= 12 else (reject(k, v) or p.wind_force)
        elif k == "wind_from":
            p.wind_from = float(v) % 360 if num(v) and 0 <= v <= 360 else (reject(k, v) or p.wind_from)
        else:
            p.notes.append(f"refine: ignored unknown field {k}")
    if p.biome != base.biome and set(p.trees) == set(base.trees):  # a new biome with the old mix: use its own
        p.trees = dict(BIOME_TREES[p.biome])
    p.notes.append("refined by LLM")
    return p


def refine(prompt: str, llm=None, seed: int | None = None, size_m: float = 128.0, detail: str = "low") -> ScenePlan:
    """Optional LLM pass: `llm(prompt, schema_json) -> dict`. The keyword plan is the fallback and the
    validator's baseline; any failure (no key, network, bad JSON) returns it unchanged with a note."""
    base = plan(prompt, seed=seed, size_m=size_m, detail=detail)
    if llm is None:
        return base
    try:
        data = llm(prompt, schema_json())
    except Exception as e:  # noqa: BLE001  (offline must always work)
        base.notes.append(f"refine: LLM unavailable ({type(e).__name__}); keyword plan used")
        return base
    if not isinstance(data, dict):
        base.notes.append("refine: LLM returned no JSON object; keyword plan used")
        return base
    return validate(data, base)


def schema_json() -> str:
    """The fields an LLM may set, with their allowed values (sent as the contract)."""
    from ..fauna.agents import FAUNA
    from ..flora.species import SPECIES
    from ..terrain.heightfield import PROVINCES
    return json.dumps({
        "province": sorted(PROVINCES), "biome": sorted(BIOMES),
        "trees": {"<species>": "relative weight > 0", "species": sorted(SPECIES)},
        "tree_density": "0..1", "buildings": f"list (≤{MAX_BUILDINGS}) of {list(BUILDING_KINDS)}",
        "paths": "bool", "creek": "bool",
        "fauna": {"<animal>": f"count 0..{MAX_PER_SPECIES}", "animals": sorted(FAUNA)},
        "hour": "0..24 local solar time", "season": list(SEASON_SET),
        "wind_force": "Beaufort 0..12", "wind_from": "degrees clockwise from north the wind blows from"}, indent=1)


DEFAULT_MODEL = "claude-opus-5-5"


def claude_llm(model: str | None = None, api_key: str | None = None, timeout: float = 60.0):
    """An `llm` for `refine` that calls the Anthropic Messages API with the standard library only.
    Key from ANTHROPIC_API_KEY, model from PLANDSCAPE_MODEL (default the newest Claude)."""
    import os
    import urllib.request
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    model = model or os.environ.get("PLANDSCAPE_MODEL", DEFAULT_MODEL)

    def call(prompt, schema):
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        system = ("You turn a description of a place in the American South into a JSON scene plan for a "
                  "procedural landscape generator. Answer with one JSON object only, using only these fields "
                  "and allowed values:\n" + schema + "\nOmit fields the description does not imply.")
        body = json.dumps({"model": model, "max_tokens": 800, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
                                     headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                              "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            msg = json.loads(r.read())
        text = "".join(c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text")
        return extract_json(text)
    return call


def extract_json(text: str):
    """The first balanced {...} object in `text`, parsed; None if there isn't one."""
    start = text.find("{")
    while start >= 0:
        depth = 0
        for i in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break
        start = text.find("{", start + 1)
    return None

"""Place names for a scene: the road, the creek, each homestead, the church.

Names are invented, never claimed to be real places. They follow the patterns Southern places are actually
named by (a family, a landform, a mill or ford, a church's congregation) instead of a syllable Markov chain
(Fantasy-Map-Generator's approach; its name bases are European/fantasy). Every choice is keyed, so a scene
always gets the same names. See docs/TECHNIQUES.md §19.
"""

from __future__ import annotations

from ..rng import rng as make_rng

SURNAMES = ["Abernathy", "Aldridge", "Bankhead", "Blevins", "Boatwright", "Burkhalter", "Caldwell", "Cantrell",
            "Crutcher", "Dabney", "Dorsey", "Easley", "Fite", "Gentry", "Goforth", "Hargrove", "Hollingsworth",
            "Hurt", "Jernigan", "Kilgore", "Lackey", "Ledbetter", "Lovelady", "Mabry", "McCrary", "Moody",
            "Nesbitt", "Oakes", "Pettus", "Pruitt", "Rakestraw", "Renfroe", "Sanders", "Shackelford", "Stallings",
            "Tidwell", "Tubb", "Vaughn", "Wardlaw", "Whitlow", "Womack", "Yarbrough"]

# landform and water words by province: the same creek is a "Branch" in the hills and a "Slough" in the Delta
LAND = {
    "cumberland_plateau": dict(water=["Branch", "Creek", "Fork"], land=["Gap", "Cove", "Bluff", "Hollow", "Mountain"]),
    "ridge_and_valley": dict(water=["Creek", "Branch", "Run"], land=["Gap", "Ridge", "Valley", "Knob"]),
    "piedmont": dict(water=["Creek", "Branch", "Shoals"], land=["Mill", "Ford", "Grove", "Hill"]),
    "coastal_plain": dict(water=["Creek", "Branch", "Swamp"], land=["Landing", "Savanna", "Pond", "Pines"]),
    "floodplain": dict(water=["Bayou", "Slough", "Bayou"], land=["Bend", "Ferry", "Landing", "Lake"]),
}
NATURE = ["Cedar", "Sugar", "Laurel", "Mulberry", "Persimmon", "Turkey", "Panther", "Beaver", "Possum", "Spring",
          "Sulphur", "Rocky", "Muddy", "Big", "Little", "Cane", "Hickory", "Chestnut", "Poplar", "Dry"]
CHURCH_NAME = ["Pleasant Hill", "Mount Zion", "New Hope", "Shiloh", "Bethel", "Mount Pisgah", "Antioch", "Ebenezer",
               "Salem", "Liberty", "Pleasant Grove", "Macedonia"]
CHURCH_KIND = ["Baptist", "Methodist", "Missionary Baptist", "Primitive Baptist", "A.M.E.", "Church of Christ"]


def scene_names(plan, n_houses=0, has_creek=True):
    r = make_rng("names", plan.seed, plan.province)
    words = LAND.get(plan.province, LAND["piedmont"])
    pick = lambda xs: xs[int(r.integers(0, len(xs)))]  # noqa: E731
    families = list(r.choice(SURNAMES, size=max(n_houses, 1) + 1, replace=False))
    creek = f"{pick(NATURE + families)} {pick(words['water'])}" if has_creek else None
    church = f"{pick(CHURCH_NAME)} {pick(CHURCH_KIND)} Church"
    road_kind = int(r.integers(0, 5))
    road = [f"{families[-1]} Rd", f"{pick(NATURE)} {pick(words['land'])} Rd",
            f"{church.split(' Church')[0].rsplit(' ', 1)[0]} Church Rd", f"Old {pick(words['land'])} Rd",
            f"{creek.split(' ')[0] if creek else pick(NATURE)} {pick(words['water'])} Rd"][road_kind]
    homes = [f"the {f} place" for f in families[:n_houses]]
    return dict(road=road, creek=creek, church=church, homesteads=homes)


def site_scores(hf, road, nrm, setback, footprint_r=6.0):
    """Suitability of a house site at each road point (after FMG's settlement score, rewritten for a 1 m tile):
        s = −mean slope / 6 − 6 · water within the plot − 2 · |height above road − 1 m| + creek bonus
    where the creek bonus is 1.5 · exp(−((d_creek − 30)/20)²): close enough to fetch water, out of its flood."""
    import numpy as np
    from scipy import ndimage
    slope = hf.layers["slope"]
    water = hf.layers["water"]
    d_water = ndimage.distance_transform_edt(water < 0.5) * hf.res
    sites = road + nrm * setback
    out = np.empty(len(road))
    for k, (x, y) in enumerate(sites):
        gx, gy = hf.to_grid(x, y)
        i0, i1 = int(max(gy - footprint_r, 0)), int(min(gy + footprint_r + 1, slope.shape[0]))
        j0, j1 = int(max(gx - footprint_r, 0)), int(min(gx + footprint_r + 1, slope.shape[1]))
        if i1 <= i0 or j1 <= j0:
            out[k] = -1e9
            continue
        s = -slope[i0:i1, j0:j1].mean() / 6 - 6 * water[i0:i1, j0:j1].max()
        rise = float(hf.sample(x, y)[0] - hf.sample(*road[k])[0])
        s -= 2 * abs(rise - 1.0)
        dw = d_water[int(np.clip(round(gy), 0, slope.shape[0] - 1)), int(np.clip(round(gx), 0, slope.shape[1] - 1))]
        s += 1.5 * np.exp(-((dw - 30) / 20) ** 2) if water.any() else 0
        out[k] = s
    return out

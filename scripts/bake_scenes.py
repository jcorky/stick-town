"""Compose a spread of scenes into the asset library (behaviour clips, terrains, impostors), checking each one.

  python3 scripts/bake_scenes.py [--out out/bake] [--only N]

No review renders: compose only, ~15 s a scene. Prints one line per scene (GLB size must stay under 15 MB) and
writes out/bake/summary.json. Prompts span every province, biome, season, time of day and wind.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROMPTS = [
    "Monte Sano hardwood cove with a dogtrot cabin, a creek, two deer and three squirrels at dawn in spring",
    "Huntsville ridge hardwoods in winter with a church, a coyote and a few deer at dusk, windy",
    "Cumberland Plateau bluff with tulip poplars, a barn, a turkey flock at noon in summer, calm",
    "ridge and valley pasture with a farmhouse, a barn, two deer and a hiker in the morning in fall",
    "ridge and valley hardwood hollow at night in summer with raccoons and an armadillo",
    "Piedmont old field with loblolly pines, a shotgun house, kids and a dog-trot cabin in the afternoon in spring, breezy",
    "Piedmont red clay pasture with live oaks, a farmhouse and a few deer at golden hour in winter, a north wind",
    "Piedmont hardwood creek with a heron, a box turtle and squirrels in the morning in summer",
    "Georgia piedmont pine plantation with a turkey flock and a coyote at dusk in fall, gusty",
    "longleaf pine savanna near Mobile at dawn in spring with a few deer and a box turtle",
    "longleaf savanna with a church and two hikers at noon in winter, from the northwest",
    "coastal plain lawn with a farmhouse, live oaks and Spanish moss, squirrels and people in the evening in summer",
    "coastal plain old field with sweetgums, an armadillo and a raccoon at night in fall",
    "Gulf coast pine savanna with a heron and deer at sunset in summer, a south wind",
    "cypress bayou floodplain with a shotgun house, a heron and a raccoon at dawn in winter",
    "Delta floodplain swamp with bald cypress, a box turtle, an armadillo and a heron at noon in spring, calm",
    "bottomland hardwoods on the floodplain with a turkey flock and two deer in the afternoon in fall",
    "Mississippi Delta cotton country pasture with a barn, a farmhouse and a coyote at twilight in summer, windy",
    "Black Belt prairie pasture with a church, a hiker and deer in the morning in winter",
    "pristine hardwood forest with no path, three squirrels and a deer at midday in fall, a gale",
]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/bake")
    ap.add_argument("--only", type=int, default=None)
    ap.add_argument("--sim", type=float, default=120.0)
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from plandscape.scene.compose import compose
    from plandscape.scene.planner import plan
    rows = []
    for i, prompt in enumerate(PROMPTS if a.only is None else PROMPTS[a.only:a.only + 1]):
        d = os.path.join(a.out, f"s{i:02d}")
        os.makedirs(d, exist_ok=True)
        t = time.time()
        p = plan(prompt)
        r = compose(p, d, sim_seconds=a.sim, log=lambda *x: None)
        st = r["stats"]
        row = dict(prompt=prompt, province=p.province, biome=p.biome, season=p.season, hour=p.hour,
                   wind=p.wind_force, fauna=p.fauna, glb_mb=st["glb_mb"], trees=st["trees"], agents=st["agents"],
                   seconds=round(time.time() - t, 1), hits=st["library"]["session_hits"],
                   misses=st["library"]["session_misses"])
        rows.append(row)
        ok = "ok" if st["glb_mb"] < 15 else "OVER 15 MB"
        print(f"{i:2d} {ok:10s} {st['glb_mb']:5.2f} MB {p.province:18s} {p.biome:15s} {p.season:6s} "
              f"{p.hour:4.1f}h B{p.wind_force:g} {st['agents']:2d} animals {row['seconds']:5.1f}s  {prompt[:60]}",
              flush=True)
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()

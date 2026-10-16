"""Asset library CLI.

  python -m plandscape.assets stats
  python -m plandscape.assets bake --variants 3 --detail low --seasons summer fall
  python -m plandscape.assets find tree species=live_oak season=fall
  python -m plandscape.assets bake-models                 # import Poly Haven props (needs network once)
  python -m plandscape.assets prune                       # drop entries from superseded generator versions
"""

from __future__ import annotations

import argparse
import json
import os
import time

from ..fauna.agents import FAUNA
from ..fauna.bodies import body
from ..flora.species import SPECIES
from ..flora.tree import generate_tree
from .. import models, textures
from ..scene.buildings import generate_building
from .store import GENERATOR_VERSIONS, AssetStore, mesh_codec, tree_codec


DERIVED = {"behavior": "terrain", "impostor": "tree"}  # kind → the upstream generator its params must name


def prune(store):
    """Delete entries whose generator version is no longer current (they can never be hit again), and
    derived entries built on a superseded upstream: a param named after a kind whose value is a version string
    of that kind (behaviour clips carry terrain="terrain-…", impostors tree="tree-…") must still be current."""
    keep, gone = {}, 0
    for k, e in store.entries.items():
        if DERIVED.get(e.kind) and DERIVED[e.kind] not in e.params:  # made before they recorded their upstream
            stale_up = True
        else:
            stale_up = any(isinstance(v, str) and q in GENERATOR_VERSIONS and v.startswith(f"{q}-")
                           and v != GENERATOR_VERSIONS[q] for q, v in e.params.items())
        if e.version == GENERATOR_VERSIONS.get(e.kind) and not stale_up:
            keep[k] = e
            continue
        gone += 1
        for ext in (".npz", ".json", ".glb"):
            f = os.path.join(store.root, os.path.splitext(e.path)[0] + ext)
            if os.path.exists(f):
                os.remove(f)
    with open(store.index_path, "w") as f:
        for e in keep.values():
            f.write(json.dumps(e.__dict__) + "\n")
    store.entries = keep
    print(f"pruned {gone} superseded entries")


def bake(store, variants, detail, seasons, moistures=(0.5, 0.8)):
    enc, dec = tree_codec()
    n0 = time.time()
    keys = {textures.leaf_key(k) for k in SPECIES} | {textures.bark_key(k) for k in SPECIES} | \
        {textures.ground_key(b) for b in textures.GROUND_SET} | {textures.needle_key()} | \
        {k for b in textures.GROUND_SET for p in (None, *textures.SPLAT_SET["soil"]) for k in textures.splat_keys(b, p)} | \
        {"ground/Gravel023"}
    for key in sorted(keys):
        textures.get(key, store)
    for sp in SPECIES:
        for season in seasons:
            for v in range(variants):
                for m in moistures:
                    params = dict(species=sp, seed=[0, v], season=season, detail=detail, moisture=m)
                    store.get_or_build("tree", params,
                                       lambda: generate_tree(sp, seed=(0, v), season=season, detail=detail, moisture=m),
                                       enc, dec)
    benc, bdec = mesh_codec("building")
    for kind in ("shotgun", "dogtrot", "barn", "farmhouse", "church"):
        for v in range(variants):
            store.get_or_build("building", dict(kind=kind, seed=[0, v]),
                               lambda: generate_building(kind, seed=(0, v)), benc, bdec)
    fenc, fdec = mesh_codec("body")
    for key, spec in FAUNA.items():
        store.get_or_build("body", dict(species=key, scale=1.0), lambda: (body(key, spec.rgb), {}), fenc, fdec)
    print(f"baked in {time.time() - n0:.1f}s")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plandscape.assets")
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    sub.add_parser("prune")
    sub.add_parser("bake-models")
    b = sub.add_parser("bake")
    b.add_argument("--variants", type=int, default=2)
    b.add_argument("--detail", default="low")
    b.add_argument("--seasons", nargs="+", default=["spring", "summer", "fall", "winter"])
    b.add_argument("--glb", action="store_true", help="also write a .glb per asset")
    f = sub.add_parser("find")
    f.add_argument("kind")
    f.add_argument("filters", nargs="*")
    a = ap.parse_args(argv)
    store = AssetStore(a.root, export_glb=getattr(a, "glb", False))
    if a.cmd == "bake":
        bake(store, a.variants, a.detail, a.seasons)
    elif a.cmd == "bake-models":
        print(models.bake(store))
    elif a.cmd == "prune":
        prune(store)
    elif a.cmd == "find":
        flt = dict(x.split("=", 1) for x in a.filters)
        for e in store.find(a.kind, **flt):
            print(json.dumps(dict(key=e.key, params=e.params, meta={k: v for k, v in e.meta.items() if k != "events"})))
    print(json.dumps(store.stats(), indent=1))


if __name__ == "__main__":
    main()

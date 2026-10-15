"""Asset library CLI.

  python -m plandscape.assets stats
  python -m plandscape.assets bake --variants 3 --detail low --seasons summer fall
  python -m plandscape.assets find tree species=live_oak season=fall
  python -m plandscape.assets export-glb        # write a .glb next to every mesh asset
"""

from __future__ import annotations

import argparse
import json
import time

from ..fauna.agents import FAUNA
from ..fauna.bodies import body
from ..flora.species import SPECIES
from ..flora.tree import generate_tree
from ..scene.buildings import generate_building
from .store import AssetStore, mesh_codec, tree_codec


def bake(store, variants, detail, seasons, moistures=(0.5, 0.8)):
    enc, dec = tree_codec()
    n0 = time.time()
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
    elif a.cmd == "find":
        flt = dict(x.split("=", 1) for x in a.filters)
        for e in store.find(a.kind, **flt):
            print(json.dumps(dict(key=e.key, params=e.params, meta={k: v for k, v in e.meta.items() if k != "events"})))
    print(json.dumps(store.stats(), indent=1))


if __name__ == "__main__":
    main()

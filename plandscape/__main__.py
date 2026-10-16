"""CLI: python -m plandscape "longleaf savanna near Mobile at dusk with deer" --out out/demo"""

from __future__ import annotations

import argparse
import os

from .scene.compose import compose
from .scene.planner import plan
from .scene.preview import closeup, homestead, map_view, perspective


def write_viewer(out):
    """Copy viewer/index.html into a scene directory (with the doctype and viewport it needs standalone)."""
    viewer = os.path.join(os.path.dirname(__file__), "..", "viewer", "index.html")
    if os.path.exists(viewer):
        with open(viewer) as f, open(os.path.join(out, "index.html"), "w") as g:
            g.write("<!doctype html>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n" + f.read())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plandscape", description=__doc__)
    ap.add_argument("prompt")
    ap.add_argument("--out", default="out/scene")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--size", type=float, default=128.0, help="tile edge in metres")
    ap.add_argument("--detail", default="low", choices=["low", "med", "high", "cm"])
    ap.add_argument("--sim", type=float, default=180.0, help="seconds of animal life to simulate")
    ap.add_argument("--no-preview", action="store_true")
    a = ap.parse_args(argv)
    p = plan(a.prompt, seed=a.seed, size_m=a.size, detail=a.detail)
    print(p.to_json())
    res = compose(p, a.out, sim_seconds=a.sim)
    write_viewer(a.out)
    if not a.no_preview:
        map_view(res, os.path.join(a.out, "map.png"))
        perspective(res, os.path.join(a.out, "preview.png"))
        closeup(res, os.path.join(a.out, "closeup.png"))
        homestead(res, os.path.join(a.out, "homestead.png"))
    print(res["stats"])


if __name__ == "__main__":
    main()

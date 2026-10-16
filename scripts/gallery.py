"""Regenerate docs/gallery: the review renders that show where the project stands.

  python3 scripts/gallery.py            # renders the three reference scenes + species sheet
  python3 scripts/gallery.py --reuse    # only re-encode existing out/<name>/ renders

Images are JPEG at ≤1100 px so the gallery stays a few MB in plain git (no LFS).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

SCENES = {
    "monte-sano": "Monte Sano hardwood cove with a dogtrot cabin, a creek, two deer, three squirrels "
                  "and a turkey flock at golden hour in fall",
    "longleaf": "longleaf pine savanna near Mobile at dusk, dirt path, a few deer",
    "bayou": "cypress bayou floodplain with a shotgun house and an armadillo at noon in summer",
}
OUT = os.path.join(ROOT, "docs", "gallery")


def _jpeg(src, dst, width=1100):
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=84, optimize=True)


def species_sheet(path, season="summer"):
    from plandscape.flora.species import SPECIES
    from plandscape.flora.tree import generate_tree
    from plandscape.render import render
    W, H = 300, 380
    tiles = []
    tmp = os.path.join(ROOT, "out", "gallery_tmp")
    os.makedirs(tmp, exist_ok=True)
    for k in SPECIES:
        m = generate_tree(k, seed=5, season=season, moisture=0.85, detail="low")
        p = os.path.join(tmp, f"{k}.png")
        render([m.bark, m.foliage], p, size=(W, H), elevation=8)
        tiles.append((k, p))
    sheet = Image.new("RGB", (W * 6, H * ((len(tiles) + 5) // 6)), "white")
    for i, (k, p) in enumerate(tiles):
        im = Image.open(p)
        ImageDraw.Draw(im).text((8, 8), k.replace("_", " "), fill=(0, 0, 0))
        sheet.paste(im, ((i % 6) * W, (i // 6) * H))
    sheet.save(path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    stats = {}
    for name, prompt in SCENES.items():
        d = os.path.join(ROOT, "out", name)
        if not a.reuse or not os.path.exists(os.path.join(d, "preview.png")):
            from plandscape.__main__ import main as run
            run([prompt, "--out", d])
        for img in ("preview", "closeup", "map"):
            _jpeg(os.path.join(d, f"{img}.png"), os.path.join(OUT, f"{name}-{img}.jpg"))
        s = json.load(open(os.path.join(d, "scene.json")))["stats"]
        stats[name] = {k: s.get(k) for k in ("glb_mb", "trees", "tree_tris", "ground_props", "agents", "signs")}
    for season in ("summer", "fall"):
        p = species_sheet(os.path.join(ROOT, "out", f"species_{season}.png"), season)
        _jpeg(p, os.path.join(OUT, f"species-{season}.jpg"), width=1500)
    with open(os.path.join(OUT, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()

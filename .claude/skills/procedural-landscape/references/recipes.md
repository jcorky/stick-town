# Recipes

Companion to `../SKILL.md`. Run from the repo root.

## Species contact sheet
```python
from plandscape.flora.tree import generate_tree
from plandscape.flora.species import SPECIES
from plandscape.render import render
from PIL import Image, ImageDraw
W, H = 360, 420; tiles = []
for k in SPECIES:
    m = generate_tree(k, seed=5, season="summer", moisture=0.85)
    p = f"out/review/tree_{k}.png"; render([m.bark, m.foliage], p, size=(W, H), elevation=8); tiles.append((k, p))
sheet = Image.new("RGB", (W * 4, H * ((len(tiles) + 3) // 4)), "white")
for i, (k, p) in enumerate(tiles):
    im = Image.open(p); ImageDraw.Draw(im).text((8, 8), k, fill=(0, 0, 0)); sheet.paste(im, ((i % 4) * W, (i // 4) * H))
sheet.save("out/review/species_sheet.png")
```

## Same scene, many seeds (variation check)
```bash
for s in 1 2 3; do python3 -m plandscape "pine savanna near Mobile with deer" --seed $s --out out/var$s --no-preview; done
```

## Behaviour audit
```python
import json; s = json.load(open("out/x/scene.json"))
from plandscape.assets.store import AssetStore
for e in AssetStore().find("behavior", species="white_tailed_deer"):
    print(e.meta["state_mix"], round(e.meta["distance"] / e.meta["duration"], 2), "m/s")
```

## Publish a viewer artifact
```bash
D=$SCRATCH/viewer; mkdir -p $D
cp viewer/index.html out/x/scene.json $D/ && base64 -w0 out/x/scene.glb > $D/scene.glb.txt
```
Then publish `$D/index.html` with `files={"scene.glb.txt": ..., "scene.json": ...}`.

## Validate a GLB
```python
from plandscape.export.validate import validate_glb; print(validate_glb("out/x/scene.glb") or "OK")
```

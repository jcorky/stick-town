# stick-town · procedural landscapes of the American South

Type a sentence, get a living place:

```bash
python3 -m plandscape "Monte Sano hardwood cove with a dogtrot cabin, a creek, two deer, three squirrels and a turkey flock at golden hour in fall" --out out/monte-sano
```

You get `scene.glb` (textured terrain, trees, grass, photoscanned ground props, buildings, water, animated animals), `scene.json` (the plan, stats, every tree, prop and animal, asset credits), `map.png` (trails, canopy, tracks, signs of life), `preview.png`, `closeup.png` (ground level, where the props are), and `index.html` — a three.js viewer with wind, a timeline and follow-cam.

![Monte Sano cove, fall](docs/gallery/monte-sano-preview.jpg)

More renders in the [gallery](docs/gallery/README.md).

## What's in it

- **Terrain** for five Southern physiographic provinces — Coastal Plain sand, Delta alluvium, Piedmont red clay, Cumberland Plateau mesas (Monte Sano), Ridge and Valley — with erosion, creek routing, bayous, slope and moisture layers.
- **Trees** grown, not modelled: space colonisation, pipe-model branch radii, root flare and cypress buttresses, north-side moss, Spanish moss on horizontal limbs, cypress knees, palm fronds, flowers and season-correct colour. Crowns are alpha-masked cards showing photographed leaf sprigs (shape-matched per species) and pine needle fascicles; bark carries a tiling photo texture. Twelve Southern species so far.
- **Ground**: province soil colour with a photo detail texture per biome (leaf litter, forest floor, swamp soil, grass), warm-season grasses that go dormant in winter, individual grass blades near the camera.
- **Ground props**: photoscanned stumps, fallen logs, deadfall, mossy sandstone rocks, ferns and shrubs from Poly Haven, decimated to a few thousand triangles and scattered by habitat around the camera.
- **Desire paths** from the Helbing active-walker model: people walk between doors, mailboxes, the creek and the big shade tree, and the trails emerge on their own.
- **Animals that plan and change their minds**: deer, gray squirrels, turkeys, armadillos, coyotes and people with needs, personalities, memory, A* routes over cover and trails, and continuous, seeded deviation (startles, snacks, pauses, flocking, hunting, tree escapes). They leave signs — beds, digs, scratches, acorn caches, and forgotten caches that sprout as oak seedlings.
- **Buildings and props**: shotgun house, dogtrot, barn, farmhouse with a brick end-chimney, church; raised on piers with metal roofs and porches; mailboxes, fences, a clothesline with laundry.
- **Asset library**: everything generated is stored by content hash and reused (`python3 -m plandscape.assets bake`). See [docs/ASSETS.md](docs/ASSETS.md).
- **Source harvester**: a license-checked catalog of public procedural repos, datasets and papers (`python3 -m plandscape.sources.harvest probe`), plus licence-gated downloads from CC0 asset sites (`python3 -m plandscape.sources.sites probe`).

## Getting the asset library

Binaries in `assets_library/` are stored with Git LFS. After cloning run `git lfs install && git lfs pull`, or regenerate them with `python3 -m plandscape.assets bake` (generation is deterministic).

## Requirements

Python 3.10+ with numpy, scipy, Pillow and matplotlib. Nothing else — it runs in locked-down sandboxes. Textures and props are downloaded once (from ambientCG and Poly Haven) and then live in the asset library; offline, textures fall back to procedural stand-ins and scenes simply have fewer props. Blender, rasterio and friends are optional future extras.

## Commands

| | |
|---|---|
| `python3 -m plandscape "<prompt>" --out DIR [--detail low\|med\|high\|cm] [--size 128] [--sim 180] [--seed N]` | prompt → scene |
| `python3 -m plandscape.assets bake --variants 2 --seasons fall summer` | pre-build the library |
| `python3 -m plandscape.assets bake-models` | import the Poly Haven ground props |
| `python3 -m plandscape.assets prune` | delete entries from superseded generator versions |
| `python3 -m plandscape.assets find tree species=live_oak season=fall` | search the library |
| `python3 -m plandscape.sources.sites probe` | re-read the asset sites' licence pages |
| `python3 -m plandscape.sources.harvest probe \| clone \| index \| discover` | catalog upkeep |
| `python3 -m unittest discover -s tests` | tests |
| `python3 scripts/gallery.py` | regenerate `docs/gallery` (reference scenes + species sheets) |

Open `DIR/index.html` through any static server (`python3 -m http.server -d DIR`) to explore the scene.

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers, seeding, LOD, how 1 cm detail works
- [docs/TECHNIQUES.md](docs/TECHNIQUES.md) — every algorithm by name, with its equations
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — real-world data for real-place mode
- [docs/ASSETS.md](docs/ASSETS.md) — the asset library and how to share it
- [CLAUDE.md](CLAUDE.md) — orientation Claude Code loads automatically
- [.claude/skills/procedural-landscape/SKILL.md](.claude/skills/procedural-landscape/SKILL.md) — working method, rules and pitfalls for Claude sessions (auto-discovered)
- [HANDOFF.md](HANDOFF.md) — current status, next priorities, and the prompt that starts the next session
- [CHANGELOG.md](CHANGELOG.md)

Licensed Apache-2.0. Third-party sources and their licences are tracked in `catalog/`; imported CC0 textures and models are credited in [catalog/PROVENANCE.md](catalog/PROVENANCE.md) and in each scene's `scene.json`.

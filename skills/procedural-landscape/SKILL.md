---
name: procedural-landscape
description: Build, extend and review procedural 3D landscapes of the American South with the plandscape package (repo jcorky/stick-town) — terrain, trees, grass, desire paths, buildings, animals with planned-but-deviating behaviour, the asset library and the license-gated source catalog. Use whenever the user asks to generate a scene from a prompt, add a species/animal/building/province, raise detail, bake or search assets, harvest procedural repos, or mentions stick-town, plandscape, desire paths, or "procedural landscape".
---

# Procedural landscape (plandscape)

You are working on a generator that turns a sentence into a living Southern place. The bar is "feels alive": plausible species in plausible places, ground that shows where people and animals go, animals that have reasons for what they do and still surprise you.

## 0. Orient (2 minutes, every session)

1. Read `README.md`, `docs/ARCHITECTURE.md`, and `references/pitfalls.md` in this skill folder.
2. `python3 -m unittest discover -s tests` — must pass before you change anything.
3. `python3 -m plandscape.assets stats` — see what's already built. **Reuse before you generate.**
4. Check the environment: `python3 -c "import numpy, scipy, PIL, matplotlib"`. PyPI is often blocked in sandboxes; don't plan work that needs new packages in the core.

## 1. The loop for any change

```
plan the change → implement → render it → LOOK at the image → fix → test → store/bake → commit
```

- **Render every generator change** with `plandscape.render.render()` (single assets) or `python3 -m plandscape "<prompt>" --out out/x` (scenes), then open `preview.png` and `map.png` with the image viewer. Numbers passing is not evidence; twice in v0.1 the stats looked fine while the picture was broken.
- Write a contact sheet when changing anything per-species or per-kind (see `references/recipes.md`).
- Keep `python3 -m unittest discover -s tests` green; add a test for every bug you fix.

## 2. Non-negotiables

- **Seeding**: all randomness via `plandscape.rng.rng(*keys)` keyed by purpose, never by call order.
- **Zero-dep core**: numpy, scipy, Pillow, matplotlib. Optional extras behind guarded imports in separate modules.
- **1 cm is synthesised near the camera, never stored** (see the LOD table in ARCHITECTURE.md).
- **Asset library first**: wrap any expensive generator in `AssetStore.get_or_build(kind, params, build, encode, decode)`. Quantise continuous params into a few buckets or the cache never hits. Bump `GENERATOR_VERSIONS[kind]` whenever that generator's output changes.
- **Licences are probed, not remembered**: add repos to `catalog/sources.json`, then `python3 -m plandscape.sources.harvest probe`. Only permissive licences may be adapted; record adaptations in `catalog/PROVENANCE.md`. Copyleft, non-commercial and no-licence repos are study-only.
- **No invented facts**: species dimensions, animal behaviour numbers and dataset specs need a source you opened; otherwise keep `verified=False` and say so.
- **Output budget**: scene GLB under 15 MB (artifact limit 16 MB). Use variant instancing, `TWIG_CULL`, leaf/grass budgets; normals are already int8.

## 3. Extending

| Add | Where | Must also |
|---|---|---|
| Tree species | `flora/species.py` (`Species(...)`) | habitat window, provinces, season colours; add to `planner.BIOME_TREES`; contact-sheet render; `verified=False` until checked against Silvics/PLANTS |
| Leaf type | `flora/tree._foliage_mesh` | budget scaling so cover stays constant across `detail` |
| Animal | `fauna/agents.FAUNA` + `fauna/bodies.body` | activity hours, fears, food layer, group size, flight behaviour; planner word in `FAUNA_WORDS`; check its `state_mix` in `scene.json` is varied, and that it doesn't panic forever |
| Behaviour | `Agent.decide` (new option) or `Agent.step` (new interrupt) or `Agent.arrive` (new outcome/sign) | an event string in `self.events`, a sign in `world.signs` if it marks the world |
| Building/prop | `scene/buildings.py` | footprint + door for desire paths; render from two angles |
| Province | `terrain/heightfield.PROVINCES` + `planner.REGIONS` | soil colours; render the tile; check creeks/water appear |
| Real data | `load_dem()` etc. | optional import; cache tiles in the library |

## 4. Reviewing a scene (what "alive" means)

Open `map.png` and `scene.json` and check:
- Trails connect real destinations (doors, mailbox, creek, shade tree, map edges) and bend around trunks and slopes; not dotted, not a grid.
- Each animal species shows ≥3 states in `state_mix`; deer travel at walking pace on average, not sprinting; nobody flees continuously.
- Signs of life exist (beds, digs, scratches, caches/seedlings) and sit where the animals actually went.
- Species match place: cypress in the wet, longleaf on dry sand, tulip poplar in moist coves, palmetto only on the coast.
- Season reads at a glance (fall colour, bare winter hardwoods with moss still hanging, dormant tan lawns in winter).

## 5. Finishing a session

- Update `README.md` (what changed), this skill's `references/pitfalls.md` (anything learned the hard way), and `HANDOFF.md` (next priorities).
- `python3 -m plandscape.assets bake` for anything new, commit small descriptive commits, push.
- Publish a viewer artifact of a representative scene: the artifact host doesn't serve `.glb`, so ship `scene.glb.txt` (base64) beside `index.html`; the viewer falls back to it automatically.

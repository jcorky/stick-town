---
name: procedural-landscape
description: Build, extend and review procedural 3D landscapes of the American South (plandscape / jcorky/stick-town): terrain, trees, grass, desire paths, buildings, living animals, asset library.
---

# Procedural landscape (plandscape)

You are working on a generator that turns a sentence into a living Southern place. The bar is "feels alive": plausible species in plausible places, ground that shows where people and animals go, animals that have reasons for what they do and still surprise you.

This file is the canonical copy of the skill. Claude Code loads it automatically from `.claude/skills/` in this repo. A copy also lives in the owner's claude.ai skills; when you change this file, say so at the end of the session so that copy can be re-synced.

## 0. Orient (2 minutes, every session)

1. Read `CLAUDE.md`, `HANDOFF.md` (current status and priorities), `README.md` and `docs/ARCHITECTURE.md`. Skim section 6 below.
2. `python3 -m unittest discover -s tests` — must pass before you change anything.
3. `python3 -m plandscape.assets stats` — see what's already built. **Reuse before you generate.** If `assets_library/` contains LFS pointer files instead of data, run `git lfs pull`, or rebuild with `python3 -m plandscape.assets bake`.
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
- **1 cm is synthesised near the camera, never stored** (see the LOD table in `docs/ARCHITECTURE.md`).
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
| Asset kind | `assets/store.GENERATOR_VERSIONS` + a codec | a `bake` step in `assets/__main__.py`; a round-trip test |

## 4. Reviewing a scene (what "alive" means)

Open `map.png` and `scene.json` and check:
- Trails connect real destinations (doors, mailbox, creek, shade tree, map edges) and bend around trunks and slopes; not dotted, not a grid.
- Each animal species shows ≥3 states in `state_mix`; deer travel at walking pace on average, not sprinting; nobody flees continuously.
- Signs of life exist (beds, digs, scratches, caches/seedlings) and sit where the animals actually went.
- Species match place: cypress in the wet, longleaf on dry sand, tulip poplar in moist coves, palmetto only on the coast.
- Season reads at a glance (fall colour, bare winter hardwoods with moss still hanging, dormant tan lawns in winter).

## 5. Finishing a session

- Update `HANDOFF.md` (status, what changed, next priorities), `CHANGELOG.md`, `README.md` if commands or features changed, and section 6 of this file with anything learned the hard way.
- `python3 -m plandscape.assets bake` for anything new, commit small descriptive commits, push.
- Publish a viewer artifact of a representative scene: the artifact host doesn't serve `.glb`, so ship `scene.glb.txt` (base64) beside `index.html`; the viewer falls back to it automatically (see `references/recipes.md`).

## 6. Pitfalls already hit (append new ones here, newest at the bottom of each group)

### Environment (Claude sandbox)
- PyPI is blocked (connect_rejected), even via the proxy. Public `git clone` from GitHub works. Hence the zero-dependency core.
- The GitHub GraphQL API is unavailable; REST works only for repos attached to the session. You cannot create repos or install GitHub Apps from the session — ask the user.
- The session's GitHub identity can differ from the repo owner's account (v0.1: the session signed in as `thecheckdigit`, the repo is `jcorky/stick-town`). Push needs the Claude GitHub app installed on the owner's account with access to the repo, and GitHub reconnected in claude.ai Settings → Connectors.
- `pkill -f <pattern>` where the pattern appears in your own command line kills your shell (exit 144).
- Artifacts don't serve `.glb`. Publish `scene.glb.txt` (base64); the viewer decodes it.

### Numerics / geometry
- `_norm(v)` on a 1-D vector returns 1-D; indexing `[0]` turns it into a scalar and silently breaks direction maths (v0.1 trunk loop hung forever).
- Any growth loop needs an iteration cap and a z-clamp; a negative-tropism species (live oak) can steer a trunk downward forever.
- Space colonisation: a leader surrounded by attraction points on all sides averages to ~0 and never branches (pines came out as bare poles). Fall back to the direction of one associated point when the mean is small.
- Pipe model + DBH scaling makes leader tops too thick on excurrent trees; taper the trunk explicitly.

### Simulation
- Scalar `map_coordinates` per walker step is ~15× slower than advancing a batch of walkers in lockstep.
- Depositing only at step points on a 1 m grid gives dotted trails; also deposit at the step midpoint.
- Animals with perception ≈ tile size panic forever. Use flight-initiation distance (< perception, scaled by boldness), require the threat to be approaching, add a cooldown and habituation.
- "a turkey flock" must parse as a group; "shotgun house" must not also add a farmhouse.

### Rendering / review
- Painter's algorithm misorders large triangles (gable roofs looked like hips) — use the z-buffer renderer.
- When thinning triangles for a quick preview, never thin terrain/buildings; holes make the ground look missing.
- Dusk lighting in review renders hides form; review in neutral light, view in the scene's real light.
- Low leaf budgets make broadleaf crowns look like wire; scale leaf cards up to keep cover constant.

### Data / licences
- 6 of 23 licences in the first catalog draft were wrong when probed: terra (grass) is CC BY-NC; proctree, SimpleHydrology and SimpleErosion have no licence file (all rights reserved); Blender add-ons and blosm have no root licence file. Always probe.

### Tests
- Spanish moss is evergreen, so a "deciduous trees are bare in winter" test must use a dry site (`moisture=0.1`) or it counts moss as leaves.

### Asset library
- Continuous params (moisture 0.4137…, body scale 1.0734…) mean zero cache hits. Bucket them.
- Bump `GENERATOR_VERSIONS` when output changes, or the library serves stale models.

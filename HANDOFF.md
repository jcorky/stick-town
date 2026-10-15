# Handoff prompt — procedural-landscape (repo: jcorky/stick-town)

Paste everything below the line into a new Claude Code session with **jcorky/stick-town** attached (push access).

---

You are continuing **procedural-landscape** (Python package `plandscape`) in the repo **jcorky/stick-town**: a generator that turns a plain-language prompt ("longleaf pine savanna near Mobile at dusk, dirt path, a few deer") into a living 3D landscape of the American South — terrain, trees, grass, desire paths, buildings, and animals that plan routes and deviate from them — exported as GLB and viewable in a three.js page.

## First, orient (do this before writing code)
1. Read `README.md`, `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md`, and `skills/procedural-landscape/SKILL.md`. Load that skill and follow it.
2. Run `python3 -m plandscape.assets stats` to see what's already in the asset library — reuse before generating. Then run `python3 -m unittest discover -s tests` and `python3 -m plandscape "live oaks and a shotgun house in the Mississippi delta at dusk with deer" --out out/demo`. Open `out/demo/preview.png` and look at it. Note what's wrong before fixing anything.
3. If the repo is empty (the first push didn't land), rebuild from the module map in "What exists" below — same names, same seeding rules.

## The non-negotiable design rules
- **Deterministic seeding.** Every random choice goes through `plandscape.rng.rng(*keys)` keyed by *what* it's for (`"tree", species, id`), never by call order. Same prompt + seed → same world; any new key → new variant. That's how "infinite combinations" stays reproducible.
- **Zero-dependency core.** `plandscape` runs on numpy + scipy + Pillow only. Optional extras (rasterio, Blender bpy, numba) live behind import guards in separate modules.
- **1 cm detail is synthesised, never stored.** Real data gives the base (USGS 3DEP ~1 m DEMs, NAIP ~0.6–1 m imagery, NLCD 30 m land cover, USFS FIA plots, OSM / Microsoft building footprints). Everything finer — leaves, grass blades, bark, pebbles, footprints — is generated on demand for the region near the camera via LOD. The American South at 1 cm would be ~10^16 cells; never attempt a full-resolution bake.
- **Store everything you build.** Every expensive generator goes through `AssetStore.get_or_build(...)` (`plandscape/assets/store.py`) so trees, buildings, terrain tiles, animal bodies and behaviour clips are generated once and reused across scenes and sessions. Bucket continuous parameters so the cache actually hits, and bump `GENERATOR_VERSIONS[kind]` whenever a generator's output changes. Bake new content with `python3 -m plandscape.assets bake`.
- **Look at every change.** After changing a generator, render it with `plandscape.render.render()` (or the viewer) and inspect the image. Numbers passing isn't the same as it looking right.
- **License gate.** Only copy code from permissive sources (MIT, BSD, Apache-2.0, Zlib, CC0, Unlicense, MPL-2.0 file-level). GPL/LGPL/AGPL repos (e.g. blender-addons, blosm) are study-only: read them for technique, never paste their code. Record provenance for anything adapted in `catalog/PROVENANCE.md`. The repo itself is Apache-2.0.
- **No fabrication.** Species dimensions, animal behaviour figures and dataset specs must come from a source you actually opened; mark anything unverified `verified=False` and say so. Don't invent repo names, papers, or licenses — verify with `git ls-remote` / the LICENSE file.

## What exists (v0.1)
| Module | Does |
|---|---|
| `rng.py`, `noise.py` | keyed seeding; vectorised Perlin, fBm, ridged, domain warp |
| `terrain/heightfield.py` | tiles for 5 provinces (coastal_plain, floodplain, piedmont red clay, cumberland_plateau / Monte Sano mesa, ridge_and_valley), thermal erosion, D8 flow, creeks, slope/moisture layers; `load_dem()` stub for 3DEP |
| `flora/species.py` | 12 Southern species as growth parameters (live oak, loblolly, longleaf, bald cypress, magnolia, sweetgum, tulip poplar, white/water oak, dogwood, redbud, sabal palmetto) — all `verified=False` |
| `flora/tree.py` | space colonisation (Runions 2007), pipe-model radii, root flare/buttress, bark furrows + north-side moss, broadleaf blades, pine needle tufts, cypress sprays, palm fronds, flowers, Spanish moss, cypress knees; season-aware; leaf budget by `detail` (low/med/high/cm) |
| `paths/desire.py` | Helbing active-walker desire paths (batched), obstacle cost from slope/water/trunks/buildings; shared `TrailField` |
| `fauna/agents.py` | 6 species (deer, gray squirrel, turkey, armadillo, coyote, human): needs, personality, memory with forgetting, softmax utility decisions, A* routes preferring cover/trails, OU heading noise, startle/alert/flee with flight distance + habituation, opportunistic snacking, flock cohesion, hunting, tree climbing, acorn caching (forgotten caches → oak seedlings), and life signs (beds, digs, scratches) |
| `render.py`, `scene/preview.py` | z-buffered preview renderer; scene preview + annotated map (trails, canopy, tracks, signs) |
| `ground/surface.py` | province soil colour, litter/pine straw, trampled trails, dormant winter lawns, grass blades (6 grasses) |
| `scene/buildings.py` | shotgun, dogtrot, barn, farmhouse, church on piers with porches and metal roofs; mailbox, fence, clothesline |
| `scene/planner.py`, `scene/compose.py` | prompt → `ScenePlan` → full scene; CLI `python3 -m plandscape "<prompt>" --out DIR` |
| `export/gltf.py`, `export/validate.py` | dependency-free GLB writer (instancing, int8 normals, agent animations) and structural validator |
| `assets/store.py` | content-addressed asset library with search; CLI `python3 -m plandscape.assets bake/find/stats` |
| `viewer/index.html` | three.js r128 viewer: time-of-day lighting, wind, timeline, follow-an-animal, event log |
| `sources/` + `catalog/sources.json` | curated seed catalog of public procedural repos/datasets/papers; license-gated harvester (`python3 -m plandscape.sources.harvest`) |

The license probe already corrected the catalog: terra (grass) is CC BY-NC, and proctree, SimpleHydrology and SimpleErosion have no licence file — all study-only. Read `skills/procedural-landscape/references/pitfalls.md` before starting; it lists every trap hit in v0.1.

## Your job, in priority order
1. **Grow the asset library.** Bake all species × seasons × ≥4 variants at `low` and `med`, every building kind × 4 variants, and behaviour clips from at least 20 scenes across provinces and times of day. Add a `grass_patch` kind (tileable blade patches per grass mix/season) and a `prop` kind. Decide with the user where binaries live (Git LFS vs a release asset) before committing large libraries.
2. **Harvest.** Run the harvester on the catalog. Where the network allows, use GitHub search (`--discover`) to propose more candidates into `catalog/candidates.json` for human review — don't auto-clone discoveries. For each permissive repo, write a short technique note in `catalog/notes/<id>.md` (what it does well that we don't).
3. **Verify species data** against USFS *Silvics of North America* (Ag. Handbook 654) and USDA PLANTS; flip `verified=True` only with a citation in `notes`.
4. **Raise fidelity, near-field first:** blade-level grass (Bermuda, St. Augustine, centipede, broomsedge, with trampling from the trail field), leaf-litter and pine-straw ground cover, bark displacement, wind sway in the viewer, LOD tiers (impostor billboards far, full mesh near, `detail="cm"` within ~5 m of camera).
5. **Fauna next steps:** skeletal gaits, day/night schedules over hours of sim time, multi-day memory, more species (great blue heron, cardinal, box turtle, raccoon, red-tailed hawk, fire ants as a ground effect), and animals + people sharing and reinforcing one trail network.
6. **Real-data mode:** implement `load_dem()` for 3DEP and an NLCD/OSM loader behind optional deps, so a prompt can name a real place.

## Definition of done for this session
- `python3 -m unittest discover -s tests` passes; tests cover determinism (same seed → identical arrays) and a smoke run of every generator.
- One command produces a GLB under 15 MB, a `scene.json`, and a `preview.png` that you have looked at, for at least three different prompts in three different provinces.
- README updated with what changed, and `skills/procedural-landscape/SKILL.md` updated with anything you learned the hard way (the skill is meant to get better every session).
- Commits are small and descriptive; push to `main` unless told otherwise.

## Environment notes
- PyPI may be blocked in sandboxed sessions; the core needs nothing beyond numpy/scipy/Pillow. Public `git clone` from GitHub works. The GitHub GraphQL API is unavailable — use REST.
- glTF is y-up; the internal world frame is z-up metres (x east, y north). Convert only at export.
- The owner is Jayde Cork (Huntsville, AL — Monte Sano). Prompts mentioning "Monte Sano" or "Huntsville" should map to the cumberland_plateau province.

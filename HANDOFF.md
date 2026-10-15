# Handoff — stick-town / plandscape

Last updated 2026-10-15, end of session 1 (v0.1.0). Paste everything below the line into a new Claude Code session with **jcorky/stick-town** attached with push access.

---

You are continuing **stick-town**, a Python package (`plandscape`) that turns a plain-language prompt ("longleaf pine savanna near Mobile at dusk, dirt path, a few deer") into a living 3D landscape of the American South: terrain, trees, grass, desire paths, vernacular buildings, and animals that plan routes and deviate from them. Output is an animated GLB, a `scene.json`, review images and a three.js viewer.

## 1. Orient first

1. `CLAUDE.md` is loaded automatically. Load the **procedural-landscape** skill (`.claude/skills/procedural-landscape/SKILL.md`) and follow it; section 6 lists every trap already hit.
2. If `assets_library/**/*.npz` are small text pointer files, run `git lfs pull`. If that fails (LFS quota or network), run `python3 -m plandscape.assets bake --variants 2 --seasons fall summer` to regenerate them; generation is deterministic.
3. `python3 -m unittest discover -s tests` (10 tests, ~8 s) and `python3 -m plandscape.assets stats`.
4. Make one scene and look at it before changing anything:
   `python3 -m plandscape "Monte Sano hardwood cove with a dogtrot cabin, a creek, two deer, three squirrels and a turkey flock at golden hour in fall" --out out/demo`
   then open `out/demo/preview.png` and `out/demo/map.png`.

## 2. Status at handoff

**Works end to end** (prompt → GLB in ~10 s at `detail=low`, 128 m tile):

| Module | State |
|---|---|
| `terrain/heightfield.py` | 5 provinces, erosion, creeks, bayous; `load_dem()` is a stub |
| `flora/` | 12 species, all `verified=False`; detail levels low/med/high/cm |
| `ground/surface.py` | soil, litter, trails, 6 grasses, blades in the central 56 m only |
| `paths/desire.py` | active-walker trails, batched |
| `fauna/` | 6 species with planning, memory, deviation, signs; bodies are static low-poly shapes that slide (no gait) |
| `scene/` | planner (keyword-based, LLM hook `refine()` unused), composer, 5 building types, props |
| `export/` | GLB with instancing, int8 normals, animations; validator |
| `assets/` | library + bake/find/stats CLI; starter library committed via LFS |
| `sources/` + `catalog/` | 23 repos probed (16 permissive, 7 study-only), 3 small repos cloned and indexed, `discover` untested (search API blocked in the sandbox) |
| `viewer/index.html` | lighting, wind, timeline, follow-cam, event log |

**Demo:** a published viewer of the Monte Sano scene exists in the owner's claude.ai artifacts ("Procedural South"), private to the owner.

**Known weaknesses** (look at them, then fix):
- Broadleaf crowns at `low` detail read as wire-and-cards up close; live oak needs denser foliage clusters.
- Desire paths are straight-ish and only in high-traffic corridors; there are no road surfaces beyond a colour strip.
- Grass is one flat triangle per blade and only in the centre of the tile.
- Squirrels spend a lot of time in `freeze`; deer often rest at golden hour. Tune with the behaviour audit recipe.
- The planner is keyword-only; prompts outside its vocabulary fall back to province defaults.
- Preview rendering of a full scene takes ~60 s (pure-Python rasteriser).

## 3. Next priorities, in order

1. **Grow the asset library.** Bake all species × 4 seasons × ≥4 variants at `low` and `med`; all building kinds × 4; behaviour clips from ≥20 scenes across provinces and hours. Add `grass_patch` and `prop` kinds. Ask the owner where large binaries should live (Git LFS quota vs a release asset vs a bucket) before committing more than ~100 MB.
2. **Fidelity near the camera.** Curved multi-segment grass blades with trampling, leaf-cluster cards for broadleaves, bark relief, leaf litter and pine straw as geometry, and LOD tiers: impostors far, meshes near, `detail="cm"` within ~5 m.
3. **Animals that walk.** Skeletal gaits matched to speed, head/tail motion for alert and feeding states, multi-hour day/night runs, and more species (great blue heron, cardinal, box turtle, raccoon, red-tailed hawk, fire-ant mounds as a ground effect).
4. **Verify species data** against USFS *Silvics of North America* (Ag. Handbook 654) and USDA PLANTS; flip `verified=True` only with a citation in `notes`.
5. **Harvest deeper.** Clone and index the remaining permissive repos; for each, write `catalog/notes/<id>.md` on what it does better than us. Run `discover` where the GitHub search API is reachable and leave results in `catalog/candidates.json` for the owner to approve.
6. **Real-place mode.** Implement `load_dem()` for USGS 3DEP behind an optional `rasterio` import, plus NLCD/FIA species weights and OSM buildings (see `docs/DATA_SOURCES.md`). Needs a machine with normal network access.
7. **Planner.** Wire `refine()` to an LLM that fills the `ScenePlan` schema; keep the keyword planner as the offline fallback and validator.

## 4. Non-negotiables (summary; details in the skill)

Purpose-keyed seeding · zero-dependency core · 1 cm synthesised near the camera, never stored · every expensive asset through the library · licences probed, never remembered · no invented facts (`verified=False` until sourced) · look at every visual change · scene GLB under 15 MB.

## 5. Definition of done for the next session

- Tests pass and cover each new feature and each bug fixed.
- At least three prompts in three provinces produce valid GLBs under 15 MB, and you have looked at their previews.
- The asset library has grown and `stats` shows cache hits on a second run of the same prompt.
- `HANDOFF.md`, `CHANGELOG.md`, `README.md` and the skill's section 6 are updated. If the skill changed, say so in your final message so the owner can re-sync their claude.ai copy.
- Small descriptive commits, pushed to `main`.

## 6. Environment notes

- PyPI is blocked in the Claude sandbox; public GitHub clones work; GraphQL doesn't.
- In session 1 the sandbox was signed in to GitHub as `thecheckdigit`, which lacked push access to `jcorky/stick-town`. If pushing fails, ask the owner to install the Claude GitHub app on the `jcorky` account (all repositories) and reconnect GitHub in claude.ai Settings → Connectors.
- Prompts naming Monte Sano or Huntsville map to the Cumberland Plateau province (the owner lives there; it's the default demo).

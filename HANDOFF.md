# Handoff — stick-town / plandscape

Last updated 2026-10-15, end of session 2 (v0.2.0). Paste everything below the line into a new Claude Code session with **jcorky/stick-town** attached with push access.

---

You are continuing **stick-town**, a Python package (`plandscape`) that turns a plain-language prompt ("longleaf pine savanna near Mobile at dusk, dirt path, a few deer") into a living 3D landscape of the American South: terrain, trees, grass, desire paths, vernacular buildings, and animals that plan routes and deviate from them. Output is an animated GLB, a `scene.json`, review images and a three.js viewer.

## 1. Orient first

1. `CLAUDE.md` is loaded automatically. Load the **procedural-landscape** skill (`.claude/skills/procedural-landscape/SKILL.md`) and follow it; section 6 lists every trap already hit.
2. If `assets_library/**/*.npz` are small text pointer files, run `git lfs pull`. If that fails (LFS quota or network), run `python3 -m plandscape.assets bake --variants 2 --seasons fall summer` to regenerate them; generation is deterministic.
3. `python3 -m unittest discover -s tests` (36 tests, ~25 s) and `python3 -m plandscape.assets stats`.
4. Make one scene and look at it before changing anything:
   `python3 -m plandscape "Monte Sano hardwood cove with a dogtrot cabin, a creek, two deer, three squirrels and a turkey flock at golden hour in fall" --out out/demo`
   then open `out/demo/preview.png`, `out/demo/closeup.png` and `out/demo/map.png`.

## 2. Status at handoff

**Works end to end** (prompt → GLB in ~12 s at `detail=low`, 128 m tile; three demo scenes 11.6, 12.3 and 13.2 MB):

| Module | State |
|---|---|
| `terrain/` | 5 provinces, thermal + batched droplet erosion; creeks as traced, sized, meandered, graded channels with a ribbon water surface (§21), one bayou in flat country; `load_dem()` is a stub |
| `flora/` | 12 species, all `verified=False`; broadleaf crowns are textured leaf-sprig cards, pines crossed needle cards, bark textured |
| `textures.py` | leaf/needle cards from ambientCG atlases, bark and ground detail maps, procedural fallbacks |
| `models.py` | glTF importer, crack-free decimator, card thinning; 10 Poly Haven models / 29 variants in the library |
| `ground/surface.py` + `scene/groundcover.py` | soil colour + biome detail texture; grass blades in the central 56 m; photoscanned props in the central 80 m |
| `paths/desire.py` | active-walker trails, batched |
| `fauna/` | 6 species with planning, memory, deviation, signs; bodies are static low-poly shapes that slide (no gait) |
| `scene/` | planner (keyword-based, LLM hook `refine()` unused), composer, 5 building types, props, review renders (`preview`, `closeup`, `homestead`, `creek`, `map`) |
| `export/` | GLB with instancing, textures, quantised attributes, animations; validator |
| `assets/` | library + bake/bake-models/prune/find/stats CLI; 36.5 MB in LFS |
| `sources/` + `catalog/` | 23 repos probed; asset sites (Poly Haven, ambientCG) probed CC0; credits in `catalog/PROVENANCE.md` |
| `viewer/index.html` | lighting, wind on all foliage materials, leaf-shaped shadows, timeline, follow-cam, event log |

**Session 2 history note:** session 1's commits were imported from the owner's bundle. Its building/body/terrain/behaviour LFS objects were never pushed and are lost; they were regenerated, and the asset commit was rewritten (owner approved) so the history only references objects that exist.

**Known weaknesses** (look at them, then fix):
- Bark limbs look faceted in the flat-shaded preview (smooth in the viewer).
- Leaf sets are other species chosen by outline; no Southern-specific leaf scans yet (e.g. sweetgum stars are maple-like).
- Grass blades are curved and trampled now (§17) but only in the central 56 m at ~6 per m² at `low`; a real lawn needs `detail="cm"` near the camera.
- Stump scans are squat hardwood stumps; there's no tall pine stump or longleaf "lighter stump".
- Desire paths are straight-ish and only in high-traffic corridors. The county road is real now (§15) but always crosses west→east; driveways and multiple roads are next.
- Deer rest ~23 % of the time in fall daytime scenes; check activity curves against a source before tuning.
- The planner is keyword-only; prompts outside its vocabulary fall back to province defaults.
- Preview rendering of a full scene takes ~60 s (pure-Python rasteriser).
- Creeks are re-cut at 25 cm inside the near windows (§22) but stay 1 m-faceted elsewhere. No creek rocks, riffles or exposed roots yet; the water is one flat colour.

## 3. Next priorities, in order

0. **Read `catalog/notes/`** — eight permissive repos were studied in session 2; each note lists what is queued from it.
1. **Fidelity near the camera, continued.** Detiling, leaf flutter (§20), fine terrain windows (§22) and far-LOD impostors (§23) are done; next: a middle LOD tier (ring/segment thinning after ez-tree) (impostors far, meshes near, `detail="cm"` within ~5 m).
2. **More imported assets, Southern first.** Search Poly Haven and ambientCG for pine-straw, red-clay, sand and moss textures; look for CC0 photoscans of Southern species' leaves. Only from sites whose licence probe is permissive. Render every variant and check GLB sizes.
3. **Grow the asset library.** All species × 4 seasons × ≥4 variants at `low` and `med`; all building kinds × 4; behaviour clips from ≥20 scenes. Ask the owner where large binaries should live before going past ~100 MB.
4. **Animals.** Gaits by speed are done (§25). Next:
   - knees and planted feet are done (§26); feet still slide where the stance is out of reach (gallop);
   - torso bob and head motion for alert and feeding states;
   - multi-hour runs;
   - more species: heron, cardinal, box turtle, raccoon, red-tailed hawk, fire-ant mounds.
5. **Species data is verified** (§24, `catalog/species_sources.json`). New species need the same: URL plus quote for height, d.b.h., leaf length and habit before `verified=True`. Silvics PDFs: research.fs.usda.gov/download/treesearch/1547.pdf (conifers) and 1548.pdf (hardwoods); the old srs.fs.usda.gov host fails TLS.
6. **Real-place mode.** `load_dem()` for USGS 3DEP behind an optional `rasterio` import, NLCD/FIA species weights, OSM buildings (see `docs/DATA_SOURCES.md`).
7. **Planner.** `refine()` + `validate()` + `claude_llm()` are done (§27, `--llm`), tested with a mocked API; not yet run against the live API (no key in session 3). Next: run it with a key on varied prompts and record failures; widen the keyword vocabulary from what the LLM gets right.

## 4. Non-negotiables (summary; details in the skill)

Purpose-keyed seeding · zero-dependency core · 1 cm synthesised near the camera, never stored · every expensive asset through the library · licences probed, never remembered · no invented facts (`verified=False` until sourced) · look at every visual change · scene GLB under 15 MB.

## 5. Definition of done for the next session

- Tests pass and cover each new feature and each bug fixed.
- At least three prompts in three provinces produce valid GLBs under 15 MB, and you have looked at their previews.
- The asset library has grown and `stats` shows cache hits on a second run of the same prompt.
- `HANDOFF.md`, `CHANGELOG.md`, `README.md` and the skill's section 6 are updated. If the skill changed, say so in your final message so the owner can re-sync their claude.ai copy.
- Small descriptive commits, pushed. Session 2 worked on branch `claude/new-session-4p7ujw` (draft PR #1 into `main`); use the branch the session is given and open a PR.

## 6. Environment notes

- Session 1: PyPI blocked. Session 2 (Claude Code cloud): PyPI, ambientCG, Poly Haven and GitHub LFS all reachable; scipy had to be `pip install`ed. Check `python3 -c "import numpy, scipy, PIL, matplotlib"` first.
- Raw texture/model downloads go to `.cache/downloads/` (git-ignored). Only processed results enter the library.
- Session 2 pushed with the Claude GitHub app on `jcorky/stick-town`. If pushing fails, ask the owner to reconnect GitHub in claude.ai Settings → Connectors.
- `jcorky/ace-combat-mods` documents more asset sources (`asset_library.md`), but the game rips (AC7, Assault Horizon), FlightGear jets and osm2city textures are not usable here (rips / GPL).
- Prompts naming Monte Sano or Huntsville map to the Cumberland Plateau province (the owner lives there; it's the default demo).
- `python3 scripts/viewer_shot.py out/<scene> out/<scene>/viewer.png` screenshots the three.js viewer in headless Chromium (Playwright, swiftshader WebGL; ~30 s). Use it after any viewer shader change: tests never see GLSL compile errors.

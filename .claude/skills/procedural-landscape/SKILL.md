---
name: procedural-landscape
description: Build, extend and review procedural 3D landscapes of the American South (plandscape / jcorky/stick-town): terrain, trees, grass, desire paths, buildings, living animals, asset library.
---

# Procedural landscape (plandscape)

You are working on a generator that turns a sentence into a living Southern place. The bar is "feels alive": plausible species in plausible places, ground that shows where people and animals go, animals that have reasons for what they do and still surprise you.

This file is the canonical copy of the skill. Claude Code loads it automatically from `.claude/skills/` in this repo. A copy also lives in the owner's claude.ai skills; when you change this file, say so at the end of the session so that copy can be re-synced.

## 0. Orient (2 minutes, every session)

1. Read `catalog/notes/README.md` (what each studied repo taught us and what is queued from it), then `CLAUDE.md`, `HANDOFF.md` (current status and priorities), `README.md` and `docs/ARCHITECTURE.md`. Skim section 6 below.
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
- Owner's standing rule: commit and merge regularly, and each commit message names the technique it uses and writes out its equations. Keep `docs/TECHNIQUES.md` in step with the code.

## 2. Non-negotiables

- **Seeding**: all randomness via `plandscape.rng.rng(*keys)` keyed by purpose, never by call order.
- **Zero-dep core**: numpy, scipy, Pillow, matplotlib. Optional extras behind guarded imports in separate modules.
- **1 cm is synthesised near the camera, never stored** (see the LOD table in `docs/ARCHITECTURE.md`).
- **Asset library first**: wrap any expensive generator in `AssetStore.get_or_build(kind, params, build, encode, decode)`. Quantise continuous params into a few buckets or the cache never hits. Bump `GENERATOR_VERSIONS[kind]` whenever that generator's output changes.
- **Licences are probed, not remembered**: add repos to `catalog/sources.json`, then `python3 -m plandscape.sources.harvest probe`. Only permissive licences may be adapted; record adaptations in `catalog/PROVENANCE.md`. Copyleft, non-commercial and no-licence repos are study-only.
- **No invented facts**: species dimensions, animal behaviour numbers and dataset specs need a source you opened; otherwise keep `verified=False` and say so.
- **Output budget**: scene GLB under 15 MB (artifact limit 16 MB). Use variant instancing, `TWIG_CULL`, leaf/grass budgets; normals are int8, UVs uint16, indices 16-bit where they fit. Bark is the largest item (~half a scene).

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
| Asset kind | `assets/store.GENERATOR_VERSIONS` + a codec | a `bake` step in `assets/__main__.py`; a round-trip test that checks UVs and texture keys survive |
| Texture | `textures.py` (key `kind/source`, a recipe in `build`) | grey detail map with mean 0.8 unless it is a model's own colour map; keep the `SOLID_UV` patch opaque and card content out of the top 1/8 strip; a procedural fallback; contact-sheet render; credit in `catalog/PROVENANCE.md` |
| Imported model | `models.MODELS` (+ a role in `scene/groundcover.MIX`) | only from a site whose licence probe is permissive; render every variant after decimation; check the scene GLB size; credit it |

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
- GitHub rejects a push whose history references LFS objects it doesn't have. Push LFS objects in the same session that commits them; if they are lost, the commit that introduced the pointers has to be rewritten (ask the owner first).
- PyPI was reachable in session 2 (scipy had to be installed); don't count on it.

### Numerics / geometry
- `_norm(v)` on a 1-D vector returns 1-D; indexing `[0]` turns it into a scalar and silently breaks direction maths (v0.1 trunk loop hung forever).
- Any growth loop needs an iteration cap and a z-clamp; a negative-tropism species (live oak) can steer a trunk downward forever.
- Space colonisation: a leader surrounded by attraction points on all sides averages to ~0 and never branches (pines came out as bare poles). Fall back to the direction of one associated point when the mean is small.
- Pipe model + DBH scaling makes leader tops too thick on excurrent trees; taper the trunk explicitly.

### Simulation
- Scalar `map_coordinates` per walker step is ~15× slower than advancing a batch of walkers in lockstep.
- Depositing only at step points on a 1 m grid gives dotted trails; also deposit at the step midpoint.
- Animals with perception ≈ tile size panic forever. Use flight-initiation distance (< perception, scaled by boldness), require the threat to be approaching, add a cooldown and habituation.
- A process-wide id counter (`Agent._ids`) silently broke determinism: the same scene differed depending on what ran
  before it in the process. Keys must come from the scene, never from global state. Test by building twice in one process.
- "a turkey flock" must parse as a group; "shotgun house" must not also add a farmhouse.

### Rendering / review
- Painter's algorithm misorders large triangles (gable roofs looked like hips) — use the z-buffer renderer.
- When thinning triangles for a quick preview, never thin terrain/buildings; holes make the ground look missing.
- Dusk lighting in review renders hides form; review in neutral light, view in the scene's real light.
- Low leaf budgets make broadleaf crowns look like wire; scale leaf cards up to keep cover constant.
- Tests never compile the viewer's GLSL. After any `viewer/index.html` change run `scripts/viewer_shot.py` and look
  (it also catches CSS bugs: the drop overlay covered every scene for two sessions). Each `out/<scene>/index.html`
  is a copy made at generation time, so it goes stale; `viewer_shot` refreshes it via `write_viewer`.

### Data / licences
- Species numbers come from `catalog/species_sources.json` (URL + verbatim quote each). Silvics: research.fs.usda.gov/download/treesearch/1547.pdf and 1548.pdf (pdftotext per chapter, not `-layout`; OCR reads "ft" as "R"). srs.fs.usda.gov fails TLS; srs.fs.fed.us and na.fs.fed.us are blocked. FEIS: fs.usda.gov/database/feis/plants/tree/<code>/all.html (no bald cypress review). EDIS: ask.ifas.ufl.edu/publication/ST###.
- 6 of 23 licences in the first catalog draft were wrong when probed: terra (grass) is CC BY-NC; proctree, SimpleHydrology and SimpleErosion have no licence file (all rights reserved); Blender add-ons and blosm have no root licence file. Always probe.

### Docs
- Writing LaTeX into docs from Python strings: `\t` in `\text`/`\times` becomes a TAB and `\f`, `\b`, `\r` vanish too. Use raw strings (`r"..."`) or the Write tool, then `grep -P '\t' docs/TECHNIQUES.md` must find nothing.

### Tests
- Spanish moss is evergreen, so a "deciduous trees are bare in winter" test must use a dry site (`moisture=0.1`) or it counts moss as leaves.

### Textures and imported assets (v0.2)
- ambientCG answers 403 to Python's default User-Agent; send one (`sources.sites.UA`).
- `PineNeedles001` is an atlas of needle fascicles on transparent black, not a ground texture. Look at every downloaded map before deciding what it is.
- Atlas sprites lying sideways (needles) need a rotation so the base is at the bottom; leaf sets used are upright.
- A card's crop box swallowed the reserved solid patch when content reached the top-left corner → opaque squares floating in pine crowns. Card content is now composited below the top 1/8 strip.
- Poly Haven glTFs pack several variants as separate nodes (six rocks, four ferns); import each node, never merge them. Alpha (fern, shrub) is a separate `Alpha` map that the glTF doesn't reference; fetch it.
- Clustering with the normal direction in the *position* key opens cracks at sharp rock edges. Weld positions per cell; split only the vertices (by UV chart and facing).
- Thinning a card-based shrub to ~10% leaves floating leaves; keep large components (stems) and don't thin card shrubs below about a third.
- Poly Haven stumps are squat, root-spread scans that read as mounds on open grass; keep them in litter-covered biomes.
- Variants of one set share one atlas: key textures by asset and material, not variant, or the GLB embeds it six times.
- The preview renderer has no near clip: close-ups must crop the terrain first or it covers the view.

### Baking for the viewer
- The preview renderer's colour (c·T/μ) is not the viewer's (clip(c/μ)·decode_sRGB(T)). Anything baked into a
  texture for the GLB (impostors) must use `render(viewer_colour=True, shading=False)`, or it comes out darker and
  more saturated than the meshes beside it. Compare in `viewer_shot.py` with `--query lod=0`.

### Creeks and flow routing
- Plain D8 on anisotropic terrain drains in dead-straight grid lines; jitter the slopes (keyed) or the creek looks ruled.
- Without pit filling, creeks stop at every erosion hollow; route over `channels.routing_surface`, carve the real z.
- Erosion fans make parallel flow threads that all pass a flow threshold; prune near-parallel lines, one valley, one creek.
- A bank cut that reaches far from the channel flattens steep valley walls into discs; fade it out within w + 2 m.
- Fine terrain patches must equal the coarse *bilinear* surface on their border (fade detail by τ), and windows
  must sit on whole metres, or the stitched mesh cracks. Crop review renders with box edges off the grid lines
  (x.25), or the centroid crop leaves sawteeth.
- Review creeks with `creek.png` and the gallery creek sheet; the map's water raster is 1 m and always looks blocky.

### Wind (§34)
- One plane wave per gust frequency paints bands across the wind (trees in a line move in sync). Split each band into
  ≥3 waves with independent lateral tilts; Davenport coherence then holds per realisation, not only on average.
- A piecewise drag law (U² then U^{2+b}) has a jump in its log-slope β and shows as a dip in gustiness at the knot.
  Use the smooth F ∝ U²(1 + U/U0)^b.
- Rayleigh's quotient on the *wind-load* shape gives nonsense when the load changes (leafless trees: 3–5× f0). Use the
  self-weight shape ω² = gΣmδ/Σmδ², and let twigs < 3 cm ride rigidly in the stem mode, or one leaf-laden 1.2 cm tip
  dominates the quotient.
- The drawn branch radii taper to a fixed 1.2 cm (R_TIP), far too thin to carry metres of twig: beam deflections came
  out at 5–10 m. Floor them by elastic similarity d = c L^{3/2}, c from the tree's own trunk.
- Leaf-card area is inflated to keep crown cover at low budgets; never turn it into leaf *mass*. Use it only as weights.
- Python must hold the gust components as float32 or JS/GLSL and Python drift apart by 1e-5 (tested to 1e-9 now).
- Viewer: three r128 re-uploads material uniforms only when the material changes, so per-tree uniforms need a cloned
  material per tree (and per shadow depth material). `scene.json` must load before the GLB: the shader is generated
  from its constants.
- Absolute coordinates in a world-space mesh (grass) are not heights: the old grass sway scaled with elevation and
  moved plateau grass a metre. Carry per-vertex data instead.
- `scripts/wind_frames.py` steps the wind clock by hand for even frames; in dense forest the camera lands inside a
  crown, so judge single trees with the Python specimen GIF (`gallery.wind_specimen`).

### Player and perception (§35)
- An integrating alarm (da/dt = kS − a/τ) has equilibrium kτS: with k = 1.5, τ = 20 any faint cue (a deer seeing you
  at 100 m, S = 0.02) eventually alerts. Let the alarm *follow* S (rise τ_r, fall τ_d) so thresholds mean salience.
- Plume salience must not scale with 1/U, or a calm evening lets squirrels smell you at 100 m; compare plume shapes.
- A cue consumed in the same tick it is made (a wave timer decremented before the NPCs read it) never reaches anyone:
  stamp actions with a time and let readers check "since".
- Teleporting the player (tests) can put it outside the walkable bounds; clamp moves to the tile instead of
  rejecting them, or the player freezes forever.
- Test play mode with `scripts/play_check.py`: it stops the animation loop and ticks a fixed 0.1 s clock inside the
  page; real-time swiftshader runs at a few fps and makes behaviour depend on frame rate.
- Scratch scenes for testing go through `PLANDSCAPE_ASSETS=<copy of the library>` so their behaviour clips stay out
  of the real library.

### Sculpted bodies (§36)
- Very flat ellipsoids (aspect > ~8) have a poor approximate SDF: Newton projection wobbles and the mesh goes jagged.
  Put thin relief (bands, seams, keels) in a displacement on a smooth shape; gradient normals shade it like a bump map.
- Detail thinner than ~2 grid cells (ears, hooves, claws, eyes) disappears or spikes: make it its own sculpture
  with its own triangle budget and merge.
- A neck part that starts as a fat sphere at its pivot shows a collar; bury it in a torso-side neck root that is wider.
- Keep the rig's `hip` = leg length (gaits use it); the back sits above it. Measure withers on the torso mesh in
  tests, never use `hip` as shoulder height.
- glTF COLOR_0 is linear: convert sculpt colours (picked as display values) with c^2.2 at export, or animals look
  bleached in the viewer while the Python renders look right.
- Budget by measuring the GLB by category before cutting detail; the walk scene's surplus was grass index width,
  not the animals.

### Sex, season and coat (§37)
- `str.replace` on a code pattern shared by several species builders edits all of them: the antler call landed
  in the coyote and raccoon too. Anchor edits on the function's own text.
- Purpose keys without the scene seed (`rng("sex", id)`) give every scene the same draws: two does everywhere.
- Parts finer than ~2 grid cells (antler tines) are swept tubes, not sculptures; budgets cannot buy the grid.
- Per-individual colour as a material factor over shared accessors (`GLB.variant`) instead of a mesh per shade.
  baseColorFactor must stay ≤ 1, so build the geometry at the brightest shade.
- A custom attribute must survive every mesh hop: `sculpt.merge`, rig scaling, `posed_legs`/`body`, compose's
  linear-colour copy. Use a zero row as "not yet set" so defaults fill only gaps.
- Detail that fades below a pixel vanishes at viewing distance; give fur a coarser octave (tufts) that survives.
- three r128 standard material: hook albedo/roughness edits before `#include <lights_physical_fragment>` (after
  `normal` exists); custom glTF attributes arrive lowercased (`_COAT` → `_coat`); `fwidth` needs
  `material.extensions.derivatives`.
- GLTFLoader may suffix duplicate node names (leg0 → leg0_3); match parts by name with the suffix stripped.

### Better models (§38)
- An ear's broad face must face the viewer: an ellipsoid ear with width on x and thickness on y faces sideways
  and reads as a spike or horn from the front. Use `sculpt.leaf`; thin blades are explicit shells, not SDFs.
- A displacement whose amplitude × frequency exceeds ~0.5 makes the field non-monotone, and Newton projection
  throws spikes. Keep fluff gentle.
- Birds' hips belong inside the body (the femur is hidden). Put the belly below the hip joint, or the legs hang
  under a floating body.
- Paint gates on colour brightness fail on dark animals (the gobbler's neck stayed feathered). Gate on hue for
  coloured parts, or mask by position.
- Islands of a few vertices appear where tips thin below the grid; `Sculpt.mesh` drops them, so keep deliberate
  tiny parts (eyes, claws) as their own sculptures.

### Asset library
- A codec that drops UVs makes every *cache hit* untextured while fresh builds look fine. Render a scene twice (second run all hits) after any codec change.
- Never cache a fallback (offline stand-in); a networked run must replace it. Tests must block the network *and* point `assets.store.DEFAULT_ROOT` at a temp dir, or generators that call `AssetStore()` write into the real library.
- Continuous params (moisture 0.4137…, body scale 1.0734…) mean zero cache hits. Bucket them.
- Bump `GENERATOR_VERSIONS` when output changes, or the library serves stale models; then `assets prune`.
- While iterating on a generator, entries built under the new (uncommitted) version are served from cache on the next
  run, so fixes seem to do nothing. Drop that version's entries (index line + file) before re-rendering, or bump again.
- Never `git restore` library files after `prune`: it brings back the pruned files without their index lines (orphans).
  Behaviour churn is fixed at the source, so restoring is no longer needed at all.
- Re-running a scene used to rewrite its behaviour clips with a new `created` timestamp (git churn); `store_behavior` now skips clips it already has. Any new writer into the library should do the same.

# Changelog

## Unreleased

**Added**
- Sex and season in the bodies (TECHNIQUES §37). Each deer, turkey and hiker draws a sex.
  - **Bucks** grow antlers on the Missouri Department of Conservation calendar: buds in spring, velvet in summer, hard antler in fall and winter. The rack is an eight-pointer drawn as swept tubes, because the tines are finer than any sculpting grid. Deer turn grayish brown in winter.
  - **Hens** are brown and tan with buff feather tips and a grey feathered head, no beard and no spurs, at 0.9 of a gobbler's size (Maryland DNR, ADW, ODWC).
  - **Hikers** come in two builds at the NHANES mean statures, 1.750 m and 1.613 m. Women have narrower shoulders, broader hips and a ponytail. Sleeves follow the season, 60 % carry a pack, and their arms swing against their legs.
  - **Sizes by sex** are node scale. Bucks are 1.11× does, from MDC weights, with both withers kept inside the sourced range.
- **Coat detail** in the viewer (`viewer/coat.js`). A per-vertex `_COAT` attribute (kind, feature size, sheen, iridescence) draws fur strands and tufts, feather scallops, shell scutes, and a gobbler's bronze-green iridescence that shifts with viewing angle. Detail fades below a pixel. `?coat=0` turns it off.
- **The player** walks in as the scene's sculpted hiker instead of a box figure: IK legs, swinging arms, crouch, a clap and a wave. People who wave back raise an arm.
- **Gallery:** `variants.jpg` (antler year, winter doe, gobbler and hen, hikers to scale) and `coat.jpg` (viewer close-ups with the coat shader off and on). Library bodies are now per sex, at body-0.3.0.

**Changed**
- Coat shades are three materials sharing one copy of each body's vertex data (`GLB.variant`), instead of a mesh per shade. With the extra variants and the coat attribute, the walk scene stays at 14.7 MB.
- Hikers stand with 1.5 % leg slack instead of 5 %, so they no longer look half-seated.

**Fixed**
- Sex and coat draws keyed only by agent id were the same in every scene; sex is now keyed by the scene seed too.

**Added**
- Sculpted animals (TECHNIQUES §36). Every species is rebuilt from blended anatomical forms (signed distance functions, smooth minimum), meshed by surface nets, projected onto the true surface, and lit by gradient normals.
  - **Anatomy:** real heads, ears, eyes, muzzles, hooves and paws, sourced proportions, and painted markings (the deer's flag and eye ring, the raccoon's mask and rings, the armadillo's nine bands, the turkey's bare blue head, the heron's dagger bill and plume).
  - **Sizes:** checked against new sourced dimensions in `catalog/fauna_sources.json` (deer withers 0.80–1.05 m, coyote ≤ 0.61 m, raccoon 0.23–0.30 m). Legs have unequal segments where sourced: the deer's hock-to-hoof is 0.45 m.
  - **Rigs:** one rig per species and coat, sized by node scale.
  - **Gallery:** `fauna.jpg` is now a portrait grid plus the to-scale lineup. `viewer_shot.py --focus <node>` frames one animal. body-0.2.0.

**Fixed**
- Animal vertex colours were exported as display values, so they looked washed out in the viewer; they are now linear.
- Grass meshes over 65,536 vertices used 32-bit indices; grass is now exported in 16-bit chunks (−0.36 MB on the walk scene).
- Folded heron wings stuck out of the body like fins; they now tuck in (WING_FOLD 0.03), and the body carries sculpted folded wings.

**Added**
- The asset library lives in GitHub (Git LFS in this repo), as the owner decided. It now holds every species × 4 seasons × 4 variants × 2 moistures at `low` and `med` (768 trees), each with its far-LOD impostor (`assets bake` now bakes them together). It also has 20 buildings and behaviour clips and terrains from 20 new scenes (`scripts/bake_scenes.py`, every province, biome, season, hour and wind; every GLB 7–14 MB). Total 213 MB, 1751 entries.

**Fixed**
- Biomes are matched by the longest phrase: "old field" no longer plans as pasture.
- A prompt naming no region takes its province from the biome: longleaf savannas are Coastal Plain, swamps floodplain. "Black Belt" and "prairie" are Coastal Plain.

**Added**
- Walking in (TECHNIQUES §35). The viewer's **Walk in** button makes the player a person the animals sense:
  - **Sight:** acuity, field of view, motion, posture, light and cover.
  - **Hearing:** footsteps by ground and gait, and claps, with 6 dB per distance doubling and foliage loss, masked by wind noise from the §34 field.
  - **Smell:** a Briggs class-D plume carried and meandered by that wind, drawn as drifting motes.
  - **Alarm:** follows the cues up in ~1 s and lets go over ~20 s, leading to sourced displays (stomp and snort, putt, kuk and tail flag).
  - **Flight:** run with the flag up, bolt up a trunk, flush and fly, shut the shell, or the armadillo's 1 m jump. It triggers inside a flight-initiation distance that grows with speed and directness (squirrels 9.2 m, Eason 2019).
  - **Learning:** animals habituate to a quiet visitor, are sensitised by claps and charges, and come to scattered food, getting tamer with each meal.
  - **Hikers:** keep Hall's distances, nod, greet, chat, wave back, sidestep, and become wary if startled. They walk as active walkers, so paths the player wears pull them; trodden grass lies down live.
  - **Export:** each animal node carries its rig (`extras.rig`); `world.bin` carries the height and habitat layers; `scene.json` carries the perception constants, gait tables and attractors.
  - **Tests and sources:** `viewer/life.js` mirrors `plandscape/fauna/perception.py` and the gait maths, tested to 1e-9. Sources are in `catalog/perception_sources.json`.
  - **Tools:** `scripts/play_check.py` is a headless play test. Gallery adds the `walk` scene, `perception.jpg` and `play.jpg`.
- Wind (TECHNIQUES §34). One deterministic gust field drives every tree, limb, branch, leaf and grass blade, evaluated per vertex in the viewer with no state and mirrored exactly in Python.
  - **Field.** Kaimal spectra scaled to measured intensities (σ_u = 1.7 u* over canopies, σ_v = 0.8 σ_u). Frozen turbulence travels downwind at U_h, with Davenport lateral coherence from Cauchy-tilted waves. The mean profile is log-law above the canopy (d = ⅔h, z₀ = 0.123h) and exponential inside it; Beaufort force comes from the NOAA table.
  - **Drag.** Vogel streamlining in a smooth law, F ∝ U²(1 + U/U0)^b with b = −1, giving C_d = 0.185 at 20 m/s.
  - **Trunk.** Rayleigh f0 on each tree's own skeleton, using green-wood E and density from the USDA Wood Handbook and McMahon elastic similarity. Damping is 8.6 % in leaf and 3.9 % bare; leaf mass is calibrated so bare trees sway 1.2× faster.
  - **Limbs and branches.** Beams with their own Rayleigh frequencies (1.4–3× the trunk) and 6 % damping.
  - **Leaves and grass.** Leaves reconfigure downwind and flutter at 6 Hz. Grass bends by local shelter, so waves cross it.
  - **Planner.** Reads wind words ("breezy", "windy", "gale", "north wind", "from the southwest"); the default direction is by season.
  - **Viewer.** A Beaufort slider with NOAA's land descriptions and a direction selector.
  - **Sources and tooling.** Every constant is in `catalog/wind_sources.json`. Gallery adds `wind.jpg` and `wind-oak.gif`; `scripts/wind_frames.py` captures viewer frames on a fixed wind clock.

**Fixed**
- Grass sway in the viewer scaled with absolute elevation (about 1 m of motion on the Monte Sano plateau).
- The viewer's animal list missed raccoons, box turtles and herons; it now follows `scene.json`.

**Added**
- Herons fly when flushed (TECHNIQUES §33). They take off at the sourced 10.7 m/s cruise, climb to 8 m and land again. Wings fold on the ground and flap in the air (±40° at 2.5 Hz, design values), and legs trail back. Gallery adds `flight.jpg`. behavior-0.2.1.
- Raccoon, eastern box turtle and great blue heron (TECHNIQUES §32), with sourced sizes, speeds and activity in `catalog/fauna_sources.json` (unsourced walking speeds are marked as design values). A shore food layer is added along the creek edge for raccoons and herons, and box turtles withdraw into the shell instead of fleeing. The bayou reference scene now has a heron, a raccoon and a box turtle. Gallery adds `fauna.jpg`, all species to scale.

**Fixed**
- "a box turtle" planned three turtles; animal phrases now match longest first.
- Gaze (TECHNIQUES §31). The heading the body no longer follows at rest becomes head yaw ψ (±70°, low-passed with τ 0.3 s), composed with the state pitch as q = yaw · pitch. Heads scan while bodies stand and lead into turns.
- Smooth turning (TECHNIQUES §30). Exported headings are turn-rate limited per species, and standing animals hold their body heading instead of spinning in place. Paths are exported from the full 0.25 s log, keyframes reduced by Ramer–Douglas–Peucker (2 cm, 2°). Gallery adds `motion.jpg`.
- Lying down and the deer's flag (TECHNIQUES §29). Resting animals lower the trunk (0.62 h for quadrupeds, 0.4 h for turkeys) and fold their legs by IK with the feet kept on the ground. Deer raise the white tail when they flee and half-raise it when alert. Gallery `poses.jpg` adds rest and flee.
- Trunk bob and head pose by behaviour (TECHNIQUES §28). The trunk rises and falls b = A h cos 2φ, and the IK keeps the feet planted. Deer, coyotes and turkeys lower their heads to eat or drink and raise them when alert, easing over 0.4 s at each state change. Gallery adds `poses.jpg`.
- `--llm`: an optional Claude pass fills the scene plan from free-form prompts (TECHNIQUES §27). A validator keeps only values the generators can honour; seed, size and detail always stay the keyword planner's, and every rejection is noted in the plan. The client is stdlib-only (`urllib`), with `ANTHROPIC_API_KEY` and an optional `PLANDSCAPE_MODEL`. Offline, or on any failure, the keyword plan is used.
- Knees and planted feet (TECHNIQUES §26). Legs are thigh plus shank. Feet follow stance and swing paths (S = λβ on the ground, a smoothstep arc lifted 0.12–0.3 h in swing), and hips and knees come from two-bone IK. Knees bend their anatomical way: fore carpus and bird intertarsal joints backward, stifle and human knee forward. The gallery's `gaits.jpg` now shows planted feet.
- Animals walk (TECHNIQUES §25). Bodies are rigs with legs pivoting at the hips. Stride is λ = 2.3 h Fr^0.3 (Alexander 1976), and the gait (walk, trot or gallop) is chosen by Froude number (Alexander & Jayes 1983), with footfall offsets and duty factors per gait. Leg swing θ = θmax sin(φ − 2π o) is keyed by stride phase, 8 keys per stride. Squirrels bound. Gallery adds `gaits.jpg`. body-0.1.1.

**Fixed**
- Bare dogwoods grew boxy, right-angled twig runs. The layered crown kept attraction points only in three thin tiers, and space colonisation bridged the empty gaps with vertical stems. Tiers are now soft: point density is p(v) = 0.3 + 0.7 cos²(π(frac(3v) − ½)). tree-0.3.3.

**Added**
- Sourced species data (TECHNIQUES §24): height, d.b.h. and leaf/needle length for all 12 species from Silvics, FEIS, USDA PLANTS and EDIS. Each value is stored with its URL and a verbatim quote in `catalog/species_sources.json`. All species are `verified=True`, and a test keeps code and sources in agreement. Pipe-model radii are remapped so the thinnest branchlets are 1.2 cm on every species (they were 8–12 % of the trunk radius, 4–6 cm on a sourced sweetgum), and the twig cull works again. Bare deciduous trees in winter keep their twigs at every detail. tree-0.3.2.
- Southern ground textures: pine straw (Ground077) under pines, Coastal Plain sand (Ground080) and Delta alluvium (Ground036) as the soil layer. Splat lookup is by biome, then province.
- `prune` retires derived entries whose upstream generator changed: impostors record the tree version, and behaviour clips the terrain version.
- Far-LOD tree impostors (TECHNIQUES §23): each tree model is baked orthographically from two sides into an alpha atlas. The bake is unlit and reproduces the viewer's colour arithmetic, encode(clip(c/μ)·decode(T)). Two crossed cards with rounded normals carry it. Tree nodes name the impostor in `extras.lod_far`, and the viewer swaps them in with `THREE.LOD` beyond 110 m (`?lod=0` turns them off). Atlases are cached as `impostor` library entries, about 25 KB per model. `render()` gains `alpha`, `shading` and `viewer_colour`; `viewer_shot.py` gains `--query`.
- Behaviour clips record the terrain version; `assets prune` drops clips lived on superseded terrain.
- Near-camera terrain (TECHNIQUES §22): fine windows (25 cm at `low`, 10 cm at `cm`) on the focus area and the creek. Each window has cubic B-spline relief and 4 cm micro-relief, and its creeks are re-cut on centrelines resampled every 5 cm. The fine detail fades to the coarse surface at the window border, so there are no seams. Patches are stitched into the one terrain mesh, and `Heightfield.sample` reads them, so grass, props and trunks follow. Creek banks are smooth curves now. `hf.channels` stores depth too. terrain-0.3.1.
- Creeks as channels (TECHNIQUES §21). Pits are filled (Priority-Flood + ε) and filled flats are tilted toward their centrelines (after Garbrecht & Martz). Flow is routed by jittered D8 (after Rho8) and traced into joined polylines, with parallel threads on fans pruned. Each reach is sized by hydraulic geometry (w ∝ A^0.5, d ∝ A^0.4) and meandered by a Kinoshita sine-generated curve that straightens with slope. Beds are graded to run only downhill and cut as a parabolic channel with faded banks. The water surface is a smooth ribbon at the stage height instead of 1 m squares. The bayou in flat country uses the same machinery. `hf.channels` and the `stage` layer are stored in the library. terrain-0.3.0.
- `creek.png` review render, framed on the widest reach in the middle of the tile. The gallery adds a creek-network sheet for four provinces.
- Lattice detiling of the ground textures (TECHNIQUES §20, after Terrain3D): hashed rotation and offset per lattice node, four corners blended by `(b+s)^8 b`; in the viewer shader and the preview renderer. Leaf flutter in the viewer (after ez-tree): card tips move along their normal, weighted by `1 − v`.
- `scripts/viewer_shot.py`: headless-Chromium screenshot of the three.js viewer for a scene, printing console errors so shader failures show up in review.

**Fixed**
- The viewer's drop-a-GLB overlay never hid after a scene loaded (`display:grid` overrode `[hidden]`), covering the scene. The viewer's opening camera now frames the whole tile instead of starting inside a corner tree's crown.

**Added**
- House siting along the road by a suitability score (flat, dry, a metre above the road, near the creek; after FMG) and invented Southern place names for road, creek, church and homesteads, keyed per scene, in `scene.json` and on `map.png` (TECHNIQUES §19).
- Rounded crown normals and twig-attached leaf cards (TECHNIQUES §18, after ez-tree): canopies shade as one volume; cards no longer float off the wood. `Mesh.nrm` carries authored normals through transforms, the library and the GLB. tree-0.3.1.
- Curved grass blades (two segments, quadratic bend, tapering) that are shorter and bent along the path where trampled (TECHNIQUES §17). Scenes 9.7 / 11.1 / 11.4 MB.

**Fixed**
- Agent ids came from a process-wide counter, so a scene's animals (and their behaviour-clip keys and body looks) changed with how many agents earlier scenes in the same process had made — e.g. in `scripts/gallery.py`. Ids are now the index within the scene.
- Squirrels froze on every routine climb (28 % of their time); they now feed, groom or rest in the canopy and freeze only when they bolted up (TECHNIQUES §16).

**Changed**
- Agents act in a keyed, reshuffled order every step (after Mesa's `shuffle_do`). behavior-0.2.0.

**Added**
- County road with a real surface (TECHNIQUES §15, after Fantasy-Map-Generator routing): Dijkstra on a slope/water cost that halves on existing paths, angle relaxation + Chaikin smoothing, cut-and-fill with crown and ditches, gravel ribbon mesh. Buildings, mailboxes and the fence follow the road's curve; the fence leaves a gate at each walk. New `homestead.png` review render.
- Droplet hydraulic erosion, batched in numpy (TECHNIQUES §14, after Lague): gullies on slopes, filled hollows, creeks follow carved valleys; 0.2 s per tile. terrain-0.2.0. Gallery gains a before/after hillshade sheet.
- Height-blended ground splatting (TECHNIQUES §13, after Terrain3D): per-vertex litter/soil/grass/mud weights from the trail, canopy, grass, water and slope layers; `W_i = (a_i + h_i)^k a_i`; glTF `_SPLAT` attribute + material `extras.splat`, blended in the viewer's fragment shader and in the preview renderer (Gouraud ground).
- `catalog/notes/`: what each of eight studied repos does, its equations, and what is queued from it.
- `docs/gallery/` + `scripts/gallery.py`; `docs/TECHNIQUES.md`.

**Changed**
- Bark is built as chain tubes with shared rings, parallel-transport frames, per-chain side counts and U wraps, ring resampling and tapered tips (TECHNIQUES §4, after ez-tree). All species at `low`: 174k → 79k bark vertices, 152k → 115k triangles; `TWIG_CULL` now differs by detail. Scenes 11.8 / 12.7 / 13.5 → 9.6 / 9.8 / 10.4 MB; library 37.7 → 27.5 MB. tree-0.3.0.
- Broadleaf leaf cards fold along the twig into a shallow V (4 triangles, two-thirds as many cards, cover held), so crowns no longer show flat streaks edge-on. tree-0.2.1; library trees rebuilt.

**Fixed**
- Re-running a scene no longer rewrites its stored behaviour clips (they were deterministic but got new timestamps, churning git).

## 0.2.0 — 2026-10-15 (second session)

**Added**
- Texture pipeline: `Mesh` carries UVs and a texture key; the GLB writer embeds PNG/JPEG images, alpha-masked materials, quantised `TEXCOORD_0` and `KHR_texture_transform` for tiling maps; the preview renderer samples textures with an alpha test.
- `plandscape.textures`: leaf-sprig cards composited from ambientCG leaf atlases (shape-matched per species), pine needle tuft cards, tiling bark and ground detail maps, procedural fallbacks when offline. Textures are grey detail maps, so one leaf texture serves every season.
- `plandscape.models`: glTF importer, crack-free vertex-clustering decimator, whole-card thinning for alpha foliage; 10 Poly Haven models (29 variants) in the library.
- `scene.groundcover`: habitat-driven scatter of stumps, logs, deadfall, mossy rocks, a boulder, ferns and shrubs in the central 80 m, instanced in the GLB.
- `closeup.png` review render; `scene.json` lists ground props and asset credits.
- `plandscape.sources.sites`: licence-gated downloads; both sites probed as CC0 (`catalog/asset_sites.json`).
- Asset CLI: `bake` builds textures, new `bake-models` and `prune`.
- 10 new tests (20 total).

**Changed**
- Broadleaf crowns: kite leaves → cropped sprig cards at half the triangles; pines: per-needle triangles → crossed needle cards. Pines no longer look bare at `detail=low`.
- Bark rings duplicate the seam vertex and get cylindrical UVs along branch arc length.
- GLB: 16-bit indices when possible; tiling UVs quantised to uint16. Three demo scenes: 11.6, 12.3, 13.2 MB.
- Generator versions: tree-0.2.0, texture-0.1.1, model-0.1.3. The library was rebuilt and pruned (36.5 MB).
- Session 1 history imported from the owner's bundle. The 53 non-tree binaries that never reached LFS were regenerated, and the asset commit was rewritten so it doesn't reference the lost objects.

**Fixed**
- Library hits dropped UVs (trees came back untextured).
- Fallback textures could be cached and then reused instead of the real maps.

## 0.1.0 — 2026-10-15 (first session)

**Added**
- Zero-dependency core: purpose-keyed seeding, vectorised noise, mesh container, z-buffered preview renderer.
- Terrain for five Southern provinces (coastal plain, floodplain, Piedmont, Cumberland Plateau, Ridge and Valley) with thermal erosion, D8 creeks, meandering bayous, slope and moisture layers.
- Twelve tree species grown by space colonisation with pipe-model radii, root flare and buttresses, north-side moss, Spanish moss, cypress knees, needle tufts, palm fronds, flowers, seasons and detail levels.
- Ground: province soil colours, litter and pine straw, trampled trails, six grasses with winter dormancy, blade-level grass near the camera.
- Desire paths with the Helbing active-walker model (batched walkers).
- Fauna: deer, gray squirrel, wild turkey, armadillo, coyote, people — needs, personality, memory, utility decisions, A* routes, seeded deviation, flight distance with habituation, flocking, hunting, tree escapes, acorn caching, signs of life.
- Buildings: shotgun house, dogtrot, barn, farmhouse, church; mailbox, fence, clothesline.
- Prompt planner, scene composer, CLI, preview and annotated map.
- GLB writer with instancing, int8 normals and agent animations; structural validator.
- three.js r128 viewer with time-of-day lighting, wind, timeline, follow-cam and event log; base64 fallback for hosts that don't serve `.glb`.
- Content-addressed asset library with search and bake CLI; starter library (96 trees, 11 buildings, 23 bodies, 2 terrain tiles, 17 behaviour clips) in Git LFS.
- License-gated source catalog (23 repos, 10 datasets, 7 papers) and harvester; the probe corrected six guessed licences.
- `procedural-landscape` skill in `.claude/skills/`, `CLAUDE.md`, `HANDOFF.md`, docs and a 10-test suite.

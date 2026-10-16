# Changelog

## Unreleased

**Added**
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

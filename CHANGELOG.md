# Changelog

## Unreleased

**Added**
- Height-blended ground splatting (TECHNIQUES §13, after Terrain3D): per-vertex litter/soil/grass/mud weights from the trail, canopy, grass, water and slope layers; `W_i = (a_i + h_i)^k a_i`; glTF `_SPLAT` attribute + material `extras.splat`, blended in the viewer's fragment shader and in the preview renderer (Gouraud ground).
- `catalog/notes/`: what each of eight studied repos does, its equations, and what is queued from it.
- `docs/gallery/` + `scripts/gallery.py`; `docs/TECHNIQUES.md`.

**Changed**
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

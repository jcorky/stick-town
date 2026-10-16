# Provenance

Code adapted from third-party sources is recorded here: source repo, commit, file, licence, and what was adapted.

| Our file | Source | Commit | Licence | What |
|---|---|---|---|---|
| `plandscape/scene/roads.py: route, smooth` | [Azgaar/Fantasy-Map-Generator](https://github.com/Azgaar/Fantasy-Map-Generator) `src/generators/routes-generator.ts` | 403a670 | MIT | Least-cost routing with a discount on existing routes, sharp-angle relaxation thresholds (re-implemented on a raster grid; no code copied) |
| `plandscape/terrain/erosion.py` | [SebLague/Hydraulic-Erosion](https://github.com/SebLague/Hydraulic-Erosion) `Assets/Scripts/Erosion.cs`, `ComputeShaders/Erosion.compute` | f245576 | MIT | Droplet erosion rules and constants (capacity, deposit/erode, brush weights, speed update), re-implemented batched in numpy |
| `plandscape/flora/tree.py: _chains, _bark_mesh` | [dgreenheck/ez-tree](https://github.com/dgreenheck/ez-tree) `src/lib/tree.js` | dcf309b | MIT | Shared-ring branch tubes, tapered tips, per-branch U wraps (re-implemented on our space-colonisation skeleton; no code copied) |
| `plandscape/textures.py: height_blend`, `viewer/index.html: addSplat` | [TokisanGames/Terrain3D](https://github.com/TokisanGames/Terrain3D) `src/shaders/main.glsl` | 854a457 | MIT | Height-blend weight form $W = (a + h)^k a$ (re-derived for four per-vertex weights; no code copied) |
| `plandscape/textures.py: detile_sample`, `viewer/index.html: detile` | [TokisanGames/Terrain3D](https://github.com/TokisanGames/Terrain3D) `src/shaders/main.glsl` | 854a457 | MIT | Per-node rotation and offset detiling (re-done on a regular lattice with our height-blend weights; no code copied) |
| `viewer/index.html: addWind` (leaf flutter) | [dgreenheck/ez-tree](https://github.com/dgreenheck/ez-tree) `src/lib/tree.js` | dcf309b | MIT | uv.y-weighted three-sine leaf motion (re-written for three.js r128 `onBeforeCompile`; no code copied) |
| `plandscape/terrain/channels.py` | [Mindwerks/worldengine](https://github.com/Mindwerks/worldengine) `worldengine/simulations/erosion.py` | b2adbb6 | MIT | Idea of a non-increasing river bed (re-done as a cumulative minimum along traced reaches; no code copied) |
| `plandscape/terrain/refine.py` | [TokisanGames/Terrain3D](https://github.com/TokisanGames/Terrain3D) `src/terrain_3d_mesher.cpp` | 854a457 | MIT | Idea of nested finer grids where the eye is (re-done as static two-level windows with a faded border; no code copied) |

## Methods from the literature (no code)

- Geometry clipmaps: Losasso & Hoppe (2004), *ACM SIGGRAPH* (ToG 23(3)).
- Priority-Flood + ε: Barnes, Lehman & Mulla (2014), *Computers & Geosciences* 62, 117–127.
- Flat-area drainage away from higher terrain: Garbrecht & Martz (1997), *J. Hydrology* 193, 204–213.
- Rho8 (randomised D8, the inspiration for our jitter): Fairfield & Leymarie (1991), *Water Resources Research* 27(5).
- Hydraulic geometry: Leopold & Maddock (1953), USGS Professional Paper 252.
- Sine-generated meanders: Langbein & Leopold (1966), USGS Professional Paper 422-H; Kinoshita (1961); coefficients after Abad & Garcia (2009), *Water Resources Research* 45.

## Imported assets (all CC0-1.0)

Licences were read from the sites' licence pages by `python3 -m plandscape.sources.sites probe` (evidence in `asset_sites.json`). CC0 needs no attribution; credits are kept anyway, here and in every `scene.json`.

**Poly Haven models** (decimated, texture cut to 512 px; `plandscape/models.py`)

| Model | Role | Authors |
|---|---|---|
| [tree_stump_01](https://polyhaven.com/a/tree_stump_01) | stump | Rob Tuytel |
| [tree_stump_02](https://polyhaven.com/a/tree_stump_02) | stump | Rob Tuytel |
| [dead_tree_trunk](https://polyhaven.com/a/dead_tree_trunk) | log | Rob Tuytel |
| [dead_tree_trunk_02](https://polyhaven.com/a/dead_tree_trunk_02) | log | Jenelle van Heerden, Rico Cilliers |
| [dry_branches_medium_01](https://polyhaven.com/a/dry_branches_medium_01) | deadfall | Rico Cilliers |
| [rock_moss_set_01](https://polyhaven.com/a/rock_moss_set_01) | rock | Kless Gyzen |
| [rock_moss_set_02](https://polyhaven.com/a/rock_moss_set_02) | rock | Kless Gyzen |
| [boulder_01](https://polyhaven.com/a/boulder_01) | boulder | Rico Cilliers |
| [fern_02](https://polyhaven.com/a/fern_02) | fern | Rico Cilliers, Rob Tuytel |
| [shrub_02](https://polyhaven.com/a/shrub_02) | shrub | Rico Cilliers |

**ambientCG textures** (converted to grey detail maps; `plandscape/textures.py`)

| Use | Assets |
|---|---|
| Leaf sprigs | LeafSet001, 003, 004, 010, 016, 018, 022, 024, 029 (photographs of other species, chosen for leaf outline; stand-ins, not botanical records) |
| Pine needles | PineNeedles001 |
| Bark | Bark001, 002, 004, 006, 007, 012, 014 |
| Ground | ScatteredLeaves009, Ground026, Ground036 (Delta alluvium), Ground048, Ground077 (pine straw), Ground080 (Coastal Plain sand), Grass004, Gravel023; Ground078 (session 2, superseded) |

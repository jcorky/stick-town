# Provenance

Code adapted from third-party sources is recorded here: source repo, commit, file, licence, and what was adapted.

| Our file | Source | Commit | Licence | What |
|---|---|---|---|---|
| `plandscape/textures.py: height_blend`, `viewer/index.html: addSplat` | [TokisanGames/Terrain3D](https://github.com/TokisanGames/Terrain3D) `src/shaders/main.glsl` | 854a457 | MIT | Height-blend weight form $W = (a + h)^k a$ (re-derived for four per-vertex weights; no code copied) |

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
| Ground | ScatteredLeaves009, Ground078, Ground048, Grass004 |

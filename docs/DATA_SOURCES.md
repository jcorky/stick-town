# Real-world data (real-place mode — planned)

The procedural core needs no data. To ground a scene in a real place, these public sources stack:

| Layer | Source | Resolution | Terms |
|---|---|---|---|
| Elevation | USGS 3DEP lidar DEMs (The National Map) | ~1 m where lidar exists, coarser elsewhere | US public domain |
| Imagery | USDA NAIP | ~0.6–1 m | US public domain |
| Land cover, canopy | NLCD | 30 m | US public domain |
| Forest composition | USFS FIA plots | plot-level; coordinates fuzzed | US public domain |
| Species reference | Silvics of North America (Ag. Handbook 654); USDA PLANTS | — | US public domain |
| Roads, buildings, paths, water | OpenStreetMap | vector | ODbL (attribution; share-alike for derived databases) |
| Building footprints | Microsoft US Building Footprints | vector | ODbL |

Check resolutions and terms on each source's site before relying on them — they change.

## Flow

1. Resolve the place in the prompt to a bounding box.
2. Fetch the 3DEP DEM tile(s) → `terrain.heightfield.load_dem()` (needs `rasterio`; keep it an optional import).
3. NLCD + FIA county data → biome and species weights for `ScenePlan.trees`.
4. OSM / footprints → buildings, roads, path attractors.
5. Procedural layers add everything below source resolution.

The sandboxed Claude environment usually blocks these hosts, so real-place mode is built and tested on a machine with normal network access. Cache downloaded tiles in the asset library under a `terrain_real` kind keyed by tile id + product version.

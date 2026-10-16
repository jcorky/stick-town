# WorldEngine (Mindwerks, MIT, b2adbb6)

Whole-planet generator; all thresholds are quantiles (`simulations/basic.py:47-85`), so nothing transfers to a single tile directly.

- Temperature (`simulations/temperature.py:79-95`): latitude triangle ×12 + noise, /13, /dist²; above mountains `t *= 1 − (e−mtn)/30`.
- Precipitation (`precipitation.py:194-202`): noise × (t^1.25·0.8 + 0.2).
- Biome (`simulations/biome.py:20-111`): Holdridge-style table, 7 temperature × 8 humidity bands.
- Watermap (`hydrology.py`): 20k droplets split flow over lower neighbours; creek/river/main river = top 5/2/0.7 %.
- Rivers (`erosion.py`): D4 descent, sources with flow ≥ 0.02 spaced ≥ 9 cells, A* to lower cell or lake;
  `cleanUpFlow` makes beds non-increasing downstream; valley carve `e += (e_river − e)·{0.2, 0.05}` at radius 1, 2.

**Queued:** Holdridge lookup fed with *physical* values (latitude + lapse-rate temperature + sourced precipitation
normals) for real-place mode; monotone-bed cleanup + valley carve for our D8 creeks. Humidity sign quirk: don't copy.

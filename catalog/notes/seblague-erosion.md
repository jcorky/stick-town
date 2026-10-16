# Hydraulic-Erosion (SebLague, MIT, f245576)

Droplet erosion. CPU `Assets/Scripts/Erosion.cs`, GPU `ComputeShaders/Erosion.compute`.

- Droplet: pos, dir = 0, speed = 1, water = 1, sediment = 0; lifetime 30 steps; moves exactly 1 cell per step.
- Gradient (bilinear, `:130-153`): `gx = (NE−NW)(1−y) + (SE−SW)y`, `gy = (SW−NW)(1−x) + (SE−NE)x`.
- Inertia: `dir = dir·inertia − g·(1−inertia)`, normalise (GPU: `len = max(0.01, len)`).
- Capacity: `cap = max(−Δh·speed·water·C, 0.01)`, C = 4 (CPU) / 3 (GPU).
- Deposit if `sediment > cap` or uphill: `min(Δh, sediment)` uphill else `(sediment−cap)·0.3`, bilinear to 4 corners.
- Erode: `min((cap−sediment)·0.3, −Δh)` over a brush r = 3, weights `1 − d/r` normalised (25 points).
- `speed = sqrt(max(0, speed² + Δh·4))`; `water *= 0.99`. Inertia 0.05 (CPU) / 0.3 (GPU).

**Pitfalls for our port:** heights ~0..1 there (×10 at mesh time) → normalise our metres or retune C; per-node clamp
assumes h ≥ 0; pad by r and crop; batch droplets with `np.bincount` scatter; keyed spawn jitter; apron ~8 m for seams.
**Queued:** terrain priority 1, after thermal erosion and before D8. Expect gullies, filled hollows, small fans.

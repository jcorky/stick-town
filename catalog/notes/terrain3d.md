# Terrain3D (TokisanGames/Terrain3D, MIT, 854a457)

Godot terrain plugin. Shaders in `src/shaders/`.

- **Control map** (`doc/docs/controlmap_format.md`, `main.glsl:29-36`): one uint32 per 1 m vertex — base id (5 bits),
  overlay id (5), blend (8, /255), UV angle (4, step −τ/16), UV scale (3), flags. Up to 4 textures meet per cell.
- **Height blend** (`main.glsl:308, 350, 395`): `k = 4 + 60·sharpness` (default 34); `W = (b + t + h·s)^k · b`,
  normalised. b = bilinear corner weight, t = blend weight, h = albedo-alpha height, s = up-component of the base
  normal (overlays fill crevices).
- **Auto shader** (`auto_shader.glsl:17-18`): `blend = clamp(2·auto_slope·(n.y−1) + 1 − 0.01·reduction·y, 0, 1)`.
- **Detiling** (`main.glsl:322-345`): per-vertex hash r → rotation `(2r−1)·detile.x·τ`, offset `(2r−1)·detile.y·τ`,
  hidden by the height blend between corners. Derivatives/normals counter-rotated.
- **Steep slopes** (`projection.glsl:6-18`): not triplanar; one planar projection snapped to 8 directions when n.y ≤ √½.
- **Macro variation** (`macro_variation.glsl:20-24`): two low-freq noise samples, `albedo *= mix(1, macrov, clamp(n.y+slope))`.
- **Ocean shader** (`extras/shaders/ocean_shader.gdshader`): depth fade `mix(bg, water, clamp(d/D)^c)`, shore alpha
  `1 − shore_mask`, foam `clamp(shore·I·noise·1.5 − h)`.

**Adopted:** height-blend form for our 4-weight splat (TECHNIQUES §13, `textures.height_blend`, viewer `addSplat`).
**Adopted (session 3):** lattice detiling — hashed rotation + offset per 1.5-tile node, four corners blended with the
height-blend weight `(b+s)^8 b` (TECHNIQUES §20; GLSL `detile` in the viewer, `textures.detile_sample` in numpy).
**Queued:** macro tint; snapped side projection on
slopes > 45°; baked depth-tinted water (we know depth on the CPU).

**Clipmap (studied session 3):** `src/terrain_3d_mesher.cpp:17-36` builds the camera-following clipmap from block
meshes: `mesh_size²` tiles, 2-wide EDGE strips that bridge LOD rings, 4-wide FILL strips, TRIM strips for LOD 0;
rings double in spacing outward and snap to the target (`terrain_3d.h:72-74`, `_clipmap_target`).
**Adopted (§22), our way:** a static scene needs no moving rings, so two levels only: the 1 m tile plus fine windows
(25 cm at `low`) placed on the focus and the creek. Instead of edge/trim strips we fade the fine detail to the
coarse bilinear surface over a 2 m border (τ), so fine border vertices lie on coarse edges and need no bridge mesh.


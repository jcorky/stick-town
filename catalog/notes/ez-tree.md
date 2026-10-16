# ez-tree (dgreenheck, MIT, dcf309b)

Recursive three.js tree generator. `src/lib/tree.js`, defaults `options.js:39-125`, presets `presets/*.json`.

- Per level: length, radius, sections, segments, taper, gnarliness, twist, angle, children, start. Breadth-first queue.
- Radius per ring: deciduous `r·(1 − taper·i/N)`, last ring of last level 0.001 (pointed tips).
- Gnarliness `g = max(1, 1/√r)·gnarliness`, Euler ±g per section; tropism `min(angle, strength/r)` → thin wood bends more.
- Children stratified `t = start + (i + U)(1 − start)/count`; Fisher-Yates slot shuffle for azimuth.
- **Geometry:** one swept tube per branch, consecutive rings shared, U wraps `max(1, round(r_base·scale))` constant per
  branch; V ping-pongs (mirrors) per section — our arc-length V is better.
- **Budget:** sides 8–12 / 5–6 / 3–4 / 3 by level, rings fixed per branch (12–16 trunk); bark 2.5k–12k tris per tree.
- Leaves: last level only, size `·(1 ± 0.7)`, rounded normals `n = normalize(n_face + (v − origin))`, alphaTest 0.5,
  wind weighted by uv.y: `0.5 sin(ωt+φ) + 0.3 sin(2ωt+1.3φ) + 0.2 sin(5ωt+1.5φ)`.
- LOD: ring stride 3 / 6, segment factor 0.75 / 0.4 at 100 / 250 m.

**Measured on ours:** live oak bark 45k tris / 52.5k verts (~1.5 MB) because every ~0.3 m skeleton segment is its own
tube with two private rings (3,801 tubes); low and med bark identical (TWIG_CULL below the minimum radius).
**Queued (priority order):** (1) chain tubes with shared rings, parallel-transport frames
`u' = normalize(u − (u·t')t')`, per-chain U wraps → ~27k verts; (2) sides 8/6/4/3, tapered tips
`r(s) = r_base(1 − 0.7 s/L)`, TWIG_CULL 0.03/0.015; (3) rounded card normals + twig-attached cards.
**Adopted (session 2):** (1) and (2): chains via thickest child, shared rings, parallel transport, per-chain U wraps,
ring resampling Δs = clip(8r, 0.3, 1.5) m or > 12° bend, sides 10/8/5/3 (8/6/4/3 looked boxy on live-oak limbs),
tip taper 0.5 r (0.3 read as thorns in winter), TWIG_CULL 0.03/0.015/0.006/0. Bark verts −55 %, tris −24 %.
(3) adopted too: rounded normals `normalize(0.65 r̂ + 0.35 s n_face)` (ez-tree adds n_face + (v − origin));
anchors along the parent→node segment, spread N(0, 0.12 L). Still queued: uv.y-weighted wind in the viewer.
**We do better:** arc-length bark V, lobed flare, north moss, crown envelopes, pipe radii, folded cards.

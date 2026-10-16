# ocean (jbouny/ocean, MIT, d5e5f4b)

three.js mirror-reflection ocean. `water-material.js:122-126`: `reflectance = 0.3 + 0.7(1−cosθ)³`,
`scatter = max(0, n·v)·waterColor` (0x001e0f). Mirror render target and animated normals can't live in glTF;
only colour choices carry over. For creeks use the Terrain3D ocean ideas instead, baked on the CPU:
`f = clamp(d/D)^c`, `COLOR_0 = mix(shallow, deep, f)`, alpha `0.15 + 0.85f`, foam band where d < 0.3 m.

// Coat detail (TECHNIQUES §37): fur strands, feather scallops, shell scutes and a gobbler's iridescence, drawn per
// fragment from the _COAT vertex attribute (plandscape/fauna/coat.py) on the sculpted bodies' standard material.
//
//   _COAT = (kind/8, size/S_MAX, sheen, iridescence), u8 normalised; kind 0 bare, 1 fur, 2 feather, 3 shell,
//   4 fur lying along the part's z (legs)
//   fur      albedo × (0.74 + 0.52 n₆)(0.72 + 0.56 S(n)),  n value noise stretched 8× along the hair (object −x), n₆ tufts 6× larger
//   feather  staggered rows of discs: d = |frac(q) − (0, ½)|, pale band where 0.32 < d < 0.47, dark rim at d → ½
//   shell    Worley cells: seam where F2 − F1 → 0, a tone per cell
//   sheen    albedo × (1 + s (1 − n·v)³)
//   irid     thin-film-like hue h = ½ + ½ cos 2π (φ + 1.6 n·v), mixed toward a bronze-green tint by w
// Detail fades out once a feature is smaller than a pixel (fwidth), so it never shimmers.
(function (root) {
  const C = { uniforms: { uCoat: { value: 1.0 } } };

  C.glsl = `
  float cHash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
  vec3 cHash3(vec3 p) { return fract(sin(vec3(dot(p, vec3(127.1, 311.7, 74.7)), dot(p, vec3(269.5, 183.3, 246.1)),
                                            dot(p, vec3(113.5, 271.9, 124.6)))) * 43758.5453); }
  float cNoise(vec3 x) {
    vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(cHash(i), cHash(i + vec3(1, 0, 0)), f.x), mix(cHash(i + vec3(0, 1, 0)), cHash(i + vec3(1, 1, 0)), f.x), f.y),
               mix(mix(cHash(i + vec3(0, 0, 1)), cHash(i + vec3(1, 0, 1)), f.x), mix(cHash(i + vec3(0, 1, 1)), cHash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
  }
  // one row-staggered disc pattern in the plane q; returns (pale band, dark rim)
  vec2 cScallop(vec2 q) {
    q.y += 0.5 * floor(q.x);
    float d = length(fract(q) - vec2(0.0, 0.5));
    d = min(d, length(fract(q) - vec2(1.0, 0.5)));
    return vec2(smoothstep(0.30, 0.40, d) * (1.0 - smoothstep(0.44, 0.48, d)), smoothstep(0.44, 0.5, d));
  }
  void coatSurface(inout vec4 dc, inout float rough, vec3 n, vec3 v) {
    float kind = floor(vCoat.x * 8.0 + 0.5);
    if (kind < 0.5 || uCoat <= 0.0) return;
    float s = max(vCoat.y * 0.05, 1e-4);
    vec3 p = vObj / s;
    float px = length(fwidth(p));
    float fade = uCoat * (1.0 - smoothstep(0.35, 1.2, px));
    float ndv = clamp(dot(n, v), 0.0, 1.0), rim = pow(1.0 - ndv, 3.0);
    vec3 c = dc.rgb;
    if (kind < 1.5 || kind > 3.5) {   // fur: strands, and tufts 6× larger that still read at a distance
      if (kind > 3.5) p = p.zyx;      // legs: the hair lies along the limb
      float st = 0.65 * cNoise(vec3(p.x * 0.125, p.y, p.z)) + 0.35 * cNoise(vec3(p.x * 0.25, p.y * 2.0, p.z * 2.0) + 7.0);
      float tuft = cNoise(vec3(p.x * 0.042, p.y * 0.167, p.z * 0.167) + 3.0);
      float fadeT = uCoat * (1.0 - smoothstep(0.35, 1.2, px / 6.0));
      st = smoothstep(0.25, 0.75, st);
      c *= mix(1.0, 0.74 + 0.52 * tuft, fadeT) * mix(1.0, 0.72 + 0.56 * st, fade);
      c *= 1.0 + vCoat.z * rim * 0.9;
      rough = max(rough, 0.85);
    } else if (kind < 2.5) {   // feathers: tri-planar, each plane's rows pointing back along −x
      vec3 w = abs(normalize(vObjN)); w = w * w; w /= (w.x + w.y + w.z);
      vec2 a = cScallop(vec2(-p.x, p.z) * vec2(1.0, 1.3)), b = cScallop(vec2(-p.x, p.y) * vec2(1.0, 1.3)),
           e = cScallop(vec2(p.y, p.z) * 1.3);
      vec2 sc = a * w.y + b * w.z + e * w.x;
      float band = sc.x * fade, edge = sc.y * fade;
      c = mix(c, c * 1.6 + 0.04, band * 0.45);
      c *= 1.0 - 0.35 * edge;
      c *= 1.0 + vCoat.z * rim * 0.6;
      vec3 film = 0.5 + 0.5 * cos(6.2832 * (vec3(0.0, 0.33, 0.67) + 1.6 * ndv + 0.15));
      vec3 tint = mix(vec3(0.85, 0.50, 0.20), film * vec3(0.6, 0.95, 0.5), 0.35);   // bronze, green at grazing
      float L = dot(c, vec3(0.3, 0.59, 0.11));
      c = mix(c, tint * max(2.4 * L, 0.06), vCoat.w * 0.6 * clamp(0.15 + 0.5 * rim + 0.9 * band, 0.0, 1.0));
      rough = mix(rough, 0.5, vCoat.w);
    } else {                   // shell and scales: Worley cells
      vec3 g = floor(p), f = fract(p);
      float d1 = 8.0, d2 = 8.0; vec3 id = g;
      for (int k = 0; k < 27; k++) {
        vec3 o = vec3(float(k / 9) - 1.0, float((k / 3) - 3 * (k / 9)) - 1.0, float(k - 3 * (k / 3)) - 1.0);
        float d = length(o + cHash3(g + o) - f);
        if (d < d1) { d2 = d1; d1 = d; id = g + o; } else if (d < d2) d2 = d;
      }
      float seam = 1.0 - smoothstep(0.0, 0.12, d2 - d1);
      c *= mix(1.0, (0.88 + 0.24 * cHash(id)) * (1.0 - 0.45 * seam), fade);
      rough = mix(rough, 0.55, 0.5);
    }
    dc.rgb = c;
  }`;

  C.patch = function (mat) {
    if (mat.userData.coatDone) return mat;
    mat.extensions = Object.assign(mat.extensions || {}, { derivatives: true });
    const prev = mat.onBeforeCompile;
    mat.onBeforeCompile = (sh, r) => {
      if (prev) prev(sh, r);
      sh.uniforms.uCoat = C.uniforms.uCoat;
      sh.vertexShader = 'attribute vec4 _coat;\nvarying vec4 vCoat;\nvarying vec3 vObj;\nvarying vec3 vObjN;\n' +
        sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n vCoat = _coat; vObj = position; vObjN = normal;');
      sh.fragmentShader = 'uniform float uCoat;\nvarying vec4 vCoat;\nvarying vec3 vObj;\nvarying vec3 vObjN;\n' + C.glsl + '\n' +
        sh.fragmentShader.replace('#include <lights_physical_fragment>',
          'coatSurface(diffuseColor, roughnessFactor, normal, normalize(vViewPosition));\n#include <lights_physical_fragment>');
    };
    mat.customProgramCacheKey = () => 'coat';
    mat.userData.coatDone = true;
    mat.needsUpdate = true;
    return mat;
  };

  // every mesh that carries the attribute: the fauna materials (fauna_0..2) are shared, so each is patched once
  C.apply = function (root3d) {
    let n = 0;
    root3d.traverse((o) => { if (o.isMesh && o.geometry.attributes._coat) { C.patch(o.material); n++; } });
    return n;
  };

  root.Coat = C;
  if (typeof module !== 'undefined') module.exports = C;
})(typeof window !== 'undefined' ? window : globalThis);

// Wind for the viewer (docs/TECHNIQUES.md §34). Mirrors plandscape/wind/{field,sway}.py: the same gust field
// (a sum of travelling sinusoids), the same damped-oscillator transfer functions, evaluated per vertex in the
// shader with no state, so scrubbing time and Python's reference agree. CPU functions (gust, at) serve the
// animals' senses (scent drift, wind noise).
(function (root) {
  const TAU = 6.283185307179586;
  const W = {
    json: null, C: null, n: 0, ratio: 1, force: 3, fromDeg: 180,
    uniforms: {
      uTime: { value: 0 }, uDir: { value: [0, 1] }, uUh: { value: 2 }, uUc: { value: 2 },
      uF: { value: [] }, uAU: { value: [] }, uAV: { value: [] }, uPU: { value: [] }, uPV: { value: [] },
      uLU: { value: [] }, uLV: { value: [] },
      uTrail: { value: null }, uTrailXf: { value: [0, 0, 1, 1] },   // live trampling (player.js), grass only
    },
  };

  W.init = function (json) {
    W.json = json; W.C = json.constants; W.n = json.f.length;
    for (const [u, k] of [['uF', 'f'], ['uAU', 'au'], ['uAV', 'av'], ['uPU', 'pu'], ['uPV', 'pv'], ['uLU', 'lu'], ['uLV', 'lv']])
      W.uniforms[u].value = json[k].slice();
    W.ratio = json.Uh / Math.max(json.U10, 1e-6);
    if (typeof THREE !== 'undefined' && !W.uniforms.uTrail.value) {   // nothing trodden yet: one black texel
      W.uniforms.uTrail.value = new THREE.DataTexture(new Uint8Array([0]), 1, 1, THREE.LuminanceFormat);
      W.uniforms.uTrail.value.needsUpdate = true;
    }   // every profile step is linear in U10, so U_h/U10 is fixed
    W.setForce(json.force); W.setFrom(json.from_deg);
  };
  W.beaufortU10 = function (F) {
    const B = W.C.BEAUFORT, lo = Math.max(0, Math.min(12, Math.floor(F))), hi = Math.max(0, Math.min(12, Math.ceil(F)));
    return lo === hi ? B[lo] : B[lo] + (B[hi] - B[lo]) * (F - lo);
  };
  W.setForce = function (F) {
    W.force = F; W.U10 = W.beaufortU10(F);
    W.uniforms.uUh.value = Math.max(W.U10 * W.ratio, 0.05);
    W.uniforms.uUc.value = W.uniforms.uUh.value;    // CONVECTION = 1: gusts travel at the canopy-top mean speed
  };
  W.setFrom = function (deg) {
    W.fromDeg = deg; const a = deg * Math.PI / 180;
    W.uniforms.uDir.value = [-Math.sin(a), -Math.cos(a)];
  };
  W.dir = () => W.uniforms.uDir.value;

  // ── CPU mirror (world x east, y north) ──
  W.phases = function (x, y, t) {
    const [dx, dy] = W.dir(), Uc = W.uniforms.uUc.value, j = W.json;
    const xi = x * dx + y * dy, eta = -x * dy + y * dx, tu = [], tv = [];
    for (let k = 0; k < W.n; k++) {
      const w = TAU * j.f[k] * (t - xi / Uc);
      tu.push(w - j.lu[k] * eta + j.pu[k]); tv.push(w - j.lv[k] * eta + j.pv[k]);
    }
    return [tu, tv];
  };
  W.gust = function (x, y, t) {
    const [tu, tv] = W.phases(x, y, t); let u = 0, v = 0;
    for (let k = 0; k < W.n; k++) { u += W.json.au[k] * Math.cos(tu[k]); v += W.json.av[k] * Math.cos(tv[k]); }
    return [u, v];
  };
  // mean speed at height z with local canopy cover c (field.Wind.mean_speed, scaled to the current force)
  W.meanSpeed = function (z, c) {
    const j = W.json, k = 0.41, s = W.U10 / Math.max(j.U10, 1e-6), Z0 = 0.03;
    const ustar = j.ustar * s, d = j.d, z0 = j.z0, h = j.canopy_h, Uh = W.uniforms.uUh.value;
    const above = ustar / k * Math.log(Math.max(Math.max(z, d + z0 * 1.01) - d, z0 * 1.0001) / z0);
    const inside = Uh * Math.exp(j.a * (Math.min(z, h) / h - 1));
    const forest = z >= h ? above : inside;
    const uo = k * W.U10 / Math.log(10 / Z0), open = uo / k * Math.log(Math.max(z, Z0 * 1.01) / Z0);
    c = Math.min(Math.max(c, 0), 1);
    return (1 - c) * open + c * forest;
  };
  W.at = function (x, y, z, t, c = 1) {
    const U = W.meanSpeed(z, c), [gu, gv] = W.gust(x, y, t), [dx, dy] = W.dir();
    const a = U * Math.max(1 + gu, 0), b = U * gv;
    return [a * dx - b * dy, a * dy + b * dx];
  };

  // ── GLSL ──
  W.glslCommon = function () {
    const C = W.C, f = (v) => Number(v).toFixed(6);
    return `
      #define NW ${W.n}
      uniform float uTime, uUh, uUc; uniform vec2 uDir;
      uniform float uF[NW], uAU[NW], uAV[NW], uPU[NW], uPV[NW], uLU[NW], uLV[NW];
      uniform sampler2D uTrail; uniform vec4 uTrailXf;
      // F ∝ U² (1 + U/U0)^b: gain relative to U_REF, and its log-slope β
      float windGain(float U) { return pow(U / ${f(C.U_REF)}, 2.0) * pow((1.0 + U / ${f(C.U0)}) / ${f(1 + C.U_REF / C.U0)}, ${f(C.VOGEL_B)}); }
      float windBeta(float U) { float x = U / ${f(C.U0)}; return 2.0 + ${f(C.VOGEL_B)} * x / (1.0 + x); }
      // response (r_u, r_v) of an oscillator (fn, zeta) at world point p (x east, y north)
      vec2 windModal(vec2 p, float fn, float zeta, float decor, float ell) {
        float xi = dot(p, uDir), eta = dot(p, vec2(-uDir.y, uDir.x));
        vec2 r = vec2(0.0);
        for (int k = 0; k < NW; k++) {
          float rr = uF[k] / max(fn, 1e-3), a = 1.0 - rr * rr, b = 2.0 * zeta * rr;
          float g = inversesqrt(a * a + b * b), psi = atan(b, a);
          float ex = ell > 0.0 ? 6.2831853 * decor * (1.0 - exp(-${f(C.DAVENPORT_CY)} * uF[k] * ell / uUc)) : 0.0;
          float w = 6.2831853 * uF[k] * (uTime - xi / uUc) - psi + ex;
          r.x += uAU[k] * g * cos(w - uLU[k] * eta + uPU[k]);
          r.y += uAV[k] * g * cos(w - uLV[k] * eta + uPV[k]);
        }
        return r;
      }
      vec3 windObj(vec3 g) {  // a world (glTF) direction in this object's frame (rotation + uniform scale)
        return normalize(vec3(dot(modelMatrix[0].xyz, g), dot(modelMatrix[1].xyz, g), dot(modelMatrix[2].xyz, g)));
      }`;
  };
  // trees, their impostors: trunk mode + limb + branch + leaf (sway.displace)
  W.glslTree = function () {
    const C = W.C, f = (v) => Number(v).toFixed(6);
    return `
      vec3 wpos = (modelMatrix * vec4(position, 1.0)).xyz;
      vec2 vxy = vec2(wpos.x, -wpos.z), bxy = vec2(modelMatrix[3].x, -modelMatrix[3].z);
      float wsc = length(modelMatrix[0].xyz);
      vec3 wo = windObj(vec3(uDir.x, 0.0, -uDir.y)), po = windObj(vec3(-uDir.y, 0.0, -uDir.x));
      float wU = uUh * uTree.w, wG = windGain(wU), wB = windBeta(wU);
      vec2 rt = windModal(bxy, uTree.x, uTree.y, 0.0, 0.0);
      vec3 dsp = _wind0.x * uTree.z * wG * ((1.0 + wB * rt.x) * wo + rt.y * po);
      vec3 ax = normalize(_wind1.xyz + vec3(0.0, 1e-4, 0.0));
      vec3 perp = wo - dot(wo, ax) * ax;
      float d1 = ${f(C.D_MAX)} * _wind0.y * _wind0.y, d2 = ${f(C.D_MAX)} * _wind0.z * _wind0.z;
      if (d1 > 0.0) dsp += d1 * wG * (1.0 + wB * windModal(vxy, max(${f(C.F1_MAX)} * _wind2.x / wsc, 0.05), ${f(C.ZETA_BRANCH)}, 0.5 * (_wind1.w + 1.0), ${f(C.LIMB_L)}).x) * perp;
      if (d2 > 0.0) dsp += d2 * wG * (1.0 + wB * windModal(vxy, max(${f(C.F2_MAX)} * _wind2.y / wsc, 0.05), ${f(C.ZETA_BRANCH)}, _wind2.z, ${f(C.BRANCH_L)}).x) * perp;
      float lever = ${f(C.L_MAX)} * _wind0.w;
      if (lever > 0.0) {
        float al = ${f(C.ALPHA_MAX)} * (1.0 - exp(-wU / ${f(C.U_ALPHA)})), af = ${f(C.FLUTTER_A)} * min(wU / ${f(C.U_FLUTTER)}, 1.0);
        float fl = sin(6.2831853 * ${f(C.FLUTTER_HZ)} * uTime + 6.2831853 * _wind2.w);
        dsp += lever * (sin(al) * wo + af * fl * normal);
      }
      dsp.y -= 0.5 * (dsp.x * dsp.x + dsp.z * dsp.z) / max(position.y, 1.0);
      transformed += dsp;`;
  };
  // grass blades, world space (sway.grass)
  W.glslGrass = function () {
    const C = W.C, f = (v) => Number(v).toFixed(6);
    return `
      vec2 vxy = vec2(position.x, -position.z);
      float gU = uUh * 2.0 * _wind0.y, gC = (gU / ${f(C.GRASS_U0)}) * (gU / ${f(C.GRASS_U0)});
      vec2 rg = windModal(vxy, ${f(C.GRASS_HZ)}, ${f(C.ZETA_GRASS)}, _wind0.w, 0.3);
      float bend = ${f(C.GRASS_BETA)} * gC / (1.0 + gC);
      float beta = clamp(bend * (1.0 + 2.0 * rg.x), 0.0, 1.45), side = bend * rg.y;
      // blades the player has trodden lie over and shorten (the baked trail is already in the geometry)
      float trod = texture2D(uTrail, (vxy - uTrailXf.xy) / uTrailXf.zw).r;
      bend += (1.3 - bend) * trod; beta = max(beta, bend);
      float hh = _wind0.x * _wind0.z * (1.0 - 0.45 * trod);
      vec2 dxy = hh * (sin(beta) * uDir + sin(side) * vec2(-uDir.y, uDir.x));
      transformed += vec3(dxy.x, -hh * (1.0 - cos(beta)), -dxy.y);`;
  };
  // ground props without attributes (ferns, shrubs): a low cantilever, height from the object frame
  W.glslProp = function () {
    return `
      vec2 bxy = vec2(modelMatrix[3].x, -modelMatrix[3].z);
      vec3 wo = windObj(vec3(uDir.x, 0.0, -uDir.y));
      float pU = uUh * 0.35, ph = clamp(position.y / 1.5, 0.0, 1.0);
      vec2 rp = windModal(bxy, 1.2, 0.15, 0.0, 0.0);
      transformed += ph * ph * 0.12 * windGain(pU) / max(windGain(4.0), 1e-3) * (1.0 + windBeta(pU) * rp.x) * wo;`;
  };

  // patch a material: kind = 'tree' | 'grass' | 'prop'; tree materials get their own uTree (f0, ζ, Q, shelter)
  W.patch = function (mat, kind, tree) {
    const body = { tree: W.glslTree, grass: W.glslGrass, prop: W.glslProp }[kind]();
    const prevCompile = mat.onBeforeCompile;
    const uTree = { value: tree ? [tree.f0, tree.zeta, tree.Q, tree.shelter] : [0, 0, 0, 0] };
    mat.onBeforeCompile = (sh, r) => {
      if (prevCompile) prevCompile(sh, r);
      Object.assign(sh.uniforms, W.uniforms, { uTree });
      sh.vertexShader = 'attribute vec4 _wind0;\nattribute vec4 _wind1;\nattribute vec4 _wind2;\nuniform vec4 uTree;\n' +
        W.glslCommon() + '\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n' + body);
    };
    mat.customProgramCacheKey = () => 'wind-' + kind;
    mat.needsUpdate = true;
    return mat;
  };

  root.Wind = W;
  if (typeof module !== 'undefined') module.exports = W;
})(typeof window !== 'undefined' ? window : globalThis);

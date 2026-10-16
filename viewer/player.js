// Walk into the scene (docs/TECHNIQUES.md §35). The player is a person the animals can see, hear and smell:
// sight by motion, posture, cover and light; hearing by footsteps and claps against the wind's noise; smell by a
// plume the wind field carries. Animals that notice take over from their baked clip and answer live: they look,
// stomp, putt, flag, freeze, flee, climb, fly or shut in; they habituate to a quiet visitor, are sensitised by a
// loud one, and come to food. People keep Hall's distances, greet, and follow the paths the player wears.
(function () {
  const G2 = (x, y, z) => new THREE.Vector3(x, z, -y);          // world (x east, y north, z up) → glTF
  const TAU = Math.PI * 2;
  const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
  const clamp = (x, a, b) => Math.min(Math.max(x, a), b);
  const pitchQ = (th, q) => q.set(0, 0, Math.sin(th / 2), Math.cos(th / 2));   // gltf.pitch_quat
  const yawQ = (th, q) => q.set(0, Math.sin(th / 2), 0, Math.cos(th / 2));     // gltf.yaw_quat

  // ── the world the player and live animals walk on (world.bin, written by compose.write_world) ──
  const World = {
    load(meta, buf) {
      this.meta = meta; [this.ny, this.nx] = meta.shape; this.res = meta.res; [this.ox, this.oy] = meta.origin;
      this.L = {};
      for (const [k, v] of Object.entries(meta.layers)) {
        const n = this.nx * this.ny;
        this.L[k] = v.dtype === 'float32' ? new Float32Array(buf, v.offset, n)
          : Float32Array.from(new Uint8Array(buf, v.offset, n), (b) => b / 255);
      }
      this.base = Float32Array.from(this.L.trail);      // the baked trail, to show only what the player adds
      this.comfort = Float32Array.from(this.L.trail); this.blur(); return this;
    },
    get(k, x, y) { return this.sampleArr(this.L[k], x, y); },
    sampleArr(A, x, y) {   // bilinear, clamped
      const gx = clamp((x - this.ox) / this.res, 0, this.nx - 1.001), gy = clamp((y - this.oy) / this.res, 0, this.ny - 1.001);
      const i = Math.floor(gy), j = Math.floor(gx), fy = gy - i, fx = gx - j, n = this.nx;
      return (A[i * n + j] * (1 - fx) + A[i * n + j + 1] * fx) * (1 - fy) + (A[(i + 1) * n + j] * (1 - fx) + A[(i + 1) * n + j + 1] * fx) * fy;
    },
    z(x, y) { return this.get('z', x, y); },
    inside(x, y, m = 1) { return x > this.ox + m && y > this.oy + m && x < this.ox + (this.nx - 1) * this.res - m && y < this.oy + (this.ny - 1) * this.res - m; },
    ground(x, y) {
      if (this.get('water', x, y) > 0.5) return 'water';
      if (this.get('trail', x, y) > 0.35) return 'trail';
      return this.get('grass', x, y) > 0.3 ? 'grass' : 'litter';
    },
    deposit(x, y, amount) {   // desire.TrailField.deposit: G += a (1 − G)
      const j = Math.round((x - this.ox) / this.res), i = Math.round((y - this.oy) / this.res);
      if (i < 0 || j < 0 || i >= this.ny || j >= this.nx) return;
      const k = i * this.nx + j; this.L.trail[k] += amount * (1 - this.L.trail[k]); this.dirty = true;
    },
    blur() {  // comfort V = G blurred by σ = 2.5 m (what walkers see), separable box³ ≈ Gaussian
      const n = this.nx, m = this.ny, r = Math.max(1, Math.round(2.5 / this.res)), a = Float32Array.from(this.L.trail), b = new Float32Array(a.length);
      for (let pass = 0; pass < 3; pass++) {
        for (let i = 0; i < m; i++) { let s = 0; for (let j = -r; j <= r; j++) s += a[i * n + clamp(j, 0, n - 1)];
          for (let j = 0; j < n; j++) { b[i * n + j] = s / (2 * r + 1); s += a[i * n + clamp(j + r + 1, 0, n - 1)] - a[i * n + clamp(j - r, 0, n - 1)]; } }
        for (let j = 0; j < n; j++) { let s = 0; for (let i = -r; i <= r; i++) s += b[clamp(i, 0, m - 1) * n + j];
          for (let i = 0; i < m; i++) { a[i * n + j] = s / (2 * r + 1); s += b[clamp(i + r + 1, 0, m - 1) * n + j] - b[clamp(i - r, 0, m - 1) * n + j]; } }
      }
      this.comfort = a;
    },
    coverTau(x0, y0, x1, y1, layer = 'cover') {   // ∫ cover ds along a line, and metres of foliage
      const d = Math.hypot(x1 - x0, y1 - y0), n = Math.max(2, Math.ceil(d / 2)); let tau = 0, fol = 0;
      for (let k = 1; k < n; k++) { const u = k / n, x = x0 + u * (x1 - x0), y = y0 + u * (y1 - y0);
        tau += this.get(layer, x, y) * d / n; fol += (this.get('canopy', x, y) > 0.5 ? d / n : 0); }
      return [tau, fol];
    },
  };

  const Play = { on: false, t: 0, minds: [], foods: [], rings: [], scent: [], showScent: true, events: [] };

  // ── the player's body: a simple person, legs and arms swinging by the same stride law as the animals ──
  function makeAvatar() {
    const g = new THREE.Group(), mat = (c) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.8 });
    const shirt = mat(0xb5562a), jeans = mat(0x34415a), skin = mat(0xd9a77f);
    const box = (w, h, d, m) => { const o = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); o.castShadow = true; return o; };
    const hips = new THREE.Group(); hips.position.y = 0.92; g.add(hips);
    const torso = box(0.38, 0.6, 0.22, shirt); torso.position.y = 0.3; hips.add(torso);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12), skin); head.position.y = 0.75; head.castShadow = true; hips.add(head);
    const limb = (x, y, len, w, m) => { const p = new THREE.Group(); p.position.set(0, y, x); const b = box(w, len, w, m); b.position.y = -len / 2; p.add(b); hips.add(p); return p; };
    g.userData = { hips, torso, head, legL: limb(-0.1, 0, 0.9, 0.13, jeans), legR: limb(0.1, 0, 0.9, 0.13, jeans),
                   armL: limb(-0.25, 0.56, 0.62, 0.09, shirt), armR: limb(0.25, 0.56, 0.62, 0.09, shirt) };
    return g;
  }

  Play.init = function (opts) {
    Object.assign(Play, opts);  // scene, camera, controls, sceneInfo, agents, log, lighting
    const s = Play.sceneInfo;
    Life.init(s.perception);
    Play.avatar = makeAvatar(); Play.avatar.visible = false; Play.scene.add(Play.avatar);
    const S = (World.nx - 1) * World.res;
    Play.p = { x: World.ox + S / 2 + 3, y: World.oy + S / 2 - 6, h: Math.PI / 2, v: 0, phase: 0, mode: 'walk', posture: 'stand', target: null };
    Play.trees = (s.trees || []).map((t) => ({ x: t.x, y: t.y, r: 0.5 }));
    Play.minds = Play.agents.map((node) => {
      const rig = (node.userData && node.userData.rig) || {}, sp = node.name.replace(/_\d+$/, '');
      const body = node.children[0], byName = (n) => body && body.children.find((c) => c.name === n);
      const legs = (rig.legs || []).map((_, i) => { const th = byName('leg' + i); return { th, sh: th && th.children.find((c) => c.name === 'shank' + i) }; });
      return { node, sp, rig, mind: new Life.Mind(sp), live: false, body, neck: byName('neck'), tail: byName('tail'),
               torso: byName('torso'), wings: [0, 1].map((i) => byName('wing' + i)).filter(Boolean), legs,
               x: 0, y: 0, h: 0, alt: 0, v: 0, phase: 0, look: 0, cue: '', act: 'idle', actT: 0, lastLog: -99,
               npc: sp === 'human' ? { wary: false, friendly: 0, greeted: -99, goal: null } : null,
               meter: makeMeter() };
    });
    Play.minds.forEach((m) => { m.meter.visible = false; Play.scene.add(m.meter); });
    // grass trampling: what the player wears in on top of the baked trail, sampled by the grass shader
    Play.trailTex = new THREE.DataTexture(new Uint8Array(World.nx * World.ny), World.nx, World.ny, THREE.LuminanceFormat);
    Play.trailTex.magFilter = Play.trailTex.minFilter = THREE.LinearFilter; Play.trailTex.flipY = false; Play.trailTex.needsUpdate = true;
    Wind.uniforms.uTrail.value = Play.trailTex;   // texel (j, i) ↔ cell centre (ox + j res, oy + i res)
    Wind.uniforms.uTrailXf.value = [World.ox - World.res / 2, World.oy - World.res / 2, World.nx * World.res, World.ny * World.res];
    // scent particles
    Play.scentGeo = new THREE.BufferGeometry();
    Play.scentPos = new Float32Array(3 * 600);
    Play.scentGeo.setAttribute('position', new THREE.BufferAttribute(Play.scentPos, 3));
    const dot = document.createElement('canvas'); dot.width = dot.height = 32;
    const cx = dot.getContext('2d'), gr = cx.createRadialGradient(16, 16, 0, 16, 16, 16);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); cx.fillStyle = gr; cx.fillRect(0, 0, 32, 32);
    Play.scentPts = new THREE.Points(Play.scentGeo, new THREE.PointsMaterial({ color: 0xf2d27a, size: 0.22, map: new THREE.CanvasTexture(dot),
      transparent: true, opacity: 0.6, depthWrite: false }));
    Play.scentPts.visible = false; Play.scentPts.frustumCulled = false; Play.scene.add(Play.scentPts);
  };

  function makeMeter() {
    const m = new THREE.Mesh(new THREE.SphereGeometry(0.16, 10, 8), new THREE.MeshBasicMaterial({ color: 0x55aa55 }));
    return m;
  }

  Play.toggle = function () {
    Play.on = !Play.on;
    Play.avatar.visible = Play.on; Play.scentPts.visible = Play.on && Play.showScent;
    Play.minds.forEach((m) => { m.meter.visible = Play.on && m.sp !== 'human'; });
    if (Play.on) {
      Play.p.z = World.z(Play.p.x, Play.p.y);
      const a = G2(Play.p.x, Play.p.y, Play.p.z + 1.4);
      Play.controls.target.copy(a);
      Play.camera.position.copy(a).add(new THREE.Vector3(-3.6, 1.4, 3.6));   // over the shoulder, under the leaves
      Play.say('you walk in');
    }
    return Play.on;
  };

  Play.say = function (txt, who) {
    const line = `${Play.t.toFixed(0)}s · ${who ? who + ' ' : ''}<b>${txt}</b>`;
    Play.events.unshift(line); if (Play.events.length > 60) Play.events.pop();
    if (Play.log) Play.log(Play.events);
  };

  // ── player actions ──
  Play.keys = {};
  Play.action = function (a) {
    const p = Play.p;
    if (a === 'run') p.mode = p.mode === 'run' ? 'walk' : 'run';
    if (a === 'crouch') { p.posture = p.posture === 'crouch' ? 'stand' : 'crouch'; if (p.posture === 'crouch') p.mode = 'walk'; }
    if (a === 'clap') {
      p.clapT = 0.4; ring(p.x, p.y, 14, 0xffe08a);
      Play.say('you clap');
      Play.minds.forEach((m) => {
        const d = Math.hypot(m.x - p.x, m.y - p.y), [, fol] = World.coverTau(p.x, p.y, m.x, m.y);
        const s = m.sp === 'human' ? (d < 6 ? 1 : 0) : Life.hearing(m.sp, Life.P.CLAP_DB, d, fol, localU(m.x, m.y));
        if (s > 0) { m.mind.startle(s); m.cue = 'heard you clap'; if (m.npc && d < 6) startleNPC(m); }
      });
    }
    if (a === 'food') {
      const f = { x: p.x + Math.cos(p.h) * 1.2, y: p.y + Math.sin(p.h) * 1.2, amount: 1 };
      f.mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.4, 0.06, 14), new THREE.MeshStandardMaterial({ color: 0xd9b23c, roughness: 0.9 }));
      f.mesh.position.copy(G2(f.x, f.y, World.z(f.x, f.y) + 0.03)); Play.scene.add(f.mesh);
      Play.foods.push(f); Play.say('you scatter corn and seed');
    }
    if (a === 'wave') { p.waveT = 1.5; p.waved = Play.t; Play.say('you wave'); }
    if (a === 'scent') { Play.showScent = !Play.showScent; Play.scentPts.visible = Play.on && Play.showScent; }
  };

  function ring(x, y, rmax, color) {
    const m = new THREE.Mesh(new THREE.RingGeometry(0.9, 1, 48), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.7, side: THREE.DoubleSide, depthWrite: false }));
    m.rotation.x = -Math.PI / 2; m.position.copy(G2(x, y, World.z(x, y) + 0.08)); Play.scene.add(m);
    Play.rings.push({ m, t: 0, rmax });
  }

  const localU = (x, y) => {   // wind speed at 1.5 m where an animal listens (mean × gust): masking noise
    const c = World.get('canopy', x, y), [vx, vy] = Wind.at(x, y, 1.5, Wind.uniforms.uTime.value, c);
    return Math.hypot(vx, vy);
  };

  // ── per-frame update ──
  Play.update = function (dt, tAbs) {
    if (!Play.on) return;
    Play.t += dt;
    movePlayer(dt);
    for (const m of Play.minds) senseAndAct(m, dt);
    updateScent(dt);
    for (let i = Play.rings.length - 1; i >= 0; i--) {
      const r = Play.rings[i]; r.t += dt; const k = r.t / 1.2;
      r.m.scale.setScalar(1 + k * r.rmax); r.m.material.opacity = 0.7 * (1 - k);
      if (k >= 1) { Play.scene.remove(r.m); Play.rings.splice(i, 1); }
    }
    if (World.dirty && (Play.t % 0.5) < dt) { updateTrailTex(); }
    if ((Play.t % 3) < dt) World.blur();
  };

  function updateTrailTex() {
    const d = Play.trailTex.image.data;
    for (let k = 0; k < d.length; k++) d[k] = clamp((World.L.trail[k] - World.base[k]) * 2, 0, 1) * 255;
    Play.trailTex.needsUpdate = true; World.dirty = false;
  }

  function movePlayer(dt) {
    const p = Play.p, K = Play.keys;
    let fx = (K.KeyW || K.ArrowUp ? 1 : 0) - (K.KeyS || K.ArrowDown ? 1 : 0), sx = (K.KeyD || K.ArrowRight ? 1 : 0) - (K.KeyA || K.ArrowLeft ? 1 : 0);
    const cam = Play.camera.getWorldDirection(new THREE.Vector3()), cy = Math.atan2(-cam.z, cam.x);   // camera heading, world
    let want = 0, dir = p.h;
    if (fx || sx) { dir = cy + Math.atan2(-sx, fx); want = 1; p.target = null; }
    else if (p.target) { const dx = p.target[0] - p.x, dy = p.target[1] - p.y; if (Math.hypot(dx, dy) > 0.4) { dir = Math.atan2(dy, dx); want = 1; } else p.target = null; }
    const speed = { walk: Life.P.WALK, run: 3.5 }[p.mode] * (p.posture === 'crouch' ? 0.45 : 1) * (World.ground(p.x, p.y) === 'water' ? 0.5 : 1);
    p.v += clamp(want * speed - p.v, -6 * dt, 4 * dt);
    p.h += clamp(wrap(dir - p.h), -6 * dt, 6 * dt);
    const S = (World.nx - 1) * World.res, nx = clamp(p.x + Math.cos(p.h) * p.v * dt, World.ox + 2, World.ox + S - 2);
    const ny = clamp(p.y + Math.sin(p.h) * p.v * dt, World.oy + 2, World.oy + S - 2);
    {
      const moved = Math.hypot(nx - p.x, ny - p.y); p.x = nx; p.y = ny;
      p.dist = (p.dist || 0) + moved;
      while (p.dist > 0.35) { p.dist -= 0.35; World.deposit(p.x, p.y, 0.06 * 0.6); }   // desire.py: intensity·0.6 a half step
      if (moved > 0 && (Play.t - (p.stepRing || 0)) > (p.mode === 'run' ? 0.35 : 0.6)) {
        p.stepRing = Play.t; const L = Life.P.STEP_DB[p.posture === 'crouch' ? 'crouch' : p.mode] + Life.P.GROUND_DB[World.ground(p.x, p.y)];
        ring(p.x, p.y, Math.max(1, Math.pow(10, (L - 30) / 20)) / 6, 0xffffff);   // ring size ∝ distance to 30 dB
      }
    }
    p.z = World.z(p.x, p.y);
    // body: stride law for a person (biped), swinging legs and arms; crouch folds the hips
    const hip = p.posture === 'crouch' ? 0.62 : 0.92;
    if (p.v > 0.05) p.phase += TAU * p.v / Life.stride(p.v, 0.92) * dt;
    const U = Play.avatar.userData, sw = Math.min(p.v / 1.3, 1.4) * 0.5;
    U.hips.position.y = hip + (p.v > 0.05 ? 0.03 * Math.cos(2 * p.phase) : 0);
    U.legL.rotation.z = sw * Math.sin(p.phase); U.legR.rotation.z = -sw * Math.sin(p.phase);
    U.armL.rotation.z = -0.8 * sw * Math.sin(p.phase); U.armR.rotation.z = 0.8 * sw * Math.sin(p.phase);
    U.torso.rotation.z = p.posture === 'crouch' ? -0.5 : -0.05 * sw;
    if (p.clapT > 0) { p.clapT -= dt; U.armL.rotation.set(0.35, 0, 1.3); U.armR.rotation.set(-0.35, 0, 1.3); }
    else { U.armL.rotation.x = 0; U.armR.rotation.x = 0; }
    if (p.waveT > 0) { p.waveT -= dt; U.armR.rotation.set(-2.6 + 0.4 * Math.sin(Play.t * 12), 0, 0); }
    Play.avatar.position.copy(G2(p.x, p.y, p.z));
    yawQ(p.h, Play.avatar.quaternion);
    // camera follows, keeping the user's orbit
    const tgt = G2(p.x, p.y, p.z + 1.4), d = tgt.clone().sub(Play.controls.target);
    Play.controls.target.add(d); Play.camera.position.add(d);
  }

  function updateScent(dt) {
    const p = Play.p, t = Wind.uniforms.uTime.value, P = Play.scentPos;
    Play.scentEmit = (Play.scentEmit || 0) + dt;
    while (Play.scentEmit > 0.05) {
      Play.scentEmit -= 0.05;
      Play.scent.push({ x: p.x + (Math.random() - 0.5) * 0.5, y: p.y + (Math.random() - 0.5) * 0.5, z: 1.0 + Math.random() * 0.6, age: 0 });
      if (Play.scent.length > 600) Play.scent.shift();
    }
    Play.scent.forEach((s, k) => {
      const c = World.get('canopy', s.x, s.y), [vx, vy] = Wind.at(s.x, s.y, s.z, t, c);
      const sp = 0.15 + 0.06 * Math.sqrt(s.age);   // turbulent spread grows with age (σ ∝ x, Briggs)
      s.x += (vx + sp * (Math.random() - 0.5) * 6) * dt; s.y += (vy + sp * (Math.random() - 0.5) * 6) * dt;
      s.z = clamp(s.z + sp * (Math.random() - 0.5) * 2 * dt, 0.2, 4); s.age += dt;
      const g = G2(s.x, s.y, World.z(s.x, s.y) + s.z); P[3 * k] = g.x; P[3 * k + 1] = g.y; P[3 * k + 2] = g.z;
    });
    for (let k = Play.scent.length; k < 600; k++) { P[3 * k + 1] = -1e4; }
    Play.scentGeo.attributes.position.needsUpdate = true;
  }

  // ── an animal: sense the player, update the mind, act ──
  const tmpV = new THREE.Vector3(), tmpQ = new THREE.Quaternion(), fwd = new THREE.Vector3();
  function senseAndAct(m, dt) {
    const p = Play.p, sp = m.sp, rig = m.rig;
    if (!m.live) {   // read where the baked clip has the animal
      m.node.getWorldPosition(tmpV); m.x = tmpV.x; m.y = -tmpV.z; m.alt = Math.max(0, tmpV.y - World.z(m.x, m.y));
      fwd.set(1, 0, 0).applyQuaternion(m.node.getWorldQuaternion(tmpQ)); m.h = Math.atan2(-fwd.z, fwd.x);
    }
    const dx = p.x - m.x, dy = p.y - m.y, d = Math.hypot(dx, dy), bear = Math.atan2(dy, dx);
    m.meter.position.copy(G2(m.x, m.y, World.z(m.x, m.y) + m.alt + (rig.hip || 0.5) * 2.2 + 0.4));
    if (m.npc) { npc(m, dt, d, bear); return; }
    // the three senses (Life mirrors perception.py)
    const [tau, fol] = World.coverTau(p.x, p.y, m.x, m.y);
    const sSee = Life.sight(sp, d, wrap(bear - m.h), p.v, p.posture, Play.lighting.intensity, Life.P.COVER_K * tau);
    const moving = p.v > 0.2;
    const Ls = moving ? Life.P.STEP_DB[p.posture === 'crouch' ? 'crouch' : p.mode] + Life.P.GROUND_DB[World.ground(p.x, p.y)] : -99;
    const sHear = Life.hearing(sp, Ls, d, fol, localU(m.x, m.y));
    const [wx, wy] = Wind.at(p.x, p.y, 1.5, Wind.uniforms.uTime.value, World.get('canopy', p.x, p.y)), U = Math.hypot(wx, wy) || 1e-3;
    const along = (-dx * wx - dy * wy) / U, across = (dx * wy - dy * wx) / U;   // animal relative to the player, in the wind's frame
    const sSmell = Life.smell(sp, along, across, U);
    const S = Life.combine(sSee, sHear, sSmell);
    const cosb = p.v > 0.1 ? Math.cos(wrap(p.h - (bear + Math.PI))) : 0;    // is the player heading at the animal?
    const D = Life.fid(sp, p.v, cosb, m.mind.sens, m.mind.habit);
    const changed = m.mind.step(dt, S, d, D);
    const top = Math.max(sSee, sHear, sSmell);
    if (top > 0.05) m.cue = top === sSmell ? 'smelled you' + (along > 0 ? ` (${along.toFixed(0)} m downwind)` : '') : top === sHear ? 'heard you' : 'saw you';
    m.meter.material.color.setHSL(0.33 * (1 - m.mind.alarm), 0.8, 0.5);
    if (changed) {
      const st = m.mind.state, who = `${sp.replace(/_/g, ' ')} ${m.node.name.split('_').pop()}`;
      const disp = Life.P.SENSES[sp].display, fl = rig.withdraws ? 'shuts its shell' : rig.flies ? 'flushes' : rig.climbs ? 'bolts for a tree' : 'flees';
      Play.say(st === 'alert' ? `${m.cue} → alert, ${disp}` : st === 'flee' ? `${m.cue} → ${fl}` : 'calms down', who);
      if (!m.live && st !== 'calm') { m.live = true; m.act = 'stand'; m.actT = 0; if (sp === 'armadillo' && st === 'flee') m.jumpT = 0.6; }
    }
    if (m.live) act(m, dt, d, bear, D);
  }

  function act(m, dt, d, bear, D) {
    const rig = m.rig, st = m.mind.state, h = rig.hip || 0.5;
    let want = 0, dir = m.h, look = wrap(bear - m.h), head = 0, flag = 0;
    m.actT += dt;
    if (st === 'alert') {
      dir = bear; want = 0; head = -0.25; flag = 0.4;
      if (m.cue.startsWith('smelled') && !rig.withdraws) { dir = bear + Math.PI * 0.75; want = rig.walk; look = wrap(bear - m.h); }  // slips away, crosswind
    } else if (st === 'flee') {
      flag = 1; head = 0.1;
      if (rig.withdraws) { want = 0; m.shut = Math.min(1, (m.shut || 0) + dt * 3); }
      else {
        dir = bear + Math.PI; want = rig.run;
        if (rig.climbs) {   // nearest trunk, then up it
          if (!m.tree) m.tree = Play.trees.reduce((b, t) => (Math.hypot(t.x - m.x, t.y - m.y) < Math.hypot(b.x - m.x, b.y - m.y) ? t : b), Play.trees[0] || { x: m.x, y: m.y });
          const tx = m.tree.x - m.x, ty = m.tree.y - m.y, td = Math.hypot(tx, ty);
          if (td > 0.6) dir = Math.atan2(ty, tx); else { want = 0; m.alt = Math.min(6, m.alt + 1.5 * dt); }
        }
        if (rig.flies) { m.alt = Math.min(8, m.alt + 2 * dt); want = rig.flies * (0.4 + 0.6 * Math.min(m.alt / 8, 1)); }
        // steer off the tile edge and out of deep water
        const ax = m.x + Math.cos(dir) * 4, ay = m.y + Math.sin(dir) * 4;
        if (!World.inside(ax, ay, 4) || (!rig.flies && World.get('water', ax, ay) > 0.5)) dir += 1.2;
      }
    } else {   // calm again: graze, or come to food when it is safe enough
      m.tree = null; m.shut = Math.max(0, (m.shut || 0) - dt * 0.15);   // turtles emerge slowly
      if (rig.flies && m.alt > 0) m.alt = Math.max(0, m.alt - 1.5 * dt);
      if (rig.climbs && m.alt > 0) m.alt = Math.max(0, m.alt - 0.6 * dt);
      const food = Play.foods.filter((f) => f.amount > 0 && ['forage', 'mast', 'shore'].includes(rig.eats))
        .sort((a, b) => Math.hypot(a.x - m.x, a.y - m.y) - Math.hypot(b.x - m.x, b.y - m.y))[0];
      const fd = food ? Math.hypot(food.x - m.x, food.y - m.y) : 1e9, pf = food ? Math.hypot(food.x - Play.p.x, food.y - Play.p.y) : 0;
      if (food && fd < 70 && pf > 0.8 * D && m.alt === 0) {
        if (fd > 0.8) { dir = Math.atan2(food.y - m.y, food.x - m.x); want = rig.walk; head = 0.15; }
        else {
          head = 1; m.eatT = (m.eatT || 0) + dt; food.amount -= 0.01 * dt;
          if (m.eatT > 4) {
            m.eatT = 0; m.mind.fed(); m.meals = (m.meals || 0) + 1;
            const who = `${m.sp.replace(/_/g, ' ')} ${m.node.name.split('_').pop()}`;
            if (m.meals === 1) Play.say('eats your corn', who);
            if (m.meals === 3) Play.say(`is getting used to you (flight distance now ${Life.fid(m.sp, Life.P.WALK, 1, m.mind.sens, m.mind.habit).toFixed(0)} m)`, who);
          }
          if (food.amount <= 0) { Play.scene.remove(food.mesh); }
        }
      } else { head = 0.8; want = 0; look *= 0.3; }   // graze where it stands, glancing up
    }
    if (m.jumpT > 0) { m.jumpT -= dt; const u = 1 - m.jumpT / 0.6; m.hop = 4 * 1.1 * u * (1 - u); } else m.hop = 0;   // 3–4 ft straight up
    // locomotion: turn-limited heading, speed ramp, stride phase
    m.h += clamp(wrap(dir - m.h), -3 * dt, 3 * dt);
    m.v += clamp(want - m.v, -8 * dt, 5 * dt);
    const nx = m.x + Math.cos(m.h) * m.v * dt, ny = m.y + Math.sin(m.h) * m.v * dt;
    if (World.inside(nx, ny, 1)) { m.x = nx; m.y = ny; }
    if (m.v > 0.05 && m.alt === 0) m.phase += TAU * m.v / Life.stride(m.v, h) * dt;
    m.look += (clamp(look, -1.22, 1.22) - m.look) * Math.min(1, dt / 0.3);
    pose(m, head, flag, h);
  }

  function pose(m, head, flag, h) {
    const rig = m.rig, z = World.z(m.x, m.y) + m.alt + m.hop;
    m.node.position.copy(G2(m.x, m.y, z)); yawQ(m.h, m.node.quaternion);
    const air = m.alt > 0.3 && rig.flies;
    const fr = Life.froude(m.v, h), gname = Life.gaitName(fr), tab = Play.sceneInfo.gait[rig.kind === 'quad' ? 'QUAD' : 'BIPED'][gname];
    const S = Life.stride(Math.max(m.v, 0.05), h) * tab[1], lift = Play.sceneInfo.gait.LIFT[gname];
    m.legs.forEach((lg, i) => {
      if (!lg.th || !lg.sh) return;
      const r = rig.legs[i]; let a1, a2;
      if (air) { a1 = -1.4; a2 = 0; }
      else if (m.v > 0.05) { const [fx, fz] = Life.footPath(m.phase / TAU - tab[0][i % tab[0].length], tab[1], S, h, lift); [a1, a2] = Life.twoBone(fx, fz, r.l1, r.l2, r.knee); }
      else [a1, a2] = Life.twoBone(0, -h, r.l1, r.l2, r.knee);
      pitchQ(a1, lg.th.quaternion); pitchQ(a2, lg.sh.quaternion);
    });
    if (m.body) m.body.position.set(0, m.v > 0.05 && !air ? Play.sceneInfo.gait.BOB[gname] * h * Math.cos(2 * m.phase) : 0, 0);
    if (m.neck) { const q1 = yawQ(m.look, new THREE.Quaternion()), q2 = pitchQ(-head * (rig.graze || 0), new THREE.Quaternion()); m.neck.quaternion.copy(q1.multiply(q2));
      m.neck.scale.setScalar(1 - 0.9 * (m.shut || 0)); }
    if (m.tail) pitchQ(-flag * (rig.flag || 0), m.tail.quaternion);
    m.legs.forEach((lg) => lg.th && lg.th.scale.setScalar(1 - 0.85 * (m.shut || 0)));
    m.wings.forEach((w, i) => {
      const roll = air ? (i ? -1 : 1) * Play.sceneInfo.gait.FLAP_AMP * Math.sin(TAU * Play.sceneInfo.gait.FLAP_HZ * Play.t) : 0;
      w.quaternion.set(Math.sin(roll / 2), 0, 0, Math.cos(roll / 2)); w.scale.set(1, 1, air ? 1 : Play.sceneInfo.gait.WING_FOLD);
    });
  }

  // ── people: Hall's distances, greetings, memory of the player, and the paths the player wears ──
  const PERSONAL = 1.22, SOCIAL = 3.7, PUBLIC = 7.6;
  function startleNPC(m) { m.npc.wary = true; m.npc.backT = 1.0; Play.say('jumps — "whoa!" — and keeps their distance', 'person ' + m.node.name.split('_').pop()); }
  function npc(m, dt, d, bear) {
    const n = m.npc, p = Play.p;
    if (!m.live && d < 12) { m.live = true; n.goal = null; }
    if (!m.live) return;
    let want = m.rig.walk || 1.31, dir = m.h, look = 0, head = 0.1;
    if (!n.goal || Math.hypot(n.goal[0] - m.x, n.goal[1] - m.y) < 2) {   // next destination: a door, a road end, the creek
      const A = Play.sceneInfo.attractors || [[m.x + 20, m.y]];
      n.goal = A[Math.floor(Math.random() * A.length)];
    }
    // active walker (desire.py): goal + trail comfort − obstacles; the player's worn path pulls them
    const ex = n.goal[0] - m.x, ey = n.goal[1] - m.y, el = Math.hypot(ex, ey) || 1;
    const e = 1.0, gx = (World.sampleArr(World.comfort, m.x + e, m.y) - World.sampleArr(World.comfort, m.x - e, m.y)) / (2 * e);
    const gy = (World.sampleArr(World.comfort, m.x, m.y + e) - World.sampleArr(World.comfort, m.x, m.y - e)) / (2 * e);
    const [ux, uy] = Life.walkerDir(ex / el, ey / el, gx, gy, 0, 0);
    dir = Math.atan2(uy, ux);
    const keep = n.wary ? SOCIAL : PERSONAL;
    if (d < PUBLIC) look = wrap(bear - m.h);
    if (d < keep) { dir = bear + Math.PI / 2 * (wrap(bear - m.h) > 0 ? -1 : 1); }   // sidestep around the player
    if (n.backT > 0) { n.backT -= dt; dir = bear + Math.PI; want = 1.0; }
    const who = 'person ' + m.node.name.split('_').pop();
    // Kendon's greeting: a distance salutation across public space, a close one inside social space
    if (!n.wary && d < PUBLIC && Play.t - n.greeted > 30 && p.mode !== 'run') {
      n.greeted = Play.t; n.closeDone = false;
      Play.say(n.friendly > 0 ? 'smiles — you again' : 'looks up and nods', who);
    }
    if (!n.wary && d < SOCIAL && !n.closeDone && Play.t - n.greeted < 30) {
      n.closeDone = true; n.chatT = n.friendly > 0 ? 4 : 1.5;
      Play.say(n.friendly > 0 ? 'stops to chat — "nice evening for it"' : '"hey there"', who);
    }
    if (p.waved !== undefined && p.waved !== n.sawWave && Play.t - p.waved < 1 && d < 25 && !n.wary) {
      n.sawWave = p.waved; n.friendly++; n.chatT = Math.max(n.chatT || 0, 1.5); Play.say('waves back', who);
    }
    if (p.mode === 'run' && d < 3 && p.v > 2 && Math.cos(wrap(p.h - (bear + Math.PI))) > 0.7 && !n.wary) startleNPC(m);
    if (n.chatT > 0) { n.chatT -= dt; want = 0; dir = bear; head = -0.1; }
    m.h += clamp(wrap(dir - m.h), -2.5 * dt, 2.5 * dt);
    m.v += clamp(want - m.v, -4 * dt, 2 * dt);
    const nx = m.x + Math.cos(m.h) * m.v * dt, ny = m.y + Math.sin(m.h) * m.v * dt;
    if (World.inside(nx, ny, 1)) {
      m.dist = (m.dist || 0) + Math.hypot(nx - m.x, ny - m.y); m.x = nx; m.y = ny;
      while (m.dist > 0.35) { m.dist -= 0.35; World.deposit(m.x, m.y, 0.06 * 0.6); }   // people wear paths too
    }
    if (m.v > 0.05) m.phase += TAU * m.v / Life.stride(m.v, m.rig.hip || 0.9) * dt;
    m.look += (clamp(look, -1.22, 1.22) - m.look) * Math.min(1, dt / 0.3);
    m.alt = 0; m.hop = 0;
    pose(m, head, 0, m.rig.hip || 0.9);
  }

  window.Play = Play; window.PlayWorld = World;
})();

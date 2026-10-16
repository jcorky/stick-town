// Perception and response of animals to the player (docs/TECHNIQUES.md §35). Mirrors plandscape/fauna/perception.py
// function by function (tests compare them through node); the constants come from scene.json (perception).
(function (root) {
  const L = { P: null };
  const clamp = (x, a, b) => Math.min(Math.max(x, a), b);
  L.init = (P) => { L.P = P; };
  L.fovGain = (theta, fov) => (Math.abs(theta) <= (fov * Math.PI / 180) / 2 ? 1 : 0.15);
  L.motionGain = (v) => 0.25 + 0.75 * clamp(v / L.P.WALK, 0, 1.5) / 1.5;
  L.lightGain = (I, twilight) => { const i = clamp(I, 0.05, 1); return twilight && i < 0.6 ? Math.max(i, 0.9) : i; };
  L.sight = (sp, d, theta, v, posture = 'stand', I = 1, coverTau = 0) => {
    const s = L.P.SENSES[sp];
    return clamp(s.acuity * L.fovGain(theta, s.fov) * L.motionGain(v) * L.P.POSTURE[posture] *
      L.lightGain(I, s.twilight) * Math.exp(-d / s.rv) * Math.exp(-coverTau), 0, 1);
  };
  L.windNoise = (U) => Math.max(L.P.QUIET_DB, L.P.WIND_DB0 + L.P.WIND_DB_LOG * Math.log10(Math.max(U, 0.05) / 5.1));
  L.level = (Ls, d, dFol = 0) => Ls - 20 * Math.log10(Math.max(d, 1)) - L.P.FOLIAGE_DB * dFol;
  L.hearing = (sp, Ls, d, dFol, U) => clamp((L.level(Ls, d, dFol) - L.windNoise(U) + L.P.SENSES[sp].hear) / 10, 0, 1);
  L.sigmas = (x) => { x = Math.max(x, 0); return [L.P.SOURCE_SIGMA + 0.08 * x / Math.sqrt(1 + 0.0001 * x),
                                                   L.P.SOURCE_SIGMA + 0.06 * x / Math.sqrt(1 + 0.0015 * x)]; };
  L.plume = (x, y, U) => {
    if (x <= 0) return 0;
    const [sy, sz] = L.sigmas(x);
    return Math.exp(-0.5 * (y / sy) ** 2) * Math.exp(-0.5 * (L.P.NOSE_H / sz) ** 2) / (Math.max(U, 0.3) * sy * sz);
  };
  L.smell = (sp, x, y, U) => { const ro = L.P.SENSES[sp].ro; if (ro <= 0) return 0;
    return clamp(1 + Math.log(Math.max(L.plume(x, y, U) / L.plume(ro, 0, U), 1e-12)), 0, 1) * L.P.SMELL_MAX; };
  L.combine = (...s) => 1 - s.reduce((p, x) => p * (1 - x), 1);
  L.fid = (sp, v, cosb, sens = 0, habit = 0) =>
    L.P.SENSES[sp].fid * (0.6 + 0.4 * Math.min(v / L.P.WALK, 2.5)) * (0.7 + 0.3 * Math.max(cosb, 0)) * Math.exp(sens - habit);

  // one animal's running state toward the player (perception.Mind)
  L.Mind = class {
    constructor(sp) { this.sp = sp; this.alarm = 0; this.habit = 0; this.sens = 0; this.state = 'calm'; }
    step(dt, S, d, D) {
      const P = L.P, s = Math.min(1, S * Math.exp(this.sens - this.habit));
      const rate = s > this.alarm ? (s - this.alarm) / P.ALARM_RISE : -this.alarm / P.ALARM_TAU;
      this.alarm = clamp(this.alarm + dt * rate, 0, 1);
      const prev = this.state;
      if (this.state === 'flee') { if (this.alarm < P.A_ALERT && d > 1.5 * D) this.state = 'calm'; }
      else if (this.alarm >= P.A_FLEE || (this.alarm >= P.A_ALERT && d < D)) this.state = 'flee';
      else if (this.alarm >= P.A_ALERT) this.state = 'alert';
      else if (this.state === 'alert' && this.alarm < 0.5 * P.A_ALERT) {
        this.state = 'calm'; this.habit = Math.min(P.MEMORY_MAX, this.habit + P.HABIT_STEP);
      }
      return prev !== this.state;
    }
    startle(a) { this.alarm = Math.min(1, this.alarm + a); this.sens = Math.min(L.P.MEMORY_MAX, this.sens + L.P.SENSITISE_STEP * a); }
    fed() { this.habit = Math.min(L.P.MEMORY_MAX, this.habit + L.P.FEED_STEP); }
  };

  // gait (plandscape/fauna/gait.py): Froude number, stride, gait choice, foot path, two-bone IK
  L.G = 9.81;
  L.froude = (v, h) => v * v / (L.G * h);
  L.stride = (v, h) => 2.3 * h * Math.pow(Math.max(L.froude(v, h), 1e-9), 0.3);
  L.gaitName = (fr) => (fr < 0.5 ? 'walk' : fr < 2.5 ? 'trot' : 'gallop');
  L.footPath = (psi, beta, S, h, lift) => {
    psi = ((psi % 1) + 1) % 1;
    if (psi < beta) return [S * (0.5 - psi / Math.max(beta, 1e-6)), -h];
    const u = clamp((psi - beta) / Math.max(1 - beta, 1e-6), 0, 1), ss = u * u * (3 - 2 * u);
    return [S * (-0.5 + ss), -h + lift * h * Math.sin(Math.PI * u)];
  };
  L.twoBone = (x, z, l1, l2, knee = 1) => {
    const d = clamp(Math.hypot(x, z), Math.abs(l1 - l2) + 1e-6, l1 + l2 - 1e-6);
    const gam = Math.acos(clamp((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1, 1));
    const K = Math.acos(clamp((l1 * l1 + l2 * l2 - d * d) / (2 * l1 * l2), -1, 1));
    return [Math.atan2(x, -z) + knee * gam, -knee * (Math.PI - K)];
  };
  // active walker step direction (plandscape/paths/desire.py simulate): goal + trail comfort − obstacles
  L.walkerDir = (ex, ey, gx, gy, ox, oy, attraction = 1.4) => {
    const gn = Math.hypot(gx, gy), k = gn > 1e-9 ? attraction * Math.min(1, gn * 40) / gn : 0;
    let x = ex + k * gx - 6 * ox, y = ey + k * gy - 6 * oy;
    const n = Math.hypot(x, y) || 1;
    return [x / n, y / n];
  };

  root.Life = L;
  if (typeof module !== 'undefined') module.exports = L;
})(typeof window !== 'undefined' ? window : globalThis);

"""Regenerate docs/gallery: the review renders that show where the project stands.

  python3 scripts/gallery.py            # renders the three reference scenes + species sheet
  python3 scripts/gallery.py --reuse    # only re-encode existing out/<name>/ renders

Images are JPEG at ≤1100 px so the gallery stays a few MB in plain git (no LFS).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

SCENES = {
    "monte-sano": "Monte Sano hardwood cove with a dogtrot cabin, a creek, two deer, three squirrels "
                  "and a turkey flock at golden hour in fall",
    "longleaf": "longleaf pine savanna near Mobile at dusk, dirt path, a few deer",
    "bayou": "cypress bayou floodplain with a shotgun house, a heron, a raccoon, a box turtle and an armadillo at dusk in summer",
    "walk": "Piedmont hardwood hollow with a farmhouse, a creek, two deer, three squirrels, a turkey flock and two hikers "
            "in the evening in summer, breezy",
}
OUT = os.path.join(ROOT, "docs", "gallery")


def _jpeg(src, dst, width=1100):
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=84, optimize=True)


def species_sheet(path, season="summer"):
    from plandscape.flora.species import SPECIES
    from plandscape.flora.tree import generate_tree
    from plandscape.render import render
    W, H = 300, 380
    tiles = []
    tmp = os.path.join(ROOT, "out", "gallery_tmp")
    os.makedirs(tmp, exist_ok=True)
    for k in SPECIES:
        m = generate_tree(k, seed=5, season=season, moisture=0.85, detail="low")
        p = os.path.join(tmp, f"{k}.png")
        render([m.bark, m.foliage], p, size=(W, H), elevation=8)
        tiles.append((k, p))
    sheet = Image.new("RGB", (W * 6, H * ((len(tiles) + 5) // 6)), "white")
    for i, (k, p) in enumerate(tiles):
        im = Image.open(p)
        ImageDraw.Draw(im).text((8, 8), k.replace("_", " "), fill=(0, 0, 0))
        sheet.paste(im, ((i % 6) * W, (i // 6) * H))
    sheet.save(path)
    return path


def terrain_sheet(path, seed=7):
    """Hillshades of three provinces before and after droplet erosion (TECHNIQUES §14)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    from plandscape.terrain import heightfield as hfm
    provs = ("piedmont", "cumberland_plateau", "ridge_and_valley")
    fig, ax = plt.subplots(2, 3, figsize=(15, 10))
    ls = LightSource(315, 35)
    real = hfm.droplet_erosion
    for col, prov in enumerate(provs):
        for row, erode in enumerate((False, True)):
            hfm.droplet_erosion = real if erode else (lambda z, **k: z)
            try:
                z = hfm.generate_tile(128, 1.0, prov, seed, creek=False).z
            finally:
                hfm.droplet_erosion = real
            ax[row, col].imshow(ls.hillshade(z, vert_exag=3), cmap="gray", origin="lower")
            ax[row, col].set_title(f"{prov.replace('_', ' ')} — {'with' if erode else 'without'} droplet erosion")
            ax[row, col].axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)
    return path


def creek_sheet(path, seed=135121):
    """Creek networks per province (TECHNIQUES §21): hillshade, wetted channel (blue), centrelines (red)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LightSource
    from plandscape.terrain.heightfield import generate_tile
    provs = ("cumberland_plateau", "piedmont", "ridge_and_valley", "floodplain")
    fig, ax = plt.subplots(1, 4, figsize=(20, 5.6))
    ls = LightSource(315, 35)
    for a, prov in zip(ax, provs):
        hf = generate_tile(128, 1.0, prov, seed)
        a.imshow(ls.hillshade(hf.z, vert_exag=3), cmap="gray", origin="lower")
        a.imshow(np.ma.masked_less(hf.layers["water"], 0.5), cmap="Blues", vmin=0, vmax=1.2, origin="lower")
        c = hf.channels
        for rid in np.unique(c[:, 4]):
            q = c[c[:, 4] == rid]
            a.plot(q[:, 0], q[:, 1], lw=0.7, color="#c0392b")
        a.set_title(f"{prov.replace('_', ' ')}: {len(np.unique(c[:, 4]))} reaches, wetted ≤ {c[:, 3].max():.1f} m")
        a.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)
    return path


def gait_sheet(path, key="white_tailed_deer"):
    """One stride in 8 frames at walk, trot and gallop speeds (TECHNIQUES §25–26), from the same rig, foot paths
    and two-bone IK the GLB uses; the grey line is the ground."""
    import numpy as np
    from plandscape.fauna import gait
    from plandscape.fauna.bodies import posed_legs, rig
    from plandscape.mesh import box
    from plandscape.render import render
    rg = rig(key, (0.55, 0.42, 0.30))
    h = rg["hip"]
    ground = box((0.1, 0, -0.01), (2.6, 0.6, 0.02), (0.45, 0.45, 0.42))
    rows = []
    for v in (1.0, 3.0, 8.0):
        fr = float(gait.froude(v, h))
        name = gait.gait_name(fr)
        offs, beta = gait.QUAD[name]
        S = float(gait.stride(v, h)) * beta
        frames = []
        for k in range(8):
            ang = []
            for lg, o in zip(rg["legs"], offs):
                x, z = gait.foot_path(k / 8 - o, beta, S, h, gait.LIFT[name])
                ang.append(gait.two_bone(x, z, lg["l1"], lg["l2"], lg["knee"]))
            img = render([ground, rg["torso"]] + posed_legs(rg, ang), None, size=(200, 150), azimuth=0, elevation=4,
                         fit=((-1.2, -0.5, -0.05), (1.4, 0.5, 1.75)), keep_first=99)
            frames.append(img)
        strip = Image.fromarray(np.concatenate(frames, 1))
        ImageDraw.Draw(strip).text((6, 4), f"v = {v} m/s   Fr = {fr:.2f}   {name}   stride = {S / beta:.2f} m   "
                                           f"stance = {S:.2f} m   lift = {gait.LIFT[name] * h:.2f} m", fill=(0, 0, 0))
        rows.append(strip)
    sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), "white")
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(path)
    return path


def pose_sheet(path):
    """Poses by behaviour state (TECHNIQUES §28–29): head pitch, the deer's flag, lying down to rest."""
    import numpy as np
    from plandscape.fauna import gait
    from plandscape.fauna.bodies import _pitch, posed_legs, rig
    from plandscape.mesh import Mesh, box
    from plandscape.render import render
    states = ("eat", "rest", "travel", "alert", "flee")
    rows = []
    for key, rgb in (("white_tailed_deer", (0.55, 0.42, 0.30)), ("coyote", (0.55, 0.5, 0.42)),
                     ("wild_turkey", (0.25, 0.2, 0.15))):
        rg = rig(key, rgb)
        h = rg["hip"]
        ground = box((0.1, 0, -0.01), (2.6, 0.6, 0.02), (0.45, 0.45, 0.42))
        frames = []
        for st in states:
            drop = gait.LIE.get(st, 0.0) * rg["lie"] * h
            lift = np.array([0, 0, -drop], np.float32)

            def part(p_, ang):
                return Mesh(_pitch(p_["mesh"].positions, -ang) + np.asarray(p_["pivot"], np.float32) + lift,
                            p_["mesh"].colors, p_["mesh"].indices)
            parts = [Mesh(rg["torso"].positions + lift, rg["torso"].colors, rg["torso"].indices)]
            if rg["neck"]:
                parts.append(part(rg["neck"], gait.HEAD.get(st, 0.0) * rg["neck"]["graze"]))
            if rg["tail"]:
                parts.append(part(rg["tail"], gait.TAIL.get(st, 0.0) * rg["tail"]["flag"]))
            ang = [gait.two_bone(0.0, -(h - drop), lg["l1"], lg["l2"], lg["knee"]) for lg in rg["legs"]]
            parts += [Mesh(m.positions + lift, m.colors, m.indices) for m in posed_legs(rg, ang)]
            img = render([ground] + parts, None, size=(220, 160), azimuth=0, elevation=4,
                         fit=((-1.2, -0.5, -0.05), (1.4, 0.5, 1.75)) if key != "wild_turkey" else
                         ((-0.6, -0.3, -0.03), (0.6, 0.3, 1.1)), keep_first=99)
            im = Image.fromarray(img)
            ImageDraw.Draw(im).text((6, 4), f"{key.replace('_', ' ')}: {st}", fill=(0, 0, 0))
            frames.append(np.asarray(im))
        rows.append(np.concatenate(frames, 1))
    Image.fromarray(np.concatenate(rows, 0)).save(path)
    return path


def motion_sheet(path):
    """A stored deer behaviour clip: logged vs exported heading, and its path with the kept keys (§30)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from plandscape.assets.store import AssetStore
    from plandscape.fauna import motion
    st = AssetStore()
    clips = [e for e in st.find("behavior", species="white_tailed_deer")]
    best = None
    for e in clips:  # the clip that both travels and stops the most
        a, _ = st.get("behavior", e.params)
        L = a["track"]
        dist = np.hypot(*np.diff(L[:, 1:3], axis=0).T)
        score = dist.sum() * (dist < 0.01).mean()
        if best is None or score > best[0]:
            best = (score, L)
    L = best[1]
    log = [(r[0], r[1], r[2], r[3], r[4], "") for r in L]
    t = L[:, 0]
    raw = L[:, 4]
    tk, Pk, Hk = motion.export_track(log, "white_tailed_deer")
    fig, ax = plt.subplots(1, 3, figsize=(20, 5))
    deg = lambda a: np.degrees(motion.wrap(a))  # noqa: E731
    ax[0].plot(t, deg(raw), lw=0.8, color="0.6", label="logged heading (snaps, jitters at rest)")
    ax[0].plot(t[::4], deg(raw[::4]), "x", ms=4, color="#c0392b", label="old export: every 1 s")
    ax[0].plot(tk, deg(Hk), "o", ms=2.5, color="#1f6f8b",
               label=f"turn-limited, {len(tk)} keys (ω ≤ {motion.OMEGA_MAX['white_tailed_deer']:.0f} rad/s)")
    ax[0].set_xlabel("time (s)")
    ax[0].set_ylabel("heading (deg)")
    ax[0].legend(fontsize=8)
    ax[1].plot(L[:, 1], L[:, 2], lw=0.8, color="0.6", label="logged path (0.25 s)")
    ax[1].plot(Pk[:, 0], Pk[:, 1], "o", ms=3, color="#1f6f8b", label=f"kept keys ({len(tk)} of {len(t)})")
    ax[1].quiver(Pk[:, 0], Pk[:, 1], np.cos(Hk), np.sin(Hk), scale=25, width=0.003, color="#1f6f8b")
    ax[1].set_aspect("equal")
    ax[1].legend(fontsize=8)
    ax[1].set_title("path, relative to start (m)")
    _, _, body = motion.body_headings(log, "white_tailed_deer")
    psi = motion.gaze(log, body)
    ax[2].plot(t, np.degrees(psi), lw=1.0, color="#7d5ba6", label="head yaw ψ (gaze), §31")
    ax[2].axhline(np.degrees(motion.GAZE_MAX), ls=":", color="0.5")
    ax[2].axhline(-np.degrees(motion.GAZE_MAX), ls=":", color="0.5")
    ax[2].set_xlabel("time (s)")
    ax[2].set_ylabel("deg from body heading")
    ax[2].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)
    return path


def fauna_sheet(path):
    """Every species (§32, sculpted §36): a portrait of each in three-quarter view, then all of them to scale."""
    import numpy as np
    from plandscape.fauna.agents import FAUNA
    from plandscape.fauna.bodies import body
    from plandscape.mesh import Mesh, box
    from plandscape.render import render
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = small = None
    W, H = 560, 420
    tiles, parts, x = [], [], 0.0
    for key, spec in FAUNA.items():
        b = body(key, spec.rgb)
        lo, hi = b.positions.min(0), b.positions.max(0)
        c, r = (lo + hi) / 2, float(np.max(hi - lo)) * 0.62
        im = render([b], None, size=(W, H), azimuth=-38, elevation=12,
                    fit=((c[0] - r, c[1] - r, lo[2] - 0.05 * r), (c[0] + r, c[1] + r, lo[2] + 1.6 * r)))
        tile = Image.fromarray(im)
        d = ImageDraw.Draw(tile)
        d.text((12, 10), spec.common, fill=(20, 26, 22), font=font)
        d.text((12, 36), f"{b.n_tris:,} triangles · {float(hi[2]):.2f} m tall", fill=(70, 80, 72), font=small)
        tiles.append(tile)
        w = float(np.ptp(b.positions[:, 0]))
        x += w / 2 + 0.25
        m = Mesh(b.positions + np.array([x - b.positions[:, 0].mean(), 0, 0], np.float32), b.colors, b.indices)
        m.nrm = b.nrm
        parts.append(m)
        x += w / 2 + 0.25
    ground = [box((x / 2, 0, -0.01), (x + 0.4, 1.0, 0.02), (0.55, 0.55, 0.5))]
    ground += [box((i, 0.3, 0.0), (0.02, 0.4, 0.004), (0.2, 0.2, 0.2)) for i in range(int(x) + 1)]  # 1 m ticks
    line = Image.fromarray(render(ground + parts, None, size=(3 * W, 470), azimuth=-12, elevation=8, keep_first=99,
                                  fit=((-0.2, -0.6, -0.05), (x + 0.2, 0.6, 1.9))))
    ImageDraw.Draw(line).text((12, 10), "all to scale, ticks every 1 m", fill=(20, 26, 22), font=font)
    rows = (len(tiles) + 2) // 3
    sheet = Image.new("RGB", (3 * W, rows * H + line.height), (247, 248, 242))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 3) * W, (i // 3) * H))
    sheet.paste(line, (0, rows * H))
    sheet.save(path)
    return path


def flight_sheet(path):
    """A flushed heron (§33): four wingbeat phases rendered from the rig, and altitude and wing roll over a flight."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from plandscape.fauna import agents as A
    from plandscape.fauna import gait
    from plandscape.fauna.bodies import _pitch, posed_legs, rig
    from plandscape.mesh import Mesh
    from plandscape.paths.desire import obstacle_cost, simulate
    from plandscape.render import render
    from plandscape.terrain.heightfield import generate_tile
    rg = rig("great_blue_heron", A.FAUNA["great_blue_heron"].rgb)
    frames = []
    for k in range(4):
        roll = gait.FLAP_AMP * np.sin(2 * np.pi * k / 4)
        parts = [rg["torso"]]
        n = rg["neck"]
        parts.append(Mesh(_pitch(n["mesh"].positions, -gait.HEAD["fly"] * n["graze"]) + np.asarray(n["pivot"], np.float32),
                          n["mesh"].colors, n["mesh"].indices))
        parts += posed_legs(rg, [gait.TRAIL] * len(rg["legs"]))
        for w in rg["wings"]:
            a = w["side"] * roll
            c, s_ = np.cos(a), np.sin(a)
            R = np.array([[1, 0, 0], [0, c, -s_], [0, s_, c]], np.float32)
            parts.append(Mesh(w["mesh"].positions @ R.T + np.asarray(w["pivot"], np.float32), w["mesh"].colors,
                              w["mesh"].indices))
        frames.append(render(parts, None, size=(300, 240), azimuth=35, elevation=18, keep_first=99,
                             fit=((-0.6, -1.0, 0.3), (0.6, 1.0, 1.3))))
    hf = generate_tile(96, 1.0, "floodplain", 3)
    z = np.zeros_like(hf.z)
    f, _ = simulate(hf, [(5, 5, 1), (90, 90, 1)], n_trips=4, seed=1)
    w = A.World(hf, f, obstacle_cost(hf), z, z, z, np.zeros((0, 4)))
    h = A.spawn(w, {"great_blue_heron": 1}, seed=1)[0]
    h.state, h.timer = "fly", 8.0
    t = 0.0
    while t < 14:
        h.step(w, [h], t, 0.25)
        t += 0.25
    tt = np.array([l[0] for l in h.log])
    alt = np.array([l[3] - w.z(l[1], l[2]) for l in h.log])
    air = np.array([l[5] == "fly" for l in h.log])
    wk, roll, span = gait.wing_track(tt, air)
    fig, ax = plt.subplots(1, 2, figsize=(12, 3.2))
    ax[0].plot(tt, alt, color="#1f6f8b")
    ax[0].set_ylabel("height above ground (m)")
    ax[0].set_xlabel("time (s)")
    ax[1].plot(wk, np.degrees(roll), lw=0.8, color="#7d5ba6", label="wing roll (deg)")
    ax[1].plot(wk, span * 40, color="0.5", label="span × 40")
    ax[1].set_xlabel("time (s)")
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    tmp = path + ".plot.png"
    fig.savefig(tmp, dpi=80)
    plt.close(fig)
    top = np.concatenate(frames, 1)
    plot = np.asarray(Image.open(tmp).convert("RGB").resize((top.shape[1], int(top.shape[1] * 3.2 / 12))))
    Image.fromarray(np.concatenate([top, plot], 0)).save(path)
    return path


def _wind_tree(species="white_oak", season="summer"):
    from plandscape.flora.tree import generate_tree
    from plandscape.wind.attrs import tree_attributes, unpack
    tm = generate_tree(species, seed=(0, 1), detail="low", season=season)
    tw, at = tree_attributes(tm, season)
    return tm, tw, {k: unpack(v) for k, v in at.items()}


def wind_sheet(path):
    """The wind model (§34): gust spectrum through each level's filter, sway at two forces, the travelling gust
    field, Beaufort calibration, and trunk frequencies against measured trees."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from plandscape.flora.tree import generate_tree
    from plandscape.wind import Wind, response, sway
    from plandscape.wind.field import LAND, kaimal_u
    from plandscape.wind.response import mechanics, transfer
    tm, tw, A = _wind_tree()
    F_ = A["foliage"]
    P = tm.foliage.positions.astype(float)
    N = tm.foliage.normals().astype(float)
    inst = dict(x=0.0, y=0.0, yaw=0.0, scale=1.0, f0=tw.f0, zeta=tw.zeta, Q=tw.Q_ref, shelter=1.0)
    fig, ax = plt.subplots(2, 3, figsize=(21, 11))
    # 1 spectrum and filters
    w = Wind(force=5, canopy_h=tw.H, seed=3)
    f = np.geomspace(0.005, 20, 400)
    zr = w.h + 2
    S = kaimal_u(f, zr, w.Uh, w.ustar)
    a = ax[0, 0]
    a.loglog(f, f * S / (f * S).max(), color="0.3", lw=2, label="Kaimal  f S_u(f), normalised")
    a.plot(w.comps["f"], (w.comps["au"] ** 2) / (w.comps["au"] ** 2).max(), "o", color="0.2", ms=5,
           label=f"the {len(w.comps['f'])} sinusoids (a_k², normalised)")
    def typical(v):  # a representative vertex: the one nearest the 80th percentile of the moving ones
        m = v > 0
        q = np.percentile(v[m], 80)
        return int(np.nonzero(m)[0][np.argmin(np.abs(v[m] - q))])
    i1 = typical(F_["d1"] * (F_["d2"] == 0))
    i2 = typical(F_["d2"])
    for fn, z_, lab, c in ((tw.f0, tw.zeta, f"trunk f0 = {tw.f0:.2f} Hz, ζ = {tw.zeta:.3f}", "#1f6f8b"),
                           (F_["f1"][i1], response.ZETA_BRANCH, f"limb f1 = {F_['f1'][i1]:.2f} Hz", "#2e8b57"),
                           (F_["f2"][i2], response.ZETA_BRANCH, f"branch f2 = {F_['f2'][i2]:.2f} Hz", "#b8860b"),
                           (sway.FLUTTER_HZ, 0.1, f"leaf flutter {sway.FLUTTER_HZ:.0f} Hz (driven, not filtered)", "#c0392b")):
        g, _ = transfer(f, fn, z_)
        a.loglog(f, g ** 2 / g.max() ** 2, color=c, lw=1.2, ls="--" if "leaf" in lab else "-", label="|H|²: " + lab)
    a.set_ylim(1e-4, 2)
    a.set_xlabel("frequency (Hz)")
    a.set_title("gusts (Kaimal) and each level's transfer function")
    a.legend(fontsize=8, loc="lower left")
    # 2 sway time series
    a = ax[0, 1]
    t = np.arange(0, 60, 0.1)
    for F, ls in ((3, ":"), (6, "-")):
        w = Wind(force=F, canopy_h=tw.H, seed=3)
        q = sway.trunk(w, inst, t)
        D = np.stack([sway.displace(w, inst, P[[i1, i2]], {k: v[[i1, i2]] for k, v in F_.items()}, N[[i1, i2]], tt)
                      for tt in t])
        along = lambda d: d[..., :2] @ w.dir  # noqa: E731
        a.plot(t, along(q), ls, color="#1f6f8b", lw=1.2, label=f"trunk top, Beaufort {F}")
        a.plot(t, along(D[:, 0]), ls, color="#2e8b57", lw=0.9, label=f"limb-tip leaf, Beaufort {F}")
        a.plot(t, along(D[:, 1]), ls, color="#b8860b", lw=0.7, label=f"branch-tip leaf, Beaufort {F}")
    a.set_xlabel("time (s)")
    a.set_ylabel("along-wind displacement (m)")
    a.set_title(f"a {tw.H:.0f} m white oak: static lean + gusts")
    a.legend(fontsize=7, ncol=2)
    # 3 gust field
    a = ax[0, 2]
    w = Wind(force=5, from_deg=225, canopy_h=22, seed=3)
    x = np.linspace(0, 128, 200)
    X, Y = np.meshgrid(x, x)
    g0, _ = w.gust(X, Y, 0.0)
    g6, _ = w.gust(X, Y, 6.0)
    im = a.imshow(g0, origin="lower", extent=(0, 128, 0, 128), cmap="RdBu_r", vmin=-1.2, vmax=1.2)
    a.contour(X, Y, g6, levels=[0.6], colors="k", linewidths=0.8)
    plt.colorbar(im, ax=a, fraction=0.04, label="u'/U at t = 0")
    a.annotate("", xy=(64 + 30 * w.dir[0], 64 + 30 * w.dir[1]), xytext=(64, 64),
               arrowprops=dict(arrowstyle="->", lw=2, color="k"))
    a.set_title(f"along-wind gusts at t = 0; black: cores (u'/U = 0.6) at t = 6 s,\n{6 * w.Uc:.0f} m further downwind (U_c = {w.Uc:.1f} m/s)")
    a.set_aspect("equal")
    a.set_xlabel("x east (m)")
    a.set_ylabel("y north (m)")
    # 4 Beaufort calibration
    a = ax[1, 0]
    forces = np.arange(0, 11)
    rows = {"leaves (flutter + reconfiguration)": [], "small branches": [], "limbs": [], "trunk top": []}
    tt = np.arange(0, 40, 0.2)
    il = typical(F_["lever"])
    for F in forces:
        w = Wind(force=F, canopy_h=tw.H, seed=3)
        q = sway.trunk(w, inst, tt)
        sel = [il, i2, i1]
        D = np.stack([sway.displace(w, inst, P[sel], {k: v[sel] for k, v in F_.items()}, N[sel], x_) for x_ in tt])
        rows["trunk top"].append(np.linalg.norm(q - q.mean(0), axis=1).mean())
        for name, j in (("leaves (flutter + reconfiguration)", 0), ("small branches", 1), ("limbs", 2)):
            d = D[:, j] - (q * np.array([1, 1, 0]))[:, :] * F_["phi"][sel[j]]
            rows[name].append(np.linalg.norm(d - d.mean(0), axis=1).mean())
    for (name, v), c in zip(rows.items(), ("#c0392b", "#b8860b", "#2e8b57", "#1f6f8b")):
        a.semilogy(forces, np.maximum(v, 1e-4), "o-", color=c, label=name)
    a.set_ylim(1e-4, 3)
    for F in (2, 3, 4, 5, 6, 7, 8):
        a.axvline(F, color="0.9", lw=0.6, zorder=0)
        a.text(F + 0.08, 1.2e-4, LAND[F], fontsize=6.5, rotation=90, va="bottom", ha="left", color="0.35")
    a.set_xlabel("Beaufort force")
    a.set_ylabel("mean |motion| about the mean (m)")
    a.set_title("calibration against the Beaufort land descriptions (NOAA)")
    a.legend(fontsize=8, loc="upper left")
    # 5 trunk frequency check
    a = ax[1, 1]
    from plandscape.flora.species import SPECIES
    for k in SPECIES:
        if SPECIES[k].leaf == "palm":
            continue
        tw_s, _ = mechanics(generate_tree(k, seed=(0, 1), detail="low"))
        a.plot(tw_s.H, tw_s.f0, "o", color="#2e8b57" if SPECIES[k].leaf == "broadleaf" else "#1f6f8b")
        a.annotate(SPECIES[k].common, (tw_s.H, tw_s.f0), fontsize=7, xytext=(3, 2), textcoords="offset points")
        if SPECIES[k].deciduous:
            tw_w, _ = mechanics(generate_tree(k, seed=(0, 1), detail="low", season="winter"), "winter")
            a.plot(tw_w.H, tw_w.f0, "x", color="0.4")
    a.plot(19.7, 0.34, "*", ms=14, color="#c0392b", label="measured: open-grown silver maple, 19.7 m (James 2014)")
    a.axhline(0.26, ls=":", color="#c0392b", label="sycamore f0 = 0.26 Hz (Jackson et al. 2019)")
    a.set_xlabel("tree height (m)")
    a.set_ylabel("first sway frequency f0 (Hz)")
    a.set_title("Rayleigh f0 of every species: o in leaf, x bare (bare/leafy ≈ 1.2; measured 1.18)")
    a.legend(fontsize=8)
    # 6 long exposure
    a = ax[1, 2]
    w = Wind(force=6, canopy_h=tw.H, seed=3)
    pick = np.random.default_rng(0).choice(len(P), min(2500, len(P)), replace=False)
    for k_, tt_ in enumerate(np.arange(0, 4, 0.25)):
        d = sway.displace(w, inst, P[pick], {k: v[pick] for k, v in F_.items()}, N[pick], 20 + tt_)
        Q = P[pick] + d
        a.scatter(Q[:, :2] @ w.dir, Q[:, 2], s=0.6, color=plt.cm.viridis(k_ / 16), alpha=0.5)
    B = tm.bark.positions
    a.scatter(B[::3, :2] @ w.dir, B[::3, 2], s=0.3, color="0.3")
    a.set_aspect("equal")
    a.set_title("4 s long exposure at Beaufort 6 (leaf positions every 0.25 s, colour = time)")
    a.set_xlabel("along-wind (m)")
    fig.tight_layout()
    fig.savefig(path, dpi=75)
    plt.close(fig)
    return path


def wind_specimen(path, species="white_oak", force=6, frames=16, dt=0.2):
    """A rendered tree swaying (animated GIF), evaluated with the viewer's own equations (sway.py)."""
    import numpy as np
    from plandscape.mesh import Mesh
    from plandscape.render import render
    from plandscape.wind import Wind, sway
    tm, tw, A = _wind_tree(species)
    w = Wind(force=force, from_deg=270, canopy_h=tw.H, seed=3)
    inst = dict(x=0.0, y=0.0, yaw=0.0, scale=1.0, f0=tw.f0, zeta=tw.zeta, Q=tw.Q_ref, shelter=1.0)
    R = max(np.abs(tm.foliage.positions[:, :2]).max(), 4) * 1.4
    fit = ((-R, -R, 0.0), (R, R, tw.H * 1.05))
    imgs = []
    for k in range(frames):
        t = 30 + k * dt
        ms = []
        for name, m in (("bark", tm.bark), ("foliage", tm.foliage)):
            d = sway.displace(w, inst, m.positions.astype(float), A[name], m.normals().astype(float), t)
            ms.append(Mesh((m.positions + d).astype(np.float32), m.colors, m.indices, m.uvs, m.texture, nrm=m.nrm))
        imgs.append(Image.fromarray(render(ms, None, size=(420, 460), azimuth=0.0, elevation=8.0, fit=fit,
                                           keep_first=2)))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=int(dt * 1000), loop=0)
    return path


def perception_sheet(path, scene="monte-sano"):
    """How animals sense the player (§35): scent plume, footsteps against wind noise, sight and flight distance,
    and the alarm of a deer approached up- and downwind."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from plandscape.fauna import perception as P
    from plandscape.wind import Wind
    d = os.path.join(ROOT, "out", scene)
    s = json.load(open(os.path.join(d, "scene.json")))
    Ls = np.load(os.path.join(d, "layers.npz"))
    wj = s["wind"]
    w = Wind(force=3, from_deg=wj["from_deg"], canopy_h=wj["canopy_h"], seed=s["plan"]["seed"])
    S = s["plan"]["size_m"]
    px, py = S / 2, S / 2
    x = np.linspace(0, S, 200)
    X, Y = np.meshgrid(x, x)
    fig, ax = plt.subplots(2, 3, figsize=(21, 12.5))
    # 1 scent: deer salience around a standing player, at one instant (the plume meanders with v')
    a = ax[0, 0]
    a.imshow(Ls["canopy"], origin="lower", extent=(0, S, 0, S), cmap="Greens", alpha=0.35, vmin=0, vmax=1.4)
    for t, c in ((0.0, "#c0392b"), (20.0, "#7d5ba6"), (40.0, "#1f6f8b")):
        vx, vy = w.at(px, py, 1.5, t, 0.8)
        U = float(np.hypot(vx, vy))
        ux, uy = vx / U, vy / U
        along = (X - px) * ux + (Y - py) * uy
        across = -(X - px) * uy + (Y - py) * ux
        sal = np.vectorize(lambda a_, b_: P.smell("white_tailed_deer", a_, b_, U))(along, across)
        a.contour(X, Y, sal, levels=[0.3, 0.99], colors=c, linewidths=[0.8, 1.6])
        a.plot([], [], color=c, label=f"t = {t:.0f} s, U = {U:.1f} m/s")
    a.plot(px, py, "k*", ms=14, label="player")
    a.set_title("where a deer smells you (salience 0.3 and 1), Beaufort 3:\nthe plume swings with the gusts")
    a.legend(fontsize=8, loc="lower left")
    a.set_aspect("equal")
    # 2 hearing: footsteps on leaf litter, audible range by wind
    a = ax[0, 1]
    dist = np.linspace(1, 120, 300)
    for U, c in ((0.2, "#1f6f8b"), (0.5, "#2e8b57"), (1.0, "#b8860b"), (2.0, "#c0392b"), (4.0, "#7d5ba6")):
        L = P.STEP_DB["walk"] + P.GROUND_DB["litter"]
        h = [P.hearing("white_tailed_deer", L, r, 0, U) for r in dist]
        a.plot(dist, h, color=c, label=f"wind {U} m/s at 1.5 m: noise {P.wind_noise(U):.0f} dBA")
    a.plot(dist, [P.hearing("white_tailed_deer", P.CLAP_DB, r, 0, 1.0) for r in dist], "k--", label="a clap, wind 1 m/s")
    a.set_xlabel("distance (m)")
    a.set_ylabel("hearing salience")
    a.set_title("footsteps in leaf litter, heard by a deer:\n\"when the wind blows you can move\" (TPWD)")
    a.legend(fontsize=8)
    # 3 sight
    a = ax[0, 2]
    for sp, c in (("wild_turkey", "#b8860b"), ("white_tailed_deer", "#c0392b"), ("gray_squirrel", "#7d5ba6"),
                  ("armadillo", "#2e8b57")):
        a.plot(dist, [P.sight(sp, r, 0.0, P.WALK) for r in dist], color=c, label=f"{sp.replace('_', ' ')}, walking")
        a.plot(dist, [P.sight(sp, r, 0.0, 0.0, "crouch") for r in dist], ":", color=c)
    a.plot(dist, [P.sight("white_tailed_deer", r, 0.0, P.WALK, intensity=0.3) for r in dist], "--", color="#c0392b",
           label="deer at dusk (twilight eyes)")
    a.axhline(P.A_ALERT, color="0.5", lw=0.8)
    a.text(118, P.A_ALERT + 0.01, "alert", ha="right", fontsize=8, color="0.4")
    a.set_xlabel("distance (m)")
    a.set_ylabel("sight salience (dotted: crouched and still)")
    a.set_title("sight: acuity × field of view × motion × posture × light × e^{−d/R}")
    a.legend(fontsize=8)
    # 4 flight-initiation distance
    a = ax[1, 0]
    v = np.linspace(0.2, 4.5, 100)
    for sp, c in (("great_blue_heron", "#1f6f8b"), ("white_tailed_deer", "#c0392b"), ("wild_turkey", "#b8860b"),
                  ("gray_squirrel", "#7d5ba6")):
        a.plot(v, [P.fid(sp, u, 1.0) for u in v], color=c, label=sp.replace("_", " ") + ", straight at it")
        a.plot(v, [P.fid(sp, u, 0.0) for u in v], ":", color=c)
    for hb in (0.5, 1.0, 1.5):
        a.plot(v, [P.fid("gray_squirrel", u, 1.0, habit=hb) for u in v], "--", color="#7d5ba6", lw=0.7)
    a.axhline(9.2, color="#7d5ba6", lw=0.5)
    a.text(4.4, 9.6, "squirrels, urban parks: 9.2 m", ha="right", fontsize=8, color="#7d5ba6")
    a.set_xlabel("player speed (m/s)")
    a.set_ylabel("flight-initiation distance (m)")
    a.set_title("FID: faster and more direct = farther (dotted: passing by;\ndashed: a squirrel fed 2, 4, 5 times)")
    a.legend(fontsize=8)
    # 5 alarm traces: walking at a deer from 150 m, up- vs downwind
    a = ax[1, 1]
    for k, (label, c) in enumerate((("player downwind of the deer", "#1f6f8b"), ("player upwind (scent reaches it)", "#c0392b"),
                                     ("player upwind, crouched and creeping", "#7d5ba6"))):
        m = P.Mind("white_tailed_deer")
        dd, tt, al, states = 150.0, [], [], []
        speed = 0.6 if k == 2 else P.WALK
        for i in range(2400):
            t = i * 0.1
            sig = P.sight("white_tailed_deer", dd, 0.3, speed, "crouch" if k == 2 else "stand", 0.6, P.COVER_K * 0.2 * dd)
            hear = P.hearing("white_tailed_deer", P.STEP_DB["crouch" if k == 2 else "walk"] + P.GROUND_DB["litter"], dd,
                             0.5 * dd, 0.8)
            sm = P.smell("white_tailed_deer", dd, 2.0, 2.0) if k else 0.0
            D = P.fid("white_tailed_deer", speed, 1.0, m.sens, m.habit)
            m.step(0.1, P.combine(sig, hear, sm), dd, D)
            tt.append(t)
            al.append(m.alarm)
            states.append(m.state)
            if m.state == "flee":
                break
            dd = max(dd - speed * 0.1, 1.0)
        a.plot(tt, al, color=c, label=f"{label}: {'flees' if states[-1] == 'flee' else states[-1]} at {dd:.0f} m")
    a.axhline(P.A_ALERT, color="0.5", lw=0.8)
    a.axhline(P.A_FLEE, color="0.3", lw=0.8)
    a.set_xlabel("time (s), walking straight at a deer from 150 m (20 % cover)")
    a.set_ylabel("alarm")
    a.set_title("alarm: follows the strongest cues up in ~1 s, lets go over ~20 s")
    a.legend(fontsize=8)
    # 6 people: Hall's zones and Kendon's greeting phases
    a = ax[1, 2]
    for r, name, c in ((7.6, "public: distance salutation (a nod)", "#dfe8d8"), (3.7, "social: close salutation, chat", "#c9dcc0"),
                       (1.22, "personal: sidestep", "#a8c79a")):
        a.add_patch(plt.Circle((0, 0), r, color=c, ec="0.5"))
        a.text(0, r - 0.45, name, ha="center", fontsize=9)
    a.plot(0, 0, "o", color="#34415a", ms=12)
    a.text(0, -0.6, "hiker", ha="center", fontsize=9)
    a.set_xlim(-9, 9)
    a.set_ylim(-9, 9)
    a.set_aspect("equal")
    a.set_title("people keep Hall's distances; a clap within 6 m or a run at them\nmakes them wary (no more greetings, 3.7 m kept)")
    fig.tight_layout()
    fig.savefig(path, dpi=72)
    plt.close(fig)
    return path


def play_sheet(path, scene="walk"):
    """The player walks in (§35): headless play test on a fixed clock; four moments and the event log."""
    import subprocess
    d = os.path.join(ROOT, "out", scene)
    shot = os.path.join(d, "play.png")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "play_check.py"), d, shot], capture_output=True,
                       text=True, timeout=1800)
    log = [ln for ln in r.stdout.splitlines() if "·" in ln][:34]
    base = os.path.splitext(shot)[0]
    ims = [Image.open(f"{base}-{n}.png").convert("RGB").resize((770, 490)) for n in ("smell", "flee", "food", "people")]
    W = Image.new("RGB", (1540 + 560, 980), (247, 248, 242))
    for i, im in enumerate(ims):
        W.paste(im, ((i % 2) * 770, (i // 2) * 490))
    dr = ImageDraw.Draw(W)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = None
    y = 10
    for ln in log:
        dr.text((1550, y), ln.replace("<b>", "").replace("</b>", "")[:70], fill=(31, 38, 32), font=font)
        y += 28
    W.save(path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    stats = {}
    for name, prompt in SCENES.items():
        d = os.path.join(ROOT, "out", name)
        if not a.reuse or not os.path.exists(os.path.join(d, "preview.png")):
            from plandscape.__main__ import main as run
            run([prompt, "--out", d])
        for img in ("preview", "closeup", "homestead", "creek", "map"):
            if os.path.exists(os.path.join(d, f"{img}.png")):
                _jpeg(os.path.join(d, f"{img}.png"), os.path.join(OUT, f"{name}-{img}.jpg"))
        s = json.load(open(os.path.join(d, "scene.json")))["stats"]
        stats[name] = {k: s.get(k) for k in ("glb_mb", "trees", "tree_tris", "ground_props", "agents", "signs")}
    _jpeg(terrain_sheet(os.path.join(ROOT, "out", "terrain.png")), os.path.join(OUT, "terrain-erosion.jpg"), 1500)
    _jpeg(creek_sheet(os.path.join(ROOT, "out", "creeks.png")), os.path.join(OUT, "creeks.jpg"), 1500)
    _jpeg(gait_sheet(os.path.join(ROOT, "out", "gaits.png")), os.path.join(OUT, "gaits.jpg"), 1600)
    _jpeg(pose_sheet(os.path.join(ROOT, "out", "poses.png")), os.path.join(OUT, "poses.jpg"), 1100)
    _jpeg(motion_sheet(os.path.join(ROOT, "out", "motion.png")), os.path.join(OUT, "motion.jpg"), 1200)
    _jpeg(fauna_sheet(os.path.join(ROOT, "out", "fauna.png")), os.path.join(OUT, "fauna.jpg"), 1500)
    _jpeg(flight_sheet(os.path.join(ROOT, "out", "flight.png")), os.path.join(OUT, "flight.jpg"), 1200)
    _jpeg(wind_sheet(os.path.join(ROOT, "out", "wind.png")), os.path.join(OUT, "wind.jpg"), 1600)
    wind_specimen(os.path.join(OUT, "wind-oak.gif"))
    _jpeg(perception_sheet(os.path.join(ROOT, "out", "perception.png")), os.path.join(OUT, "perception.jpg"), 1600)
    _jpeg(play_sheet(os.path.join(ROOT, "out", "play-sheet.png")), os.path.join(OUT, "play.jpg"), 1700)
    for season in ("summer", "fall"):
        p = species_sheet(os.path.join(ROOT, "out", f"species_{season}.png"), season)
        _jpeg(p, os.path.join(OUT, f"species-{season}.jpg"), width=1500)
    with open(os.path.join(OUT, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()

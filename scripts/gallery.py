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
    "bayou": "cypress bayou floodplain with a shotgun house and an armadillo at noon in summer",
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
    fig, ax = plt.subplots(1, 2, figsize=(15, 5))
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
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)
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
    for season in ("summer", "fall"):
        p = species_sheet(os.path.join(ROOT, "out", f"species_{season}.png"), season)
        _jpeg(p, os.path.join(OUT, f"species-{season}.jpg"), width=1500)
    with open(os.path.join(OUT, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()

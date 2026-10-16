"""Review images for a composed scene: a perspective render and an annotated map."""

from __future__ import annotations

import numpy as np

from ..mesh import Mesh
from ..render import render


def _rotz(theta, t, s):
    c, si = np.cos(theta), np.sin(theta)
    M = np.eye(4)
    M[:3, :3] = np.array([[c, -si, 0], [si, c, 0], [0, 0, 1]]) * s
    M[:3, 3] = t
    return M


def _scene_meshes(res, near=None, foliage=True):
    """Scene meshes in world space; `near=(x, y, r)` keeps only trees and props within r metres."""
    meshes = [res["ter"], res["grass"], res["built"], res["water"]] + ([res["road"]] if res.get("road") is not None else [])
    def ok(o):
        return near is None or np.hypot(o["x"] - near[0], o["y"] - near[1]) < near[2]
    for pl in res["placements"]:
        if not ok(pl):
            continue
        tm = res["variants"][pl["model"]]
        M = _rotz(pl["yaw"], (pl["x"], pl["y"], pl["z"]), pl["scale"])
        meshes += [tm.bark.transformed(M)] + ([tm.foliage.transformed(M)] if foliage else [])
    for gp in res.get("ground_props", []):
        if not ok(gp):
            continue
        M = _rotz(gp["yaw"], (gp["x"], gp["y"], gp["z"]), gp["scale"])
        meshes.append(res["prop_parts"][gp["model"]].mesh.transformed(M))
    return meshes


def perspective(res, path, size=(1100, 720)):
    meshes = _scene_meshes(res)
    light = res["light"]
    S = res["hf"].size[0]
    zc = float(res["hf"].z.mean())
    fit = ((S * 0.15, S * 0.15, zc - 2), (S * 0.85, S * 0.85, zc + 22))  # frame the centre of the tile
    # review render uses neutral late-morning light so form and colour are judgeable;
    # the viewer applies the scene's real time-of-day lighting
    return render(meshes, path, size=size, azimuth=200, elevation=16, fit=fit,
                  sky=(0.70, 0.80, 0.90), sun=(0.35, -0.45, 0.8), max_tris=1_200_000, keep_first=5)


def _crop(m, box):
    """Keep triangles whose centroid lies in an xy box (the preview renderer has no near clip)."""
    if m is None or not m.n_tris:
        return m
    cen = m.positions[m.indices].mean(1)
    keep = (cen[:, 0] > box[0]) & (cen[:, 0] < box[2]) & (cen[:, 1] > box[1]) & (cen[:, 1] < box[3])
    return Mesh(m.positions, m.colors, m.indices[keep], m.uvs, m.texture, m.weights, m.splat)


def closeup(res, path, size=(1100, 720)):
    """Ground-level review of the focus area, where textures and imported props matter most.
    Tree crowns are left out (trunks stay) so they don't hide the ground."""
    S = res["hf"].size[0]
    cx = cy = S / 2
    gp = res.get("ground_props", [])
    if gp:  # centre on the busiest patch of ground props
        xy = np.array([(g["x"], g["y"]) for g in gp])
        n = (np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1)) < 5).sum(1)
        cx, cy = xy[int(np.argmax(n))]
    cx, cy = float(round(cx)) + 0.25, float(round(cy)) + 0.25  # crop box off the grid lines: clean edges
    zc = float(res["hf"].sample(cx, cy)[0])
    meshes = [_crop(m, (cx - 9, cy - 9, cx + 9, cy + 9))
              for m in _scene_meshes(res, near=(cx, cy, 9), foliage=False)]
    fit = ((cx - 6, cy - 6, zc - 1), (cx + 6, cy + 6, zc + 2))
    return render(meshes, path, size=size, azimuth=200, elevation=14, fit=fit,
                  sky=(0.70, 0.80, 0.90), sun=(0.35, -0.45, 0.8), max_tris=1_500_000, keep_first=5)


def homestead(res, path, size=(1100, 720)):
    """The first building seen from across the road: road, ditch, fence, mailbox, porch (crowns left out)."""
    if not res.get("buildings"):
        return None
    mx, my = res["buildings"][0]["mailbox"]
    cx, cy = float(round(mx)) + 0.25, float(round(my + 2)) + 0.25  # crop box off the grid lines
    z = float(res["hf"].sample(cx, cy)[0])
    meshes = [_crop(m, (cx - 16, cy - 12, cx + 16, cy + 16))
              for m in _scene_meshes(res, near=(cx, cy, 16), foliage=False)]
    return render(meshes, path, size=size, azimuth=20, elevation=22, fit=((cx - 12, cy - 8, z - 2), (cx + 12, cy + 12, z + 5)),
                  sky=(0.70, 0.80, 0.90), sun=(0.35, -0.45, 0.8), max_tris=1_500_000, keep_first=5)


def creek(res, path, size=(1100, 720)):
    """The creek where it is widest in the middle of the tile: banks, bed cut, water surface (crowns left out)."""
    from ..terrain.refine import creek_focus
    f = creek_focus(res["hf"])  # the same point the near-terrain window is centred on
    if f is None:
        return None
    cx, cy = float(round(f[0])) + 0.25, float(round(f[1])) + 0.25  # box edges off the grid lines: clean crop
    r = 10.0
    meshes = [_crop(m, (cx - r, cy - r, cx + r, cy + r))
              for m in _scene_meshes(res, near=(cx, cy, r), foliage=False)]
    gx, gy = np.meshgrid(np.linspace(cx - r, cx + r, 21), np.linspace(cy - r, cy + r, 21))
    zs = res["hf"].sample(gx.ravel(), gy.ravel())  # frame the real relief: creeks often sit in steep ravines
    fit = ((cx - r, cy - r, float(zs.min()) - 1), (cx + r, cy + r, float(zs.max()) + 1))
    return render(meshes, path, size=size, azimuth=200, elevation=35, fit=fit,
                  sky=(0.70, 0.80, 0.90), sun=(0.35, -0.45, 0.8), max_tris=1_500_000, keep_first=5)


def map_view(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    hf, field = res["hf"], res["field"]
    S = hf.size[0]
    ls = LightSource(azdeg=315, altdeg=40)
    shade = ls.hillshade(hf.z, vert_exag=2.0, dx=hf.res, dy=hf.res)
    fig, ax = plt.subplots(figsize=(8.5, 8.5), dpi=110)
    ax.imshow(shade, origin="lower", cmap="gray", extent=(0, S, 0, S), alpha=0.9)
    ax.imshow(np.ma.masked_less(res["canopy"], 0.15), origin="lower", cmap="Greens", extent=(0, S, 0, S),
              alpha=0.45, vmin=0, vmax=1.2)
    ax.imshow(np.ma.masked_less(field.G, 0.12), origin="lower", cmap="Oranges", extent=(0, S, 0, S), alpha=0.85)
    ax.imshow(np.ma.masked_less(hf.layers["water"], 0.5), origin="lower", cmap="Blues", extent=(0, S, 0, S),
              alpha=0.9, vmin=0, vmax=1.2)
    for pl in res["placements"]:
        ax.plot(pl["x"], pl["y"], ".", color="darkgreen", ms=3)
    colors = {"white_tailed_deer": "saddlebrown", "gray_squirrel": "gray", "wild_turkey": "black",
              "armadillo": "tan", "coyote": "goldenrod", "human": "royalblue"}
    seen = set()
    for a in res["agents"]:
        L = np.array([(l[1], l[2]) for l in a.log])
        lab = a.spec.common if a.spec.key not in seen else None
        seen.add(a.spec.key)
        ax.plot(L[:, 0], L[:, 1], "-", lw=1, color=colors.get(a.spec.key, "k"), label=lab, alpha=0.85)
        ax.plot(L[-1, 0], L[-1, 1], "o", ms=4, color=colors.get(a.spec.key, "k"))
    for s in res["world"].signs:
        ax.plot(s["x"], s["y"], "x", ms=4, color="purple")
    ax.set_xlim(0, S)
    ax.set_ylim(0, S)
    nm = res.get("names") or {}
    if res.get("road_line") is not None and nm.get("road"):
        rl = res["road_line"]
        k = len(rl) // 2
        d = rl[min(k + 3, len(rl) - 1)] - rl[max(k - 3, 0)]
        below = rl[k, 1] > 12  # keep the label inside the map when the road hugs the south edge
        ax.text(rl[k, 0], rl[k, 1] + (-3.5 if below else 3.5), nm["road"], fontsize=8, ha="center",
                va="top" if below else "bottom", color="#5a3a1a",
                rotation=float(np.degrees(np.arctan2(d[1], d[0]))), style="italic")
    wy_, wx_ = np.nonzero(hf.layers["water"] > 0.5)
    if nm.get("creek") and len(wx_):
        k = len(wx_) // 2
        ax.text(wx_[k] * hf.res, wy_[k] * hf.res + 3, nm["creek"], fontsize=8, color="#1f4e79", style="italic",
                ha="center")
    for b in res.get("buildings") or []:
        ax.plot(b["x"], b["y"], "s", ms=6, color="#7a4a2a")
        if b.get("name"):
            ax.text(b["x"], b["y"] + 3, b["name"], fontsize=7, ha="center", color="#3a2a1a")
    ax.set_title("trails (orange) · canopy (green) · animal tracks · signs (x)", fontsize=9)
    ax.legend(loc="upper right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path

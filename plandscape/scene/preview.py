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


def perspective(res, path, size=(1100, 720)):
    meshes = [res["ter"], res["grass"], res["built"], res["water"]]
    for pl in res["placements"]:
        tm = res["variants"][pl["model"]]
        M = _rotz(pl["yaw"], (pl["x"], pl["y"], pl["z"]), pl["scale"])
        meshes += [tm.bark.transformed(M), tm.foliage.transformed(M)]
    light = res["light"]
    S = res["hf"].size[0]
    zc = float(res["hf"].z.mean())
    fit = ((S * 0.15, S * 0.15, zc - 2), (S * 0.85, S * 0.85, zc + 22))  # frame the centre of the tile
    # review render uses neutral late-morning light so form and colour are judgeable;
    # the viewer applies the scene's real time-of-day lighting
    return render(meshes, path, size=size, azimuth=200, elevation=16, fit=fit,
                  sky=(0.70, 0.80, 0.90), sun=(0.35, -0.45, 0.8), max_tris=1_200_000, keep_first=4)


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
    ax.set_title("trails (orange) · canopy (green) · animal tracks · signs (x)", fontsize=9)
    ax.legend(loc="upper right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path

"""Low-poly procedural bodies for animals and people (facing +x, z-up, feet at z=0).

Placeholders for the viewer; skeletal, gait-animated bodies are on the roadmap.
Each individual gets slight size/colour variation from its seed.
"""

from __future__ import annotations

import numpy as np

from ..mesh import Mesh, MeshBuilder, box


def ellipsoid(c, r, rgb, nu=10, nv=6):
    u = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    v = np.linspace(0, np.pi, nv + 1)
    U, V = np.meshgrid(u, v)
    P = np.stack([np.cos(U) * np.sin(V) * r[0], np.sin(U) * np.sin(V) * r[1], np.cos(V) * r[2]], -1).reshape(-1, 3) + c
    idx = []
    for i in range(nv):
        for j in range(nu):
            a, b = i * nu + j, i * nu + (j + 1) % nu
            idx += [(a, a + nu, b), (b, a + nu, b + nu)]
    mb = MeshBuilder()
    mb.add(P, rgb, idx)
    return mb.build()


def body(key, rgb, scale=1.0):
    rgb = np.asarray(rgb)
    parts = []
    if key in ("white_tailed_deer", "coyote"):
        L = 0.75 if key == "white_tailed_deer" else 0.5
        h = 0.95 if key == "white_tailed_deer" else 0.5
        parts += [ellipsoid((0, 0, h), (L, 0.22 * L / 0.75 + 0.05, 0.25 * L / 0.75 + 0.03), rgb),
                  ellipsoid((L * 0.8, 0, h + 0.3 * L), (0.12, 0.07, 0.25 * L), rgb),
                  ellipsoid((L * 1.05, 0, h + 0.55 * L), (0.2 * L / 0.75 + 0.05, 0.07, 0.08), rgb * 0.9)]
        for x in (-L * 0.6, L * 0.6):
            for y in (-0.1, 0.1):
                parts.append(box((x, y, h / 2), (0.06, 0.06, h), rgb * 0.8))
        tail = (0.95, 0.95, 0.92) if key == "white_tailed_deer" else rgb * 0.8
        parts.append(ellipsoid((-L * 1.0, 0, h + 0.05), (0.12, 0.05, 0.08), tail))
        if key == "coyote":
            parts.append(ellipsoid((-L * 1.2, 0, h - 0.1), (0.25, 0.06, 0.07), rgb * 0.75))
    elif key == "gray_squirrel":
        parts += [ellipsoid((0, 0, 0.1), (0.12, 0.05, 0.06), rgb),
                  ellipsoid((0.12, 0, 0.14), (0.05, 0.04, 0.04), rgb),
                  ellipsoid((-0.15, 0, 0.2), (0.06, 0.05, 0.14), rgb * 1.1)]
    elif key == "wild_turkey":
        parts += [ellipsoid((0, 0, 0.55), (0.32, 0.2, 0.22), rgb),
                  ellipsoid((0.3, 0, 0.82), (0.04, 0.04, 0.16), (0.55, 0.65, 0.75)),
                  ellipsoid((0.33, 0, 0.98), (0.06, 0.04, 0.05), (0.7, 0.15, 0.15)),
                  ellipsoid((-0.3, 0, 0.6), (0.12, 0.25, 0.08), rgb * 0.8)]
        for y in (-0.08, 0.08):
            parts.append(box((0.02, y, 0.18), (0.03, 0.03, 0.36), (0.6, 0.35, 0.3)))
    elif key == "armadillo":
        parts += [ellipsoid((0, 0, 0.14), (0.25, 0.12, 0.12), rgb),
                  ellipsoid((0.27, 0, 0.1), (0.08, 0.04, 0.04), rgb * 0.9),
                  ellipsoid((-0.33, 0, 0.08), (0.15, 0.025, 0.025), rgb * 0.9)]
    else:  # human
        parts += [box((0, 0, 0.45), (0.25, 0.32, 0.9), (0.25, 0.25, 0.3)),
                  box((0, 0, 1.2), (0.25, 0.42, 0.6), rgb),
                  ellipsoid((0, 0, 1.62), (0.11, 0.1, 0.13), (0.72, 0.55, 0.42))]
    m = Mesh.merge(parts)
    m.positions *= scale
    return m

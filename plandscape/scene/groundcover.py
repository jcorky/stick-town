"""Ground props near the camera: stumps, fallen logs, deadfall, mossy rocks, ferns, shrubs.

These are imported photoscans (plandscape.models), instanced from the library. They are
placed only in the central focus area where the eye lands, on habitat rules:
ferns under moist canopy, logs and deadfall under trees, rocks on slopes and on the
sandstone provinces, nothing on water, trails, roads or building footprints.
"""

from __future__ import annotations

import numpy as np

from .. import models
from ..rng import rng as make_rng

# per biome: model id → relative weight
MIX = {
    "hardwood": {"fern_02": 3, "rock_moss_set_01": 1.5, "rock_moss_set_02": 1.5, "boulder_01": 0.4,
                 "tree_stump_01": 1, "dead_tree_trunk": 0.8, "dead_tree_trunk_02": 0.8,
                 "dry_branches_medium_01": 3, "shrub_02": 2},
    # the stump scans are squat, root-spread hardwood stumps that read as mounds on open grass
    "pine_savanna": {"dead_tree_trunk": 1.2, "dead_tree_trunk_02": 0.6, "dry_branches_medium_01": 2.5,
                     "shrub_02": 0.6},
    "swamp": {"dead_tree_trunk_02": 2, "dead_tree_trunk": 1, "tree_stump_01": 1.5, "fern_02": 2.5,
              "dry_branches_medium_01": 1.5},
    "open": {"rock_moss_set_02": 0.5, "dead_tree_trunk": 0.4, "dry_branches_medium_01": 1},
}
MIX["pine_plantation"] = MIX["pine_savanna"]
DENSITY = {"hardwood": 0.045, "swamp": 0.03, "pine_savanna": 0.02, "pine_plantation": 0.018, "open": 0.005}
ROCKY = {"cumberland_plateau": 1.3, "ridge_and_valley": 1.1, "piedmont": 0.6}
SINK = {"stump": 0.12, "rock": 0.25, "boulder": 0.3, "log": 0.06, "deadfall": 0.02, "fern": 0.0, "shrub": 0.0}


def _habitat(role, canopy, moist, slope, rocky):
    if role == "fern":
        return 1.5 * canopy * np.clip((moist - 0.2) / 0.3, 0, 1)
    if role in ("log", "deadfall", "stump"):
        return 0.25 + canopy
    if role in ("rock", "boulder"):
        return rocky * (0.3 + np.clip(slope / 25, 0, 1.0))
    if role == "shrub":
        return 0.3 + canopy * (1 - canopy) * 2
    return 1.0


def scatter(hf, plan, store, canopy, trail, footprints, trunks, focus, log=print):
    """Return (placements, parts) where parts maps (id, variant) → models.Part."""
    mix = MIX.get(plan.biome, MIX["open"])
    rocky = ROCKY.get(plan.province, 0.3)
    parts = {}
    for mid in mix:
        got = models.variants(store, mid)
        if not got:
            try:  # first use on a networked machine: import into the library
                models.bake(store, [mid], log=log)
                got = models.variants(store, mid)
            except Exception as e:  # noqa: BLE001 - offline: scene simply has fewer props
                log(f"ground props: {mid} unavailable ({type(e).__name__})")
        for p in got:
            parts[(mid, p.meta["variant"])] = p
    ids = sorted({k[0] for k in parts})
    if not ids:
        return [], parts
    r = make_rng("groundcover", plan.seed)
    x0, y0, x1, y1 = focus
    n_target = int(DENSITY.get(plan.biome, DENSITY["open"]) * (x1 - x0) * (y1 - y0) * (1 + 0.3 * rocky))
    out, occ = [], []
    tr = np.asarray(trunks, float).reshape(-1, 4)
    for p in r.uniform([x0, y0], [x1, y1], (n_target * 15, 2)):
        if len(out) >= n_target:
            break
        x, y = float(p[0]), float(p[1])
        if float(hf.sample(x, y, "water")[0]) > 0.3 or trail(x, y) > 0.2:
            continue
        if any(a - 1 < x < c + 1 and b - 1 < y < d + 1 for (a, b, c, d) in footprints):
            continue
        cv, mo, sl = canopy(x, y), float(hf.sample(x, y, "moisture")[0]), float(hf.sample(x, y, "slope")[0])
        w = np.array([mix[i] * _habitat(models.MODELS[i][0], cv, mo, sl, rocky) for i in ids])
        if w.sum() < 1e-6:
            continue
        mid = ids[int(r.choice(len(ids), p=w / w.sum()))]
        vs = [k for k in parts if k[0] == mid]
        key = vs[int(r.integers(0, len(vs)))]
        part = parts[key]
        role = part.meta["role"]
        if role == "log" and sl > 22:
            continue
        rad = max(part.meta["size"][0], part.meta["size"][1]) / 2
        if occ and np.min(np.hypot(*(np.array(occ)[:, :2] - [x, y]).T) - np.array(occ)[:, 2]) < rad * 0.8:
            continue
        sc = float(r.uniform(0.8, 1.25))
        if len(tr) and np.min(np.hypot(tr[:, 0] - x, tr[:, 1] - y) - tr[:, 3] * 2.5) < 0.3 + rad * sc * 0.8:
            continue  # clear of trunks and their root flare, by the prop's own size (a 3 m log needs room)
        if role == "rock":
            sc *= float(r.uniform(1.0, 1.0 + 0.4 * rocky))  # sandstone blocks on the plateau run large
        yaw = float(r.uniform(0, 2 * np.pi))
        ang = np.linspace(0, 2 * np.pi, 6, endpoint=False)
        ring = np.c_[x + np.cos(ang) * rad * sc * 0.7, y + np.sin(ang) * rad * sc * 0.7]
        zs = hf.sample(ring[:, 0], ring[:, 1])
        z = float(min(zs.min(), hf.sample(x, y)[0])) - SINK.get(role, 0.05) * part.meta["size"][2] * sc
        occ.append((x, y, rad * sc))
        out.append(dict(model=key, role=role, x=x, y=y, z=z, yaw=yaw, scale=sc))
    return out, parts

"""ScenePlan → living scene → GLB + scene.json + previews.

Order matters because layers feed each other:
terrain → buildings/road → trees (habitat-suited) → canopy → desire paths
(around trunks and footprints) → animals (use cover, mast, trails; leave signs)
→ ground colour & grass (trampled where trails are) → export.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

import numpy as np
from scipy import ndimage

from ..assets.store import AssetStore, mesh_codec, store_behavior, terrain_codec, tree_codec
from ..export.gltf import GLB
from ..fauna.agents import FAUNA, World, run, spawn
from ..fauna.bodies import body
from ..flora.species import SPECIES
from ..flora.tree import generate_tree
from ..ground.surface import BIOME_GRASS, grass_density, grass_mesh, terrain_mesh
from ..mesh import Mesh, MeshBuilder
from ..paths.desire import TrailField, obstacle_cost, simulate
from ..rng import rng as make_rng
from ..terrain.heightfield import generate_tile
from .buildings import clothesline, fence, generate_building, mailbox
from .planner import ScenePlan

GRASS_BUDGET = {"low": 20000, "med": 70000, "high": 250000, "cm": 2_000_000}
VARIANTS = {"low": 2, "med": 3, "high": 5, "cm": 8}


def _rotz(theta, t=(0, 0, 0), s=1.0):
    c, si = np.cos(theta), np.sin(theta)
    M = np.eye(4)
    M[:3, :3] = np.array([[c, -si, 0], [si, c, 0], [0, 0, 1]]) * s
    M[:3, 3] = t
    return M


def sun_and_sky(hour):
    day = np.clip(np.sin(np.pi * (hour - 6.0) / 13.5), -0.3, 1)
    elev = max(day, -0.2) * 65
    az = 90 + (hour - 6.0) / 13.5 * 180  # east → south → west
    warm = np.exp(-((elev - 6) / 10) ** 2)
    blue = np.array([0.55, 0.72, 0.92]) * (0.25 + 0.75 * max(day, 0))
    sky = blue * (1 - 0.6 * warm) + np.array([0.95, 0.62, 0.45]) * 0.6 * warm * (0.4 + max(day, 0))
    a, e = np.radians(az), np.radians(max(elev, 2))
    sun = [float(np.sin(a) * np.cos(e)), float(np.cos(a) * np.cos(e)), float(np.sin(e))]
    return dict(sun_dir=sun, sun_elev=float(elev), sky=np.clip(sky, 0.03, 1).round(3).tolist(),
                sun_rgb=np.clip([1, 0.95 - 0.4 * warm, 0.88 - 0.6 * warm], 0, 1).round(3).tolist(),
                intensity=float(np.clip(day, 0.05, 1)))


def _poisson(r, n_try, bounds, min_d, ok_fn):
    pts = []
    x0, y0, x1, y1 = bounds
    cand = r.uniform([x0, y0], [x1, y1], (n_try, 2))
    for p in cand:
        if not ok_fn(p):
            continue
        if pts and np.min(np.hypot(*(np.array(pts)[:, :2] - p).T) - np.array(pts)[:, 2] - 0) < min_d(p):
            continue
        pts.append((p[0], p[1], min_d(p) * 0.5))
    return pts


def compose(plan: ScenePlan, out_dir: str, sim_seconds=180.0, log=print, store: AssetStore | None = None,
            library_pool=True):
    """library_pool=True draws trees from the shared library seeds (0, v) so scenes reuse
    pre-baked models; False gives every scene its own fresh variants."""
    store = store or AssetStore()
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    r = make_rng("compose", plan.seed)
    S = plan.size_m
    hf = store.get_or_build("terrain", dict(size=S, res=plan.res_m, province=plan.province, seed=plan.seed,
                                            creek=plan.creek),
                            lambda: generate_tile(S, plan.res_m, plan.province, plan.seed, creek=plan.creek),
                            *terrain_codec())
    bounds = (0.0, 0.0, S, S)
    water = hf.layers["water"]
    log(f"terrain {hf.shape} {plan.province} ({time.time() - t0:.1f}s)")

    # ── buildings, road, props ─────────────────────────────────────────
    footprints, doors, props, bmeshes, info = [], [], [], [], []
    road_y = 6.0
    if plan.buildings:
        xs = np.linspace(S * 0.2, S * 0.8, len(plan.buildings))
        for k, (kind, bx) in enumerate(zip(plan.buildings, xs)):
            bseed = [0, int(make_rng("bpick", plan.seed, k).integers(0, 4))] if library_pool else [plan.seed, k]
            m, meta = store.get_or_build("building", dict(kind=kind, seed=bseed),
                                         lambda: generate_building(kind, seed=tuple(bseed)), *mesh_codec("building"))
            yaw = -np.pi / 2  # front (+x local) faces the road to the south
            fx0, fy0, fx1, fy1 = meta["footprint"]
            by = road_y + 8.0 + (fx1 - 0)  # set back from the road
            corners = np.array([[fx0, fy0], [fx1, fy0], [fx1, fy1], [fx0, fy1]])
            R2 = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
            wc = corners @ R2.T + [bx, by]
            zfoot = float(hf.sample(wc[:, 0], wc[:, 1]).max())
            M = _rotz(yaw, (bx, by, zfoot - 0.05))
            bmeshes.append(m.transformed(M))
            footprints.append((*wc.min(0), *wc.max(0)))
            d = np.array(meta["door"]) @ R2.T + [bx, by]
            doors.append((float(d[0]), float(d[1]), 2.5))
            mb = mailbox(r)
            mx, my = bx + r.uniform(-4, 4), road_y + 3.0
            props.append(mb.transformed(_rotz(0, (mx, my, float(hf.sample(mx, my)[0])))))
            doors.append((mx, my, 0.8))
            info.append(dict(kind=kind, x=float(bx), y=float(by), mailbox=(float(mx), float(my))))
            if k == 0:
                cx, cy = bx + 10, by + 4
                props.append(clothesline(r).transformed(_rotz(np.pi / 2, (cx, cy, float(hf.sample(cx, cy)[0])))))
                doors.append((cx, cy, 0.6))
        fx = np.linspace(2, S - 2, 12)
        fpts = [(x, road_y + 1.6, float(hf.sample(x, road_y + 1.6)[0])) for x in fx]
        props.append(fence(fpts, r))
    log(f"buildings {plan.buildings}")

    # ── trees ──────────────────────────────────────────────────────────
    species = list(plan.trees)
    weights = np.array([plan.trees[k] for k in species])
    moist = hf.layers["moisture"]
    slope = hf.layers["slope"]

    def blocked(p):
        if plan.buildings and p[1] < road_y + 4:
            return True
        for (a, b, c, d) in footprints:
            if a - 4 < p[0] < c + 4 and b - 4 < p[1] < d + 4:
                return True
        return False

    avg_crown = np.mean([SPECIES[k].crown_width * np.mean(SPECIES[k].height) / 2 for k in species])
    n_target = int(plan.tree_density * S * S / (np.pi * avg_crown ** 2) * 1.1) + 1
    placements = []
    cand = r.uniform([2, 2], [S - 2, S - 2], (n_target * 12, 2))
    occ = []
    for p in cand:
        if len(placements) >= n_target or blocked(p):
            continue
        m_ = float(hf.sample(p[0], p[1], "moisture")[0])
        sl = float(hf.sample(p[0], p[1], "slope")[0])
        wt = float(hf.sample(p[0], p[1], "water")[0])
        suit = []
        for k in species:
            sp = SPECIES[k]
            lo, hi = sp.moisture
            sm = np.exp(-((max(lo - m_, 0) + max(m_ - hi, 0)) / 0.12) ** 2)
            ss = 1.0 if sl <= sp.max_slope else 0.1
            sw = 1.0 if wt < 0.5 or sp.knees else 0.0
            sprov = 1.0 if (not sp.provinces or plan.province in sp.provinces) else 0.25
            suit.append(sm * ss * sw * sprov)
        w = weights * np.array(suit)
        if w.sum() < 1e-3:
            continue
        k = species[int(r.choice(len(species), p=w / w.sum()))]
        sp = SPECIES[k]
        crad = sp.crown_width * np.mean(sp.height) / 2
        spacing = crad * (0.55 if plan.tree_density > 0.5 else 0.9)
        if occ:
            o = np.array(occ)
            if np.min(np.hypot(o[:, 0] - p[0], o[:, 1] - p[1]) - o[:, 2]) < spacing * 0.6:
                continue
        occ.append((p[0], p[1], spacing * 0.6))
        placements.append(dict(species=k, x=float(p[0]), y=float(p[1]), moisture=m_,
                               variant=int(r.integers(0, VARIANTS[plan.detail])),
                               yaw=float(r.uniform(0, 2 * np.pi)), scale=float(r.uniform(0.85, 1.12))))
    variants = {}
    tenc, tdec = tree_codec()
    for pl in placements:
        pl["moisture_bucket"] = 0.8 if pl["moisture"] > 0.65 else 0.5  # moss/knee thresholds → max reuse
        key = (pl["species"], pl["variant"], pl["moisture_bucket"])
        pl["model"] = key
        if key not in variants:
            seed = [0, pl["variant"]] if library_pool else [plan.seed, pl["variant"]]
            params = dict(species=pl["species"], seed=seed, season=plan.season, detail=plan.detail,
                          moisture=pl["moisture_bucket"])
            variants[key] = store.get_or_build(
                "tree", params, lambda: generate_tree(params["species"], seed=tuple(seed), season=plan.season,
                                                      detail=plan.detail, moisture=params["moisture"]), tenc, tdec)
    log(f"trees {len(placements)} placed, {len(variants)} unique models ({time.time() - t0:.1f}s)")

    canopy = np.zeros_like(hf.z)
    trees_arr = []
    yy, xx = np.indices(hf.z.shape)
    for pl in placements:
        tm = variants[pl["model"]]
        sp = tm.species
        cr = max(sp.crown_width * tm.height / 2 * pl["scale"], 1.0)
        d = np.hypot(xx * hf.res - pl["x"], yy * hf.res - pl["y"])
        canopy += np.clip(1 - d / cr, 0, 1) ** 0.5 * (0.5 if sp.leaf == "needle" else 0.9)
        trees_arr.append((pl["x"], pl["y"], tm.height * pl["scale"], tm.skeleton.radius[0] * pl["scale"]))
        pl["z"] = float(hf.sample(pl["x"], pl["y"])[0])
    canopy = np.clip(canopy, 0, 1)
    trees_arr = np.array(trees_arr) if trees_arr else np.zeros((0, 4))

    # ── desire paths ───────────────────────────────────────────────────
    cost = obstacle_cost(hf, trunks=[(x, y, rd) for x, y, _, rd in trees_arr], footprints=footprints)
    field = TrailField(np.zeros_like(hf.z), hf.res, hf.origin)
    if plan.buildings:
        field.G[int(road_y / hf.res) - 2:int(road_y / hf.res) + 2, :] = 1.0  # gravel road
    att = list(doors)
    if water.any():
        wy, wx = np.argwhere(water > 0.5)[len(np.argwhere(water > 0.5)) // 2]
        att.append((wx * hf.res, wy * hf.res + 3, 1.0))
    edge = r.uniform(0.15, 0.85, 3) * S
    att += [(edge[0], S - 2, 1.0), (2, edge[1], 0.8), (S - 2, edge[2], 0.8)]
    if plan.buildings:
        att += [(3, road_y, 1.5), (S - 3, road_y, 1.5)]
    if len(trees_arr):  # the big shade tree everybody walks to
        i = int(np.argmax(trees_arr[:, 3]))
        att.append((trees_arr[i, 0] + 3, trees_arr[i, 1], 0.8))
    if plan.paths and len(att) >= 2:
        trips = int(150 + 6 * S)
        field, _ = simulate(hf, att, n_trips=trips, seed=plan.seed, cost=cost, field=field)
    log(f"desire paths: {int((field.G > 0.35).sum())} trodden cells ({time.time() - t0:.1f}s)")

    # ── animals ────────────────────────────────────────────────────────
    is_oak = np.zeros_like(hf.z)
    for pl in placements:
        if "oak" in pl["species"]:
            d = np.hypot(xx * hf.res - pl["x"], yy * hf.res - pl["y"])
            is_oak += np.exp(-(d / 8) ** 2)
    dens = grass_density(hf, field.G, canopy)
    forage = np.clip(0.6 * dens * (0.5 + moist) + 0.3 * canopy * (1 - canopy), 0, 1)
    mast = np.clip(is_oak, 0, 1)
    if plan.season == "fall":
        mast = np.clip(mast * 1.4, 0, 1)  # acorn drop
    world = World(hf, field, cost, np.clip(canopy * 1.2, 0, 1), forage, mast, trees_arr, hour=plan.hour)
    world.attractors = [(a[0], a[1]) for a in att]
    agents = spawn(world, plan.fauna, seed=plan.seed) if plan.fauna else []
    run(world, agents, seconds=sim_seconds, dt=0.25, start_hour=plan.hour)
    scene_key = AssetStore.key("terrain", dict(prompt=plan.prompt, seed=plan.seed))[:12]
    for a in agents:
        store_behavior(store, a, scene_key)
    log(f"fauna: {len(agents)} agents, {sum(len(a.events) for a in agents)} decisions/events, "
        f"{len(world.signs)} signs ({time.time() - t0:.1f}s)")

    # ── ground ─────────────────────────────────────────────────────────
    dens = grass_density(hf, field.G, canopy)
    mix = BIOME_GRASS.get(plan.biome, BIOME_GRASS["pasture"])
    ter = terrain_mesh(hf, dens, field.G, canopy, world.signs, plan.season,
                       litter=0.6 if plan.biome in ("pine_savanna", "pine_plantation") else 0.2)
    c = S / 2
    focus = (c - 28, c - 28, c + 28, c + 28)
    grass = grass_mesh(hf, dens, focus, GRASS_BUDGET[plan.detail], mix, plan.seed, plan.season)
    wmb = MeshBuilder()
    wy, wx = np.nonzero(water > 0.5)
    for i, j in zip(wy, wx):
        z = hf.z[max(i - 1, 0):i + 2, max(j - 1, 0):j + 2].max() + 0.05
        x, y = j * hf.res, i * hf.res
        h = hf.res / 2
        wmb.add([[x - h, y - h, z], [x + h, y - h, z], [x + h, y + h, z], [x - h, y + h, z]],
                [0.18, 0.26, 0.24], [[0, 1, 2], [0, 2, 3]])
    water_mesh = wmb.build()
    seedlings = MeshBuilder()
    for s_ in world.signs:
        if s_["type"] == "oak_seedling":
            z = float(hf.sample(s_["x"], s_["y"])[0])
            seedlings.add([[s_["x"] - 0.04, s_["y"], z], [s_["x"] + 0.04, s_["y"], z], [s_["x"], s_["y"], z + 0.18]],
                          [0.3, 0.5, 0.2], [[0, 1, 2]])
    props.append(seedlings.build())

    # ── export ─────────────────────────────────────────────────────────
    light = sun_and_sky(plan.hour)
    g = GLB()
    m_ter, m_bark = g.material("terrain", rough=1.0), g.material("bark", rough=0.95)
    m_fol, m_grass = g.material("foliage", double=True, rough=0.7), g.material("grass", double=True, rough=0.8)
    m_bld, m_water = g.material("building", rough=0.6), g.material("water", rough=0.08, alpha=0.85)
    m_fauna = g.material("fauna", rough=0.8)
    g.node("terrain", g.mesh(ter, "terrain", m_ter))
    if grass.n_tris:
        g.node("grass", g.mesh(grass, "grass", m_grass))
    if water_mesh.n_tris:
        g.node("water", g.mesh(water_mesh, "water", m_water))
    built = Mesh.merge(bmeshes + props)
    if built.n_tris:
        g.node("buildings_props", g.mesh(built, "buildings_props", m_bld))
    vmesh = {}
    for key, tm in variants.items():
        nm = f"{key[0]}_{key[1]}_{int(key[2] * 10)}"
        vmesh[key] = (g.mesh(tm.bark, nm + "_bark", m_bark), g.mesh(tm.foliage, nm + "_foliage", m_fol))
    kids = []
    for n, pl in enumerate(placements):
        b, f = vmesh[pl["model"]]
        sub = [g.node(f"bark", b)] + ([g.node("foliage", f)] if f is not None else [])
        kids.append(g.node(f"{pl['species']}_{n}", translation=(pl["x"], pl["y"], pl["z"]),
                           rotation_z=pl["yaw"], scale=pl["scale"], children=sub))
    g.node("trees", children=kids)
    tracks = []
    akids = []
    for a in agents:
        rr = make_rng("look", a.id)
        # a few quantised looks per species so bodies come from the library instead of being rebuilt
        rgb = np.clip(np.array(a.spec.rgb) * [0.88, 1.0, 1.12][int(rr.integers(0, 3))], 0, 1)
        sc = [0.9, 1.0, 1.1][int(rr.integers(0, 3))]
        bm, _ = store.get_or_build("body", dict(species=a.spec.key, scale=sc, rgb=[round(float(c), 2) for c in rgb]),
                                   lambda: (body(a.spec.key, rgb, scale=sc), {}), *mesh_codec("body"))
        node = g.node(f"{a.spec.key}_{a.id}", g.mesh(bm, f"{a.spec.key}_{a.id}", m_fauna))
        akids.append(node)
        L = a.log[::4]
        if len(L) > 1:
            tracks.append((node, [l[0] for l in L], [(l[1], l[2], l[3]) for l in L], [l[4] for l in L]))
    if akids:
        g.node("fauna", children=akids)
    g.animate("life", tracks)
    glb = os.path.join(out_dir, "scene.glb")
    g.save(glb, extras=dict(prompt=plan.prompt, seed=plan.seed))
    size_mb = os.path.getsize(glb) / 1e6

    stats = dict(trees=len(placements), unique_tree_models=len(variants),
                 tree_tris=int(sum(tm.n_tris for tm in variants.values())), grass_blades=grass.n_tris,
                 terrain_tris=ter.n_tris, agents=len(agents), signs=len(world.signs),
                 trodden_cells=int((field.G > 0.35).sum()), glb_mb=round(size_mb, 2),
                 seconds=round(time.time() - t0, 1), library=store.stats())
    scene = dict(plan=asdict(plan), stats=stats, lighting=light, buildings=info,
                 trees=[{k: v for k, v in pl.items() if k != "model"} for pl in placements], signs=world.signs,
                 agents=[dict(id=a.id, species=a.spec.key, traits={k: round(v, 2) for k, v in a.trait.items()},
                              events=a.events[:80]) for a in agents])
    with open(os.path.join(out_dir, "scene.json"), "w") as f:
        json.dump(scene, f, indent=1, default=float)
    np.savez_compressed(os.path.join(out_dir, "layers.npz"), z=hf.z, trail=field.G, canopy=canopy,
                        grass=dens, moisture=moist, water=water)
    log(f"exported {glb} ({size_mb:.1f} MB) in {time.time() - t0:.1f}s")
    return dict(dir=out_dir, glb=glb, stats=stats, hf=hf, field=field, canopy=canopy, agents=agents,
                world=world, placements=placements, variants=variants, ter=ter, grass=grass,
                built=built, water=water_mesh, light=light)

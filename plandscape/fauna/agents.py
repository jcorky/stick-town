"""Animals that plan, notice, remember and change their minds.

Each animal has
  • needs (hunger, thirst, fatigue, fear) that drift over time,
  • a personality sampled from its seed (boldness, curiosity, wanderlust, ...),
  • a memory of where it found food/water/cover (with forgetting),
  • a utility-based decision layer that picks a goal,
  • an A* route over a cost map that prefers cover and existing trails,
  • an execution layer that follows the route with Ornstein-Uhlenbeck heading
    noise and stochastic interrupts (startle, opportunistic snack, pause to look,
    flock cohesion, pursuit) that make it deviate and replan.

Plans are concrete, deviations are continuous and seeded, so every run is
reproducible and the space of behaviours is unbounded. Animals also *change
the world*: trails deepen, deer leave beds and rubs, squirrels cache acorns
(some forgotten → oak seedlings), armadillos dig, turkeys scratch.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from ..rng import rng as make_rng


@dataclass(frozen=True)
class FaunaSpec:
    key: str
    common: str
    walk: float                 # m/s
    run: float
    perceive: float             # metres
    fears: tuple                # keys of agents it flees
    eats: str                   # world layer: forage|mast|prey|shore (the creek's edge, §32)
    active: tuple               # hours (start, end) of peak activity; may wrap midnight
    crepuscular: bool = False
    group: tuple = (1, 1)
    shy: float = 0.5            # preference for cover
    trail_use: float = 0.5      # attraction to trails
    climbs: bool = False
    hunts: tuple = ()
    size: float = 1.0
    rgb: tuple = (0.5, 0.4, 0.3)
    withdraws: bool = False     # meets a threat by shutting in (box turtle) instead of fleeing


FAUNA: dict[str, FaunaSpec] = {f.key: f for f in [
    FaunaSpec("white_tailed_deer", "White-tailed deer", 1.3, 9.0, 45, ("human", "coyote", "dog"),
              "forage", (5, 9), crepuscular=True, group=(1, 4), shy=0.8, trail_use=0.9, size=1.0,
              rgb=(0.55, 0.40, 0.26)),
    FaunaSpec("gray_squirrel", "Eastern gray squirrel", 1.2, 5.0, 18, ("human", "coyote", "dog", "red_tailed_hawk"),
              "mast", (7, 18), group=(1, 1), shy=0.3, trail_use=0.1, climbs=True, size=0.25,
              rgb=(0.52, 0.50, 0.48)),
    FaunaSpec("wild_turkey", "Wild turkey", 0.9, 5.0, 40, ("human", "coyote", "dog"),
              "mast", (6, 17), group=(3, 9), shy=0.6, trail_use=0.4, size=0.55, rgb=(0.22, 0.18, 0.14)),
    FaunaSpec("armadillo", "Nine-banded armadillo", 0.5, 2.0, 8, ("dog", "coyote"),
              "forage", (19, 5), group=(1, 1), shy=0.4, trail_use=0.3, size=0.35, rgb=(0.62, 0.56, 0.50)),
    FaunaSpec("coyote", "Coyote", 1.4, 11.0, 60, ("human",), "prey", (18, 6), group=(1, 2), shy=0.7,
              trail_use=0.9, hunts=("gray_squirrel", "armadillo", "wild_turkey"), size=0.6,
              rgb=(0.58, 0.50, 0.40)),
    FaunaSpec("human", "Person walking", 1.3, 3.0, 30, (), "none", (7, 20), group=(1, 2), shy=0.0,
              trail_use=1.0, size=0.9, rgb=(0.25, 0.35, 0.55)),
    # sizes, top speeds, activity and grouping sourced in catalog/fauna_sources.json (§32); walks marked design there
    FaunaSpec("raccoon", "Raccoon", 0.5, 6.7, 25, ("human", "coyote", "dog"), "shore", (19, 5), group=(1, 1),
              shy=0.6, trail_use=0.5, climbs=True, size=0.3, rgb=(0.45, 0.43, 0.40)),
    FaunaSpec("box_turtle", "Eastern box turtle", 0.05, 0.49, 5, ("human", "dog", "coyote", "raccoon"), "forage",
              (6, 11), group=(1, 1), shy=0.5, trail_use=0.1, size=0.15, rgb=(0.35, 0.25, 0.12), withdraws=True),
    FaunaSpec("great_blue_heron", "Great blue heron", 0.15, 3.0, 50, ("human", "dog", "coyote"), "shore", (5, 9),
              crepuscular=True, group=(1, 1), shy=0.7, trail_use=0.0, size=0.6, rgb=(0.45, 0.52, 0.60)),
]}


def activity(spec: FaunaSpec, hour: float) -> float:
    a, b = spec.active
    inside = (a <= hour < b) if a < b else (hour >= a or hour < b)
    base = 1.0 if inside else 0.2
    if spec.crepuscular:
        base = max(base, np.exp(-((hour - 6.5) / 1.5) ** 2), np.exp(-((hour - 19.0) / 1.5) ** 2))
    return float(base)


@dataclass
class World:
    hf: object
    trail: object
    cost: np.ndarray          # 0..1 obstacle
    cover: np.ndarray         # 0..1 canopy/understory
    forage: np.ndarray        # 0..1 browse / grass / insects
    mast: np.ndarray          # 0..1 acorns etc. under oaks
    trees: np.ndarray         # (N,4) x, y, height, trunk radius
    hour: float = 7.0
    signs: list = field(default_factory=list)

    def grid(self, x, y):
        gx, gy = self.hf.to_grid(x, y)
        return gx, gy

    def sample(self, arr, x, y):
        gx, gy = self.grid(x, y)
        return ndimage.map_coordinates(arr, [np.atleast_1d(gy), np.atleast_1d(gx)], order=1, mode="nearest")

    def z(self, x, y):
        return float(self.hf.sample(x, y)[0])

    @property
    def shore(self):
        """0..1 band along the water's edge, 1.5 m in and 3 m out: where herons wade and raccoons feel for food."""
        if getattr(self, "_shore", None) is None:
            w = self.hf.layers["water"] > 0.5
            if not w.any():
                self._shore = np.zeros_like(self.cost)
            else:
                band = ndimage.binary_dilation(w, iterations=3) & ~ndimage.binary_erosion(w, iterations=2)
                self._shore = np.clip(ndimage.gaussian_filter(band.astype(float), 1.0) * 1.6, 0, 1)
        return self._shore

    def food(self, eats):
        return {"forage": self.forage, "mast": self.mast, "shore": self.shore}.get(eats)

    @property
    def bounds(self):
        w, h = self.hf.size
        return (self.hf.origin[0], self.hf.origin[1], self.hf.origin[0] + w, self.hf.origin[1] + h)


def astar(cost_grid: np.ndarray, start, goal, max_expand=40000):
    ny, nx = cost_grid.shape
    sy, sx = start
    gy, gx = goal
    if not (0 <= gy < ny and 0 <= gx < nx):
        return [goal]
    openh = [(0.0, 0.0, start)]
    came = {start: None}
    gcost = {start: 0.0}
    nb = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1), (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
    n = 0
    while openh and n < max_expand:
        _, g, cur = heapq.heappop(openh)
        n += 1
        if cur == goal:
            break
        cy, cx = cur
        for dy, dx, d in nb:
            y, x = cy + dy, cx + dx
            if not (0 <= y < ny and 0 <= x < nx):
                continue
            c = cost_grid[y, x]
            if c >= 50:
                continue
            ng = g + d * c
            if ng < gcost.get((y, x), 1e18):
                gcost[(y, x)] = ng
                came[(y, x)] = cur
                h = np.hypot(gy - y, gx - x)
                heapq.heappush(openh, (ng + h, ng, (y, x)))
    if goal not in came:  # unreachable: go to closest explored
        goal = min(came, key=lambda k: np.hypot(k[0] - gy, k[1] - gx))
    path = []
    k = goal
    while k is not None:
        path.append(k)
        k = came[k]
    return path[::-1]


class Agent:
    def __init__(self, spec: FaunaSpec, pos, seed, world: World, group_id=None, agent_id=0):
        self.spec = spec
        # the id is the agent's index in its scene, never a process-wide counter: a counter made a scene's
        # animals depend on how many agents earlier scenes in the same process had created
        self.id = agent_id
        self.r = make_rng("agent", spec.key, seed, self.id)
        self.p = np.array(pos, float)
        self.heading = self.r.uniform(0, 2 * np.pi)
        self.omega = 0.0
        self.z = world.z(*self.p)
        self.climb = 0.0
        self.group_id = group_id
        # personality: every individual is different
        self.trait = dict(boldness=self.r.beta(2, 2), curiosity=self.r.beta(2, 3),
                          wanderlust=self.r.beta(2, 4), patience=self.r.beta(3, 2),
                          laziness=self.r.beta(2, 3))
        self.needs = dict(hunger=self.r.uniform(0.2, 0.8), thirst=self.r.uniform(0.1, 0.6),
                          fatigue=self.r.uniform(0.0, 0.5), fear=0.0)
        self.memory: list[tuple] = []   # (kind, x, y, value, t)
        self.state = "idle"
        self.timer = 0.0
        self.route: list = []
        self.goal = None
        self.goal_kind = None
        self.carry = None
        self.target_agent = None
        self.log: list = []
        self.events: list = []
        self.cooldown = 0.0          # seconds before it will react to threats again
        self.habituation: dict = {}  # threat key -> times seen without harm

    # ── perception & memory ────────────────────────────────────────────
    def remember(self, kind, x, y, value, t):
        self.memory.append((kind, float(x), float(y), float(value), t))
        if len(self.memory) > 60:
            self.memory.pop(0)

    def recall(self, kind, t):
        best, bv = None, 0.0
        for k, x, y, v, tm in self.memory:
            if k != kind:
                continue
            fresh = np.exp(-(t - tm) / 900.0)
            d = np.hypot(x - self.p[0], y - self.p[1])
            score = v * fresh / (1 + d / 40)
            if score > bv:
                best, bv = (x, y), score
        return best, bv

    def scan(self, world: World, layer, kind, t, n=10):
        a = self.r.uniform(0, 2 * np.pi, n)
        d = self.r.uniform(3, self.spec.perceive, n)
        xs = np.clip(self.p[0] + np.cos(a) * d, world.bounds[0] + 1, world.bounds[2] - 1)
        ys = np.clip(self.p[1] + np.sin(a) * d, world.bounds[1] + 1, world.bounds[3] - 1)
        v = world.sample(layer, xs, ys)
        i = int(np.argmax(v))
        if v[i] > 0.15:
            self.remember(kind, xs[i], ys[i], v[i], t)
        return (xs[i], ys[i]), float(v[i])

    # ── deciding ───────────────────────────────────────────────────────
    def decide(self, world: World, agents, t):
        s, nd, tr = self.spec, self.needs, self.trait
        act = activity(s, world.hour)
        opts = []
        if s.eats in ("forage", "mast", "shore"):
            layer = world.food(s.eats)
            loc, v = self.recall("food", t)
            if loc is None or self.r.uniform() < tr["curiosity"] * 0.5:
                loc, v = self.scan(world, layer, "food", t)
            opts.append(("eat", nd["hunger"] * (0.4 + v) * act, loc))
        if s.eats == "prey":
            prey = [a for a in agents if a.spec.key in s.hunts and a.climb < 0.5 and
                    np.hypot(*(a.p - self.p)) < s.perceive]
            if prey:
                tgt = min(prey, key=lambda a: np.hypot(*(a.p - self.p)))
                opts.append(("hunt", nd["hunger"] * 1.5 * act, tuple(tgt.p), tgt))
        water = world.hf.layers["water"]
        if water.any() and s.key != "human":
            loc, v = self.recall("water", t)
            if loc is None:
                loc, v = self.scan(world, water, "water", t, n=16)
            opts.append(("drink", nd["thirst"] * (0.3 + v), loc))
        loc, v = self.recall("cover", t)
        if loc is None:
            loc, v = self.scan(world, world.cover, "cover", t)
        opts.append(("rest", nd["fatigue"] * (1.2 - act) * (0.5 + tr["laziness"]) * (0.4 + v * s.shy), loc))
        if s.climbs and len(world.trees):
            d = np.hypot(world.trees[:, 0] - self.p[0], world.trees[:, 1] - self.p[1])
            i = int(np.argmin(d + self.r.uniform(0, 8, len(d))))
            opts.append(("climb", 0.25 + 0.4 * nd["fear"] + 0.2 * tr["curiosity"], tuple(world.trees[i, :2]), i))
            if self.carry == "acorn":
                a = self.r.uniform(0, 2 * np.pi)
                dd = self.r.uniform(6, 25)
                opts.append(("cache", 0.9, (self.p[0] + np.cos(a) * dd, self.p[1] + np.sin(a) * dd)))
            loc, v = self.recall("cache", t)
            if loc is not None:
                opts.append(("retrieve", nd["hunger"] * 0.7 * v, loc))
        if s.key == "human":
            pts = getattr(world, "attractors", [])
            if pts:
                q = pts[int(self.r.integers(0, len(pts)))]
                opts.append(("walk", 0.6 + tr["wanderlust"], (q[0], q[1])))
        a = self.r.uniform(0, 2 * np.pi)
        dd = self.r.uniform(10, 50) * (0.5 + tr["wanderlust"])
        opts.append(("explore", 0.15 + 0.5 * tr["curiosity"] * act,
                     (self.p[0] + np.cos(a) * dd, self.p[1] + np.sin(a) * dd)))
        # softmax with personality temperature → same needs, different choices
        u = np.array([o[1] for o in opts])
        temp = 0.08 + 0.25 * tr["curiosity"]
        pr = np.exp((u - u.max()) / temp)
        pr /= pr.sum()
        choice = opts[int(self.r.choice(len(opts), p=pr))]
        self.set_goal(world, choice, t)

    def set_goal(self, world, choice, t):
        kind, _, loc = choice[:3]
        b = world.bounds
        loc = (float(np.clip(loc[0], b[0] + 1, b[2] - 1)), float(np.clip(loc[1], b[1] + 1, b[3] - 1)))
        self.goal, self.goal_kind = np.array(loc), kind
        self.target_agent = choice[3] if kind == "hunt" else None
        self.tree_idx = choice[3] if kind == "climb" else None
        self.plan(world)
        self.state = "travel"
        self.events.append((round(t, 1), f"plan:{kind}"))

    def plan(self, world):
        cell = 2.0
        step = max(1, int(cell / world.hf.res))
        c = world.cost[::step, ::step]
        cov = world.cover[::step, ::step]
        tr = world.trail.G[::step, ::step]
        s = self.spec
        grid = 1.0 + 30 * c ** 2 + 2.5 * s.shy * (1 - cov) - 0.7 * s.trail_use * tr
        grid = np.maximum(grid, 0.2)
        grid[c > 0.95] = 99
        gx, gy = world.grid(*self.p)
        tx, ty = world.grid(*self.goal)
        start = (int(np.clip(gy / step, 0, grid.shape[0] - 1)), int(np.clip(gx / step, 0, grid.shape[1] - 1)))
        goal = (int(np.clip(ty / step, 0, grid.shape[0] - 1)), int(np.clip(tx / step, 0, grid.shape[1] - 1)))
        path = astar(grid, start, goal)
        o = world.hf.origin
        self.route = [np.array([o[0] + j * step * world.hf.res, o[1] + i * step * world.hf.res]) for i, j in path[1:]]
        if self.route:
            self.route[-1] = self.goal.copy()

    # ── acting ─────────────────────────────────────────────────────────
    def threats(self, agents):
        out = []
        for a in agents:
            if a is self or a.spec.key not in self.spec.fears:
                continue
            d = np.hypot(*(a.p - self.p))
            if d < self.spec.perceive * (1.2 - 0.5 * self.trait["boldness"]):
                out.append((d, a))
        return out

    def step(self, world: World, agents, t, dt):
        s, nd, tr, r = self.spec, self.needs, self.trait, self.r
        act = activity(s, world.hour)
        nd["hunger"] = min(1, nd["hunger"] + dt * 0.0006 * act)
        nd["thirst"] = min(1, nd["thirst"] + dt * 0.0005)
        nd["fatigue"] = min(1, nd["fatigue"] + dt * 0.0004 * (2 if self.state == "flee" else 1))
        nd["fear"] = max(0, nd["fear"] - dt * 0.02 * (0.5 + tr["boldness"]))
        speed = s.walk * (0.6 + 0.6 * act)

        # interrupts ------------------------------------------------------
        self.cooldown = max(0.0, self.cooldown - dt)
        th = self.threats(agents)
        if th and self.state != "flee":
            d, a = min(th, key=lambda q: q[0])
            hab = self.habituation.get(a.spec.key, 0)
            # flight initiation distance shrinks with boldness and habituation
            fid = s.perceive * 0.45 * (1.3 - tr["boldness"]) / (1 + 0.35 * hab)
            closing = np.dot(a.p - self.p, np.array([np.cos(a.heading), np.sin(a.heading)])) < 0
            if d < fid and (closing or d < fid * 0.5) and self.cooldown <= 0:
                nd["fear"] = min(1, nd["fear"] + 0.6)
                if s.withdraws:  # a box turtle shuts its shell and waits it out
                    self.state, self.timer = "freeze", r.uniform(30, 120)
                    self.events.append((round(t, 1), f"withdraw:{a.spec.key}"))
                elif s.climbs and len(world.trees) and self.climb <= 0:
                    i = int(np.argmin(np.hypot(world.trees[:, 0] - self.p[0], world.trees[:, 1] - self.p[1])))
                    self.set_goal(world, ("climb", 1, tuple(world.trees[i, :2]), i), t)
                    self.events.append((round(t, 1), f"escape_up:{a.spec.key}"))
                    self.state = "flee_route"
                elif self.climb > 0.5:
                    self.state, self.timer = "freeze", r.uniform(5, 15)
                else:
                    self.state, self.timer = "flee", r.uniform(3, 7)
                    away = self.p - a.p
                    cov_dir = self._toward_cover(world)
                    v = away / max(np.hypot(*away), 1e-6) + 0.6 * cov_dir
                    self.heading = np.arctan2(v[1], v[0]) + r.normal(0, 0.4)
                    self.events.append((round(t, 1), f"flee:{a.spec.key}"))
                self.cooldown = r.uniform(12, 30)
                self.habituation[a.spec.key] = hab + 1
            elif self.state not in ("alert", "freeze") and self.cooldown <= 0 and d < s.perceive * 0.8:
                self.state, self.timer = "alert", r.uniform(2, 6) * (1.5 - tr["boldness"])
                self.cooldown = r.uniform(8, 20)
                self.events.append((round(t, 1), f"alert:{a.spec.key}"))
        if self.state == "flee_route":
            self.state = "travel"
            speed = s.run
        if self.state in ("alert", "freeze", "pause", "eat", "drink", "rest", "groom", "dig", "scratch"):
            self.timer -= dt
            if self.state == "eat":
                nd["hunger"] = max(0, nd["hunger"] - dt * 0.02)
            if self.state == "drink":
                nd["thirst"] = max(0, nd["thirst"] - dt * 0.05)
            if self.state == "rest":
                nd["fatigue"] = max(0, nd["fatigue"] - dt * 0.01)
            self.heading += r.normal(0, 0.2) * dt  # look around
            if self.timer <= 0:
                if self.state == "rest" and s.key == "white_tailed_deer":
                    world.signs.append(dict(type="deer_bed", x=self.p[0], y=self.p[1], size=1.2))
                self.state = "idle"
            self._log(t, world)
            return
        if self.state == "flee":
            self.timer -= dt
            speed = s.run
            self.omega += r.normal(0, 0.8) * dt
            self.heading += self.omega * dt
            self._move(world, speed, dt)
            if self.timer <= 0:
                self.state = "idle"  # calm down, then replan from wherever it ended up
            self._log(t, world)
            return
        if self.state == "idle" or not self.route:
            if self.state == "travel" and not self.route:
                self.arrive(world, t)
            else:
                self.decide(world, agents, t)
            self._log(t, world)
            return

        # travel along plan, with deviations -------------------------------
        if self.goal_kind == "hunt" and self.target_agent is not None:
            self.route = [self.target_agent.p.copy()]
            speed = s.run * 0.8 if np.hypot(*(self.target_agent.p - self.p)) < 15 else speed
        tgt = self.route[0]
        to = tgt - self.p
        if np.hypot(*to) < 1.2:
            self.route.pop(0)
            self._log(t, world)
            return
        desired = np.arctan2(to[1], to[0])
        # Ornstein-Uhlenbeck turn noise: smooth, never-repeating wobble
        self.omega += (-0.8 * self.omega + r.normal(0, 0.9 * (0.4 + tr["wanderlust"]))) * dt
        err = (desired - self.heading + np.pi) % (2 * np.pi) - np.pi
        self.heading += (2.0 * err + self.omega) * dt
        # opportunism: food underfoot beats the plan if hungry
        if s.eats in ("forage", "mast", "shore") and r.uniform() < 0.02 * dt * 10:
            here = world.sample(world.food(s.eats), *self.p)[0]
            if here > 0.5 and nd["hunger"] > 0.35:
                self.state, self.timer = "eat", r.uniform(3, 15) * tr["patience"]
                self.remember("food", *self.p, here, t)
                self.events.append((round(t, 1), "snack"))
        # occasional pause to look/listen
        if r.uniform() < 0.004 * dt * 10 * (1.5 - tr["boldness"]):
            self.state, self.timer = "pause", r.uniform(1, 5)
        # flock cohesion
        if self.group_id is not None:
            mates = [a for a in agents if a.group_id == self.group_id and a is not self]
            if mates:
                c = np.mean([a.p for a in mates], 0) - self.p
                if np.hypot(*c) > 6:
                    self.heading += 0.3 * ((np.arctan2(c[1], c[0]) - self.heading + np.pi) % (2 * np.pi) - np.pi) * dt
        self._move(world, speed, dt)
        if self.goal_kind == "hunt" and self.target_agent is not None:
            if np.hypot(*(self.target_agent.p - self.p)) < 1.0 and self.target_agent.climb < 0.5:
                self.events.append((round(t, 1), f"catch_attempt:{self.target_agent.spec.key}"))
                self.target_agent.state, self.target_agent.timer = "flee", 6
                self.needs["hunger"] *= 0.7
                self.route = []
        self._log(t, world)

    def arrive(self, world, t):
        k, s, r = self.goal_kind, self.spec, self.r
        self.events.append((round(t, 1), f"arrive:{k}"))
        if k == "eat":
            self.state, self.timer = "eat", r.uniform(8, 40) * (0.5 + self.trait["patience"])
            if s.key == "armadillo":
                world.signs.append(dict(type="armadillo_dig", x=self.p[0], y=self.p[1], size=0.25))
            if s.key == "wild_turkey":
                world.signs.append(dict(type="turkey_scratch", x=self.p[0], y=self.p[1], size=0.5))
            if s.climbs and world.sample(world.mast, *self.p)[0] > 0.3:
                self.carry = "acorn"
        elif k == "drink":
            self.state, self.timer = "drink", r.uniform(5, 20)
        elif k == "rest":
            self.state, self.timer = "rest", r.uniform(20, 120)
        elif k == "climb" and self.tree_idx is not None:
            tx, ty, th, trad = world.trees[self.tree_idx]
            self.climb = r.uniform(0.3, 0.8) * th
            if self.needs["fear"] > 0.35:  # bolted up the trunk: flatten against the bark and wait
                self.state, self.timer = "freeze", r.uniform(4, 12)
            else:  # a routine climb: feed, groom or loaf in the canopy
                opt = ["eat", "groom", "rest"]
                w = np.array([0.5 + 0.8 * self.needs["hunger"], 0.25, 0.25 + 0.6 * self.needs["fatigue"]])
                k2 = opt[int(r.choice(3, p=w / w.sum()))]
                self.state = k2
                self.timer = {"eat": r.uniform(6, 25), "groom": r.uniform(3, 10), "rest": r.uniform(10, 40)}[k2]
                self.events.append((round(t, 1), f"canopy:{k2}"))
            self.p = np.array([tx + trad + 0.05, ty])
        elif k == "cache":
            self.carry = None
            self.remember("cache", *self.p, 0.9, t)
            world.signs.append(dict(type="acorn_cache", x=self.p[0], y=self.p[1], size=0.1,
                                    forgotten=bool(r.uniform() < 0.25)))
            self.state, self.timer = "dig", r.uniform(2, 5)
        elif k == "retrieve":
            self.memory = [m for m in self.memory if not (m[0] == "cache" and np.hypot(m[1] - self.p[0], m[2] - self.p[1]) < 2)]
            self.needs["hunger"] = max(0, self.needs["hunger"] - 0.3)
            self.state, self.timer = "eat", r.uniform(3, 8)
        else:
            self.state, self.timer = "pause", r.uniform(1, 6)
        if self.climb > 0 and k != "climb":
            self.climb = 0.0

    def _toward_cover(self, world):
        a = np.linspace(0, 2 * np.pi, 8, endpoint=False)
        xs, ys = self.p[0] + np.cos(a) * 12, self.p[1] + np.sin(a) * 12
        i = int(np.argmax(world.sample(world.cover, xs, ys)))
        return np.array([np.cos(a[i]), np.sin(a[i])])

    def _move(self, world, speed, dt):
        if self.climb > 0:  # climbing down before going anywhere
            self.climb = max(0.0, self.climb - 2.0 * dt)
            return
        d = np.array([np.cos(self.heading), np.sin(self.heading)])
        nxt = self.p + d * speed * dt
        b = world.bounds
        if not (b[0] < nxt[0] < b[2] and b[1] < nxt[1] < b[3]) or world.sample(world.cost, *nxt)[0] > 0.9:
            self.heading += np.pi * 0.5 * (1 if self.r.uniform() < 0.5 else -1)
            return
        self.p = nxt
        if self.spec.trail_use > 0.3 and self.spec.size > 0.5:
            world.trail.deposit(self.p[0:1], self.p[1:2], 0.002 * self.spec.size)

    def _log(self, t, world):
        z = world.z(*self.p) + self.climb
        self.log.append((t, float(self.p[0]), float(self.p[1]), z, float(self.heading), self.state))


def spawn(world: World, counts: dict, seed=0):
    r = make_rng("spawn", seed)
    agents = []
    b = world.bounds
    for key, n in counts.items():
        spec = FAUNA[key]
        placed = 0
        g = 0
        while placed < n:
            gs = int(r.integers(spec.group[0], spec.group[1] + 1))
            gid = f"{key}-{g}" if spec.group[1] > 1 else None
            c = r.uniform([b[0] + 5, b[1] + 5], [b[2] - 5, b[3] - 5])
            if spec.eats == "shore" and world.shore.max() > 0.5:  # start on the creek's edge
                ii, jj = np.nonzero(world.shore > 0.5)
                k = int(r.integers(0, len(ii)))
                c = np.array([world.hf.origin[0] + jj[k] * world.hf.res, world.hf.origin[1] + ii[k] * world.hf.res])
            for _ in range(min(gs, n - placed)):
                agents.append(Agent(spec, c + r.normal(0, 3, 2), (seed, placed), world, gid, agent_id=len(agents)))
                placed += 1
            g += 1
    return agents


def run(world: World, agents, seconds=180.0, dt=0.25, start_hour=7.0, seed=0):
    """Advance everyone. The acting order is reshuffled every step from a keyed stream (after Mesa's
    AgentSet.shuffle_do), so no species always acts first — a coyote no longer always moves before the deer."""
    t = 0.0
    k = 0
    while t < seconds:
        world.hour = (start_hour + t / 3600.0) % 24
        for i in make_rng("act_order", seed, k).permutation(len(agents)):
            agents[i].step(world, agents, t, dt)
        t += dt
        k += 1
    # forgotten caches become oak seedlings: animals planting the future forest
    for s in world.signs:
        if s["type"] == "acorn_cache" and s.get("forgotten"):
            world.signs.append(dict(type="oak_seedling", x=s["x"], y=s["y"], size=0.15))
    return agents

# Fantasy-Map-Generator (Azgaar, MIT, 403a670)

- **Roads** (`src/generators/routes-generator.ts`): burgs linked by an Urquhart graph (Delaunay minus each triangle's
  longest edge, `:256-298`), each edge Dijkstra-routed (`utils/pathUtils.ts:337-372`). Step cost (`:300-314`):
  `d² · (1 + max(100−hab,0)/1000) · (1 + max(h−25,25)/25) · (0.5 if reusing a route) · (3 if next cell not a burg)`.
  Order: sea → main roads → trails, so later routes bundle onto trunks. Sharp-angle relax: angle < 135° → move ½ to
  neighbour midpoint, < 115° → ⅔ (`:634-668`); drawn as Catmull-Rom α = 0.1. No road surface (SVG stroke only).
- **Rivers** (`river-generator.ts`): width `wf·(i/200 + Fib[i]/200) + min(flux^0.7/500, 1) + srcW`; form at flux ≥ 30;
  downcut `h −= min(floor(fl/mean upslope), 5)`; meander points `m = 0.5 + 1/step + max(0.5 − step/100, 0)`.
- **Siting** (`population-generator.ts:32-49`): `hab + norm(flux + confluence)·250 − (h−50)/5` + coast bonuses;
  greedy placement by score × noise with quadtree min-spacing.
- **Names** (`names-generator.ts`): Markov chain over pseudo-syllables. For the South, patterns matter more:
  "Mill Branch", "Pleasant Hill Church Rd", "<surname> Cove Rd".

**Adopted (session 2):** `plandscape/scene/roads.py` — Dijkstra (scipy csgraph) on the 1 m grid with step cost
`d·(1 + (s/12)²)·(1 + 8W)·(0.5 on existing paths)`, FMG's angle relax (< 135° → ½, < 115° → ⅔), then Chaikin
instead of Catmull-Rom, cut-and-fill crown 8 cm, ditch 35 cm, 4 m blend, gravel ribbon 4.5 m wide. Bed sits
12 cm under the ribbon (3 cm let the 1 m terrain poke through).
**Was queued:** a real road surface — Dijkstra on our grid with cost `d·(1 + slope term)·(0.5 on desire paths)`,
angle relax, Catmull-Rom, crowned cut-and-fill profile with ditches, gravel ribbon mesh; FMG-style house siting;
creek width ∝ flux^0.7; Southern name patterns.

# Architecture

## Layers and their order

```
prompt ─▶ planner ─▶ ScenePlan (JSON, saved with every output)
                         │
terrain tile ─▶ buildings + road + props ─▶ trees (habitat-suited) ─▶ canopy
      │                                                                 │
      └──────── obstacle cost (slope, water, trunks, footprints) ◀─────┘
                         │
                desire paths (TrailField)  ◀───────┐
                         │                         │ animals reinforce trails
                 fauna simulation ─────────────────┘  and leave signs
                         │
        ground colour, grass blades, water, seedlings
                         │
          GLB (+ animations) · scene.json · map.png · preview.png
```

Every arrow is data, not a side effect, so any layer can be swapped (e.g. real 3DEP terrain instead of procedural).

## Seeding

`rng(*keys)` hashes a tuple of *what the randomness is for* (`"tree", species, seed`). No layer consumes a shared stream, so adding a layer or reordering work never changes what already existed. Same prompt + seed → identical output; any new key → a new, distinct variant. That is the meaning of "infinite combinations" here: unbounded, addressable and reproducible.

## Detail and the 1 cm target

A 1 cm grid over the American South would be on the order of 10^16 cells; nothing stores that. The plan is a resolution pyramid:

| Range from camera | Source | Representation |
|---|---|---|
| > 1 km | NLCD 30 m, 3DEP coarse | terrain mesh + canopy impostors |
| 50 m – 1 km | 3DEP ~1 m, NAIP | terrain tiles, tree impostors, grass as colour |
| 5 – 50 m | procedural on top of 1 m | full trees (`detail=low/med`), grass blades |
| < 5 m | procedural | `detail="cm"`: true-size leaves, blade-level grass, bark relief, litter, footprints |

Fine detail is a pure function of (world seed, position, kind), so it can be regenerated identically whenever the camera returns. The asset library caches the expensive pieces (trees, buildings, tiles, behaviour clips).

## Trees

`flora/tree.py`: crown envelope per species → attraction points → trunk/leader → space colonisation (with a fix for leaders that would otherwise cancel to zero and never branch) → pipe-model radii → tube sweep with flare/buttress lobes → foliage by leaf type. `detail` sets the leaf budget; below true leaf counts, leaf cards are enlarged so crown cover stays constant. `TWIG_CULL` drops twigs hidden by foliage at low detail.

## Animals

`fauna/agents.py` layers: needs → utility options (eat, drink, rest, climb, cache, retrieve, hunt, walk, explore) → softmax choice with a personality temperature → A* over a cost grid that prefers cover (shy species) and trails → execution with Ornstein–Uhlenbeck heading noise → interrupts (threat with flight-initiation distance, habituation and cooldown; opportunistic snack; pause; flock cohesion; pursuit). Memory holds food/water/cover/cache locations with time decay.

## Export

`export/gltf.py` writes GLB with vertex colours, int8 normals (`KHR_mesh_quantization`), node instancing for tree models, and linear translation/rotation animations for agents. `export/validate.py` checks structure, since no external validator runs offline. Internal frame z-up (x east, y north); glTF is y-up.

## Review loop

`render.py` is a small z-buffered rasteriser. Every generator change should be rendered and looked at; `scene/preview.py` makes the scene preview and annotated map.

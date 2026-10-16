# Asset library

Generate once, reuse everywhere. Every asset is stored under

```
key = blake2b(kind, generator version, canonical params)
assets_library/<kind>/<key[:2]>/<key>.npz   # arrays (compressed)
assets_library/<kind>/<key[:2]>/<key>.json  # params + metadata
assets_library/<kind>/<key[:2]>/<key>.glb   # optional, with --glb, for Blender/three.js/engines
assets_library/index.jsonl                  # searchable index
```

Kinds today: `tree`, `building`, `terrain`, `body`, `behavior` (each animal's lived trajectory as a reusable motion clip, stored relative to its start with traits, state mix and events), `texture` (leaf/needle cards and bark/ground detail maps, encoded PNG/JPEG bytes plus their mean colour and card crop box), `model` (one imported, decimated variant: mesh, UVs, its 512 px texture, source URL, authors and licence), `grass_patch` (reserved).

Textures and models are the only kinds that need the network to build (ambientCG and Poly Haven, CC0, licence pages probed into `catalog/asset_sites.json`). Raw downloads stay in `.cache/downloads/` (git-ignored); only the budget-sized results enter the library. A texture built from a procedural fallback (offline) is never stored, so the next networked run fetches the real one.

## Using it

```bash
python3 -m plandscape.assets bake --variants 3 --detail low --seasons spring summer fall winter
python3 -m plandscape.assets bake-models          # Poly Haven ground props
python3 -m plandscape.assets prune                # drop superseded generator versions
python3 -m plandscape.assets find tree species=sweetgum season=fall
python3 -m plandscape.assets find model role=fern
python3 -m plandscape.assets find behavior species=white_tailed_deer
python3 -m plandscape.assets stats
```

```python
from plandscape.assets.store import AssetStore
lib = AssetStore()
calm_deer = lib.find("behavior", species="white_tailed_deer",
                     traits=lambda t: t["boldness"] > 0.6)
```

`compose()` checks the library first for terrain, trees, buildings and bodies (`library_pool=True` draws trees from the shared seed pool `(0, v)` so scenes share models; set it False for scene-unique trees), and writes every animal's behaviour clip back.

## Versioning

`GENERATOR_VERSIONS` in `assets/store.py` is part of every key. Change a generator's output → bump its version → old entries stop matching (they stay on disk and readable until `prune`). Never reuse a version string for different output.

Size at v0.2.0: 36.5 MB (96 trees, 21 textures, 29 model variants, buildings, bodies, terrain, behaviour clips). Ask the owner before committing more than ~100 MB to LFS.

## Keeping it between sessions

Generation is deterministic, so `index.jsonl` alone can rebuild the library exactly; the binaries are a speed cache. Options for persisting them:

1. **Git LFS** (configured in `.gitattributes`). Fine for a curated starter set; watch GitHub's LFS storage and bandwidth quota for the account.
2. **Release assets / object storage** for large libraries: tar the library, attach it to a GitHub release or upload to a bucket, and point `PLANDSCAPE_ASSETS` at the unpacked folder.
3. **Rebuild on demand**: `bake` regenerates the same files from the index's params.

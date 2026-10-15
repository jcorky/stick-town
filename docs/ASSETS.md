# Asset library

Generate once, reuse everywhere. Every asset is stored under

```
key = blake2b(kind, generator version, canonical params)
assets_library/<kind>/<key[:2]>/<key>.npz   # arrays (compressed)
assets_library/<kind>/<key[:2]>/<key>.json  # params + metadata
assets_library/<kind>/<key[:2]>/<key>.glb   # optional, with --glb, for Blender/three.js/engines
assets_library/index.jsonl                  # searchable index
```

Kinds today: `tree`, `building`, `terrain`, `body`, `behavior` (each animal's lived trajectory as a reusable motion clip, stored relative to its start with traits, state mix and events), `grass_patch` (reserved).

## Using it

```bash
python3 -m plandscape.assets bake --variants 3 --detail low --seasons spring summer fall winter
python3 -m plandscape.assets find tree species=sweetgum season=fall
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

`GENERATOR_VERSIONS` in `assets/store.py` is part of every key. Change a generator's output → bump its version → old entries stop matching (they stay on disk and readable). Never reuse a version string for different output.

## Keeping it between sessions

Generation is deterministic, so `index.jsonl` alone can rebuild the library exactly; the binaries are a speed cache. Options for persisting them:

1. **Git LFS** (configured in `.gitattributes`). Fine for a curated starter set; watch GitHub's LFS storage and bandwidth quota for the account.
2. **Release assets / object storage** for large libraries: tar the library, attach it to a GitHub release or upload to a bucket, and point `PLANDSCAPE_ASSETS` at the unpacked folder.
3. **Rebuild on demand**: `bake` regenerates the same files from the index's params.

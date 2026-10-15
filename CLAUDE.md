# CLAUDE.md — stick-town (plandscape)

Prompt-driven procedural 3D landscapes of the American South: terrain, trees, grass, desire paths, vernacular buildings, and animals that plan routes and deviate from them. Python package `plandscape`, owner Jayde Cork (`jcorky`).

## Start here, every session

1. Load the **procedural-landscape** skill (`.claude/skills/procedural-landscape/SKILL.md`) and follow it. It holds the working loop, the non-negotiables and every pitfall hit so far.
2. Read **`HANDOFF.md`** for current status and the prioritised next steps.
3. `python3 -m unittest discover -s tests` and `python3 -m plandscape.assets stats` before changing anything.

## Commands

```bash
python3 -m plandscape "<prompt>" --out out/x [--detail low|med|high|cm] [--size 128] [--sim 180] [--seed N]
python3 -m plandscape.assets bake | find <kind> key=value | stats
python3 -m plandscape.sources.harvest probe | clone | index | discover
python3 -m unittest discover -s tests
```

## Rules that are easy to break

- All randomness through `plandscape.rng.rng(*keys)`, keyed by purpose.
- Core stays numpy + scipy + Pillow + matplotlib only.
- Expensive generators go through `AssetStore.get_or_build`; bump `GENERATOR_VERSIONS` when output changes.
- Render and look at every visual change; tests alone have missed broken pictures.
- Licences come from `harvest probe`, never from memory. Copyleft, non-commercial and unlicensed repos are study-only.
- World frame is z-up metres (x east, y north); glTF export converts to y-up.
- Scene GLBs stay under 15 MB.

## Layout

```
plandscape/   rng, noise, mesh, render · terrain/ flora/ ground/ paths/ fauna/ scene/ export/ assets/ sources/
viewer/       three.js r128 viewer (index.html)
catalog/      sources.json, harvest_report.json, PROVENANCE.md
assets_library/   content-addressed asset cache (Git LFS)
docs/         ARCHITECTURE, ASSETS, DATA_SOURCES
tests/        unittest suite
```

## End of session

Update `HANDOFF.md`, `CHANGELOG.md`, the skill's pitfalls section, and `README.md` if commands changed. Commit in small steps and push.

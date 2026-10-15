# Changelog

## 0.1.0 — 2026-10-15 (first session)

**Added**
- Zero-dependency core: purpose-keyed seeding, vectorised noise, mesh container, z-buffered preview renderer.
- Terrain for five Southern provinces (coastal plain, floodplain, Piedmont, Cumberland Plateau, Ridge and Valley) with thermal erosion, D8 creeks, meandering bayous, slope and moisture layers.
- Twelve tree species grown by space colonisation with pipe-model radii, root flare and buttresses, north-side moss, Spanish moss, cypress knees, needle tufts, palm fronds, flowers, seasons and detail levels.
- Ground: province soil colours, litter and pine straw, trampled trails, six grasses with winter dormancy, blade-level grass near the camera.
- Desire paths with the Helbing active-walker model (batched walkers).
- Fauna: deer, gray squirrel, wild turkey, armadillo, coyote, people — needs, personality, memory, utility decisions, A* routes, seeded deviation, flight distance with habituation, flocking, hunting, tree escapes, acorn caching, signs of life.
- Buildings: shotgun house, dogtrot, barn, farmhouse, church; mailbox, fence, clothesline.
- Prompt planner, scene composer, CLI, preview and annotated map.
- GLB writer with instancing, int8 normals and agent animations; structural validator.
- three.js r128 viewer with time-of-day lighting, wind, timeline, follow-cam and event log; base64 fallback for hosts that don't serve `.glb`.
- Content-addressed asset library with search and bake CLI; starter library (96 trees, 11 buildings, 23 bodies, 2 terrain tiles, 17 behaviour clips) in Git LFS.
- License-gated source catalog (23 repos, 10 datasets, 7 papers) and harvester; the probe corrected six guessed licences.
- `procedural-landscape` skill in `.claude/skills/`, `CLAUDE.md`, `HANDOFF.md`, docs and a 10-test suite.

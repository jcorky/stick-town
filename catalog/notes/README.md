# Repo notes — what we learned from each permissive source

One file per repo studied: what it does, the equations and constants that matter, what it does better
than us, what we do better, and what we adopted (with the commit). Licences come from
`catalog/harvest_report.json` (probed); clones live in `.cache/sources/` (git-ignored). Paths and line
numbers refer to the commit in the harvest report.

| Repo | Licence | Status |
|---|---|---|
| [terrain3d](terrain3d.md) | MIT | height blend (TECHNIQUES §13), lattice detiling (§20), clipmap idea (§22) adopted |
| [ocean](ocean.md) | MIT | water ideas queued |
| [seblague-erosion](seblague-erosion.md) | MIT | droplet erosion adopted (TECHNIQUES §14) |
| [worldengine](worldengine.md) | MIT | monotone creek beds adopted (§21); Holdridge lookup queued for real-place mode |
| [fantasy-map-generator](fantasy-map-generator.md) | MIT | road routing (§15), siting and naming patterns (§19), creek sizing idea (§21) adopted |
| [wfc](wfc.md) | MIT | low priority |
| [ez-tree](ez-tree.md) | MIT | chain tubes (§4), rounded normals + twig-attached cards (§18), uv.y leaf flutter (§20) adopted |
| [mesa](mesa.md) | Apache-2.0 | shuffled activation adopted (TECHNIQUES §16); vectorised neighbours not needed at ~10 agents |

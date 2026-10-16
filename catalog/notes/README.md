# Repo notes — what we learned from each permissive source

One file per repo studied: what it does, the equations and constants that matter, what it does better
than us, what we do better, and what we adopted (with the commit). Licences come from
`catalog/harvest_report.json` (probed); clones live in `.cache/sources/` (git-ignored). Paths and line
numbers refer to the commit in the harvest report.

| Repo | Licence | Status |
|---|---|---|
| [terrain3d](terrain3d.md) | MIT | height blend adopted (TECHNIQUES §13) |
| [ocean](ocean.md) | MIT | water ideas queued |
| [seblague-erosion](seblague-erosion.md) | MIT | droplet erosion queued (priority 1 terrain) |
| [worldengine](worldengine.md) | MIT | Holdridge lookup queued for real-place mode |
| [fantasy-map-generator](fantasy-map-generator.md) | MIT | road routing, siting, names queued |
| [wfc](wfc.md) | MIT | low priority |
| [ez-tree](ez-tree.md) | MIT | chain tubes + shared rings adopted (TECHNIQUES §4); card normals queued |
| [mesa](mesa.md) | Apache-2.0 | shuffled order, vectorised neighbours queued |

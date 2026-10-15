# Pitfalls learned the hard way

Append to this file whenever something costs you more than one attempt. Newest at the bottom.

## Environment (Claude sandbox)
- PyPI is blocked (connect_rejected), even via the proxy. Public `git clone` from GitHub works. Hence the zero-dependency core.
- The GitHub GraphQL API is unavailable; REST works only for repos attached to the session. You cannot create repos or install GitHub Apps from the session — ask the user.
- The session's GitHub identity can differ from the repo owner's account (v0.1: session was `thecheckdigit`, repo is `jcorky/stick-town`). Push needs the Claude app installed on the owner's account and GitHub reconnected in claude.ai Settings → Connectors.
- `pkill -f <pattern>` where the pattern appears in your own command line kills your shell (exit 144).
- Artifacts don't serve `.glb`. Publish `scene.glb.txt` (base64); the viewer decodes it.

## Numerics / geometry
- `_norm(v)` on a 1-D vector returns 1-D; indexing `[0]` turns it into a scalar and silently breaks direction maths (v0.1 trunk loop hung forever).
- Any growth loop needs an iteration cap and a z-clamp; a negative-tropism species (live oak) can steer a trunk downward forever.
- Space colonisation: a leader surrounded by attraction points on all sides averages to ~0 and never branches (pines came out as bare poles). Fall back to the direction of one associated point when the mean is small.
- Pipe model + DBH scaling makes leader tops too thick on excurrent trees; taper the trunk explicitly.

## Simulation
- Scalar `map_coordinates` per walker step is ~15× slower than advancing a batch of walkers in lockstep.
- Depositing only at step points on a 1 m grid gives dotted trails; also deposit at the step midpoint.
- Animals with perception ≈ tile size panic forever. Use flight-initiation distance (< perception, scaled by boldness), require the threat to be approaching, add a cooldown and habituation.
- "a turkey flock" must parse as a group; "shotgun house" must not also add a farmhouse.

## Rendering / review
- Painter's algorithm misorders large triangles (gable roofs looked like hips) — use the z-buffer renderer.
- When thinning triangles for a quick preview, never thin terrain/buildings; holes make the ground look missing.
- Dusk lighting in review renders hides form; the review preview uses neutral light, the viewer uses the scene's real light.
- Low leaf budgets make broadleaf crowns look like wire; scale leaf cards up to keep cover constant.

## Data / licences
- 6 of 23 licences in the first catalog draft were wrong when probed: terra (grass) is CC BY-NC, proctree / SimpleHydrology / SimpleErosion have no licence file (all rights reserved), Blender add-ons and blosm have no root licence file. Always probe.

## Asset library
- Continuous params (moisture 0.4137…, body scale 1.0734…) mean zero cache hits. Bucket them.
- Bump `GENERATOR_VERSIONS` when output changes, or the library serves stale models.

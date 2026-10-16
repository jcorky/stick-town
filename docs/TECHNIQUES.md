# Techniques and their equations

Every algorithm in plandscape, by name, with the equations as the code implements them and the
file they live in. Kept up to date with each change; commit messages quote the relevant entry.
Symbols in `code` are the parameter names in the source.

---

## 1. Purpose-keyed seeding (hash-derived RNG streams)
`plandscape/rng.py`

$$\text{seed}(k_1,\dots,k_n) = \text{BLAKE2b}_{64}\big(\text{repr}(k_1)\,\|\,\texttt{0x1f}\,\|\cdots\|\,\text{repr}(k_n)\,\|\,\texttt{0x1f}\big)$$

Each random decision draws from `default_rng(seed(purpose, ...))`, so streams are independent of
call order: adding a layer never changes what already existed.

## 2. Space colonisation (Runions, Lane & Prusinkiewicz 2007) — tree skeletons
`plandscape/flora/tree.py: grow_skeleton`

Attraction points $\mathbf{a}$ fill the species crown envelope. Node step $D = \text{clip}(H/45,\ 0.12,\ 0.55)$ m,
influence radius $d_i = 14D$, kill radius $d_k = 2D$. Each iteration, every point within $d_i$ of its
nearest node $v$ votes for it:

$$\mathbf{n}_v = \frac{1}{|S_v|}\sum_{\mathbf{a}\in S_v} \frac{\mathbf{a}-\mathbf{v}}{\lVert\mathbf{a}-\mathbf{v}\rVert},\qquad
\mathbf{v}' = \mathbf{v} + D\,\widehat{\big(\hat{\mathbf{n}}_v + \tau\,\hat{\mathbf{z}} + \boldsymbol{\epsilon}\big)},\quad \boldsymbol{\epsilon}\sim\mathcal{N}(0, 0.08^2)$$

with tropism $\tau$ (`sp.tropism`). If $\lVert\mathbf{n}_v\rVert < 0.25$ (votes cancel, e.g. a pine leader), one
representative direction is used instead. Points within $d_k$ of a new node are removed.

## 3. Pipe model (Shinozaki et al. 1964; "da Vinci's rule") — branch radii
`plandscape/flora/tree.py: grow_skeleton`

$$r_\text{parent}^{\,n} = \sum_{c\,\in\,\text{children}} r_c^{\,n},\qquad n = \texttt{sp.pipe\_n}\ (\approx 2\text{–}2.5)$$

Trunk nodes are then held to an explicit taper from the species DBH,
$r \ge \tfrac{\text{DBH}}{2}\,(1 - 0.85\,t_z)^{1.4}$ with $t_z$ = relative height, because pure pipe radii make
excurrent leaders too thick.

## 4. Chain tubes with shared rings, parallel transport and root flare — bark mesh (after ez-tree, MIT)
`plandscape/flora/tree.py: _chains, _bark_mesh`

The skeleton is split into **chains**: from each node follow the thickest child; every other child starts a new chain
at its parent (with a 1.08× collar). One ring per kept node, shared by the segments either side. Rings are resampled
along each chain: node $k$ keeps a ring when the run since the last ring reaches $\Delta s = \text{clip}(8r_k,\,0.3,\,1.5)$ m
or the chain bends ($\hat{\mathbf s}_k\cdot\hat{\mathbf s}_\text{last} < 0.978$, about 12°). Frames are carried by
**parallel transport** so the seam never twists at a node:

$$\mathbf t_k = \widehat{\mathbf p_{k+1}-\mathbf p_{k-1}},\qquad \mathbf u_k = \widehat{\mathbf u_{k-1} - (\mathbf u_{k-1}\cdot\mathbf t_k)\,\mathbf t_k},\qquad \mathbf w_k = \mathbf t_k\times\mathbf u_k$$

Sides per chain from its base radius: 10 / 8 / 5 / 3 for $r_0 >$ 0.12 / 0.05 / 0.02 m / else; terminal tips taper to
$0.5\,r$; chains thinner than `TWIG_CULL` (0.03 / 0.015 / 0.006 / 0 m for low / med / high / cm) are dropped.

Ring $k$ of $s$ sides around segment direction $\mathbf{t}$ with frame $(\mathbf{u},\mathbf{w})$:

$$\mathbf{p}_k = \mathbf{c} + r\,f(z,\theta_k)\,(\mathbf{u}\cos\theta_k + \mathbf{w}\sin\theta_k),\qquad
f = 1 + \text{flare}\;e^{-z/0.45}\,\big(1 + 0.45\cos(n_\text{lobe}\theta_k + \phi)\big)$$

**Bark UVs (cylindrical, arc-length):** the seam vertex is duplicated ($s+1$ per ring) so $u$ never wraps,

$$u = \frac{\theta_k}{2\pi}\,\text{reps},\quad \text{reps} = \max\!\big(1,\ \text{round}(2\pi r_0/\ell)\big)\ \text{per chain},\qquad
v = \frac{s_\text{arc}}{\ell},\quad s_\text{arc}(i) = s_\text{arc}(\text{parent}) + \lVert \mathbf{p}_i - \mathbf{p}_\text{parent}\rVert$$

with tile length $\ell$ = 1 m, so texel size stays roughly constant from trunk to twig.

## 5. Detail-texture modulation — one grey texture, any colour
`plandscape/textures.py`, `plandscape/export/gltf.py`

A detail map has mean $\mu$ (0.8 for leaf, needle, bark and ground maps). The GLB stores

$$\text{COLOR\_0} = \text{clip}\!\left(\frac{\mathbf{c}_\text{vertex}}{\mu}\right),\qquad
\text{shaded colour} = T(u,v)\cdot\text{COLOR\_0}\ \Rightarrow\ \mathbb{E}[\,\cdot\,] = \mathbf{c}_\text{vertex}$$

so vertex colour stays the final look (preview, fallbacks) and the texture only adds detail; one
oak-leaf texture serves summer green, fall red and spring lime. Detail maps are luminance-normalised:
$L' = \mu + (L - \bar L)\,\frac{\mu}{\bar L}\,\kappa$ with contrast $\kappa$.

## 6. Leaf-sprig and needle-tuft cards (alpha-masked billboards)
`plandscape/textures.py: leaf_cluster, needle_tuft`; `plandscape/flora/tree.py: _foliage_mesh`

Leaves are cut from an atlas as connected components of the opacity map (area $> 0.25\cdot$ largest),
then composited along a twig. Each card is cropped to its opaque box (aspect $\alpha$, opaque share
$\rho$). The card length keeps crown cover constant for any budget of $N$ cards:

$$N\,L^2\,\alpha\,\rho\,\phi \approx 3.2\,A_\text{shell}\ \Rightarrow\ L = \sqrt{\frac{3.2\,A_\text{shell}}{N\,\alpha\,\rho\,\phi}},\qquad
A_\text{shell} = 1.2\cdot 4\pi R\,\max\!\big(H(1-c_b)/2,\ 0.5\big)$$

with $\phi$ = `FOLD_COVER` = 0.92 for folded cards (below).

**Folded cards (V-fold about the twig).** With twig axis $\mathbf{a}$, side $\mathbf{s}$ and card normal
$\mathbf{n} = \mathbf{s}\times\mathbf{a}$, each wing is rotated by $\theta\sim\mathcal{U}(0.35, 0.65)$ rad (sign random):

$$\mathbf{w}_\text{L} = -\mathbf{s}\cos\theta + \mathbf{n}\sin|\theta|,\qquad \mathbf{w}_\text{R} = \mathbf{s}\cos\theta + \mathbf{n}\sin|\theta|$$

6 vertices and 4 triangles per card; the projected width is $\cos\theta \approx 0.92$ of flat, hence $\phi$.
Pines use two crossed needle cards per shoot.

## 7. Active-walker model (Helbing, Keltsch & Molnár 1997) — desire paths
`plandscape/paths/desire.py: simulate`

Trail field $G\in[0,1]$. Walkers see a blurred comfort map $V = G * \mathcal{N}_\sigma$, $\sigma$ = `visibility`/res.
Heading update per step (length 0.7 m):

$$\mathbf{e} \leftarrow \widehat{\frac{\mathbf{x}_\text{dest}-\mathbf{x}}{\lVert\cdot\rVert} + \beta\,\widehat{\nabla V}\,\min(1, 40\lVert\nabla V\rVert) - 6\,\nabla C + \boldsymbol{\eta}}$$

with attraction $\beta$ = 1.4, obstacle cost $C$ (slope, water, trunks, footprints), noise $\boldsymbol\eta\sim\mathcal N(0,0.12^2)$.
Deposition at the step and its midpoint, and regrowth per batch of $b$ walkers:

$$G \mathrel{+}= I\,(1 - G),\quad I = 0.06\cdot 0.6;\qquad G \leftarrow G\,(1 - \lambda b),\quad \lambda = 0.002$$

## 8. Utility choice with softmax temperature — animal decisions
`plandscape/fauna/agents.py: Agent.decide`

$$P(o) = \frac{e^{(U_o - U_\max)/T}}{\sum_{o'} e^{(U_{o'} - U_\max)/T}},\qquad T = 0.08 + 0.25\cdot\text{curiosity}$$

Same needs, different personalities, different choices.

## 9. Ornstein–Uhlenbeck heading noise — walking that wobbles but never repeats
`plandscape/fauna/agents.py: Agent.step`

$$d\omega = -0.8\,\omega\,dt + \sigma\,dW,\quad \sigma = 0.9\,(0.4+\text{wanderlust});\qquad
\dot\psi = 2\,\text{wrap}(\psi_\text{goal}-\psi) + \omega$$

**Flight-initiation distance** shrinks with boldness and habituation $h$:
$d_\text{FID} = 0.45\,d_\text{perceive}\,(1.3 - \text{boldness})/(1 + 0.35h)$; flee only if the threat closes or $d < d_\text{FID}/2$.

## 10. Vertex-clustering simplification (Rossignac & Borrel 1993) — decimating photoscans
`plandscape/models.py: decimate, _cluster`

Cell size $h$ is binary-searched (geometric mean of bounds, ≤ 22 steps) until the triangle count lands
in $(0.85\,T, T]$. Positions are welded per cell, so neighbours share a vertex and no cracks open:

$$\text{cell}(\mathbf p) = \left\lfloor \frac{\mathbf p - \mathbf p_\min}{h}\right\rfloor,\qquad
\bar{\mathbf p}_c = \frac{1}{|c|}\sum_{\mathbf p\in c}\mathbf p$$

Vertices split within a cell by UV chart $\lfloor 6\,\mathbf{uv}\rfloor$ and dominant normal axis, so seams
and two-sided sheets keep their own UVs while sharing $\bar{\mathbf p}_c$. Degenerate and duplicate triangles are dropped.

**Card thinning (alpha foliage).** Connected components with more than 5% of the triangles (stems) are kept;
the rest are sampled to fit the budget and scaled about their centroids by
$\min\!\big(1/\sqrt{f},\ 2\big)$, where $f$ is the kept fraction of the thinned triangles, so cover holds.

## 11. Habitat-weighted scatter with rejection — ground props
`plandscape/scene/groundcover.py: scatter`

Candidates are uniform in the focus box. A candidate is rejected on water ($>0.3$), trails ($G>0.2$),
footprints, trunk clearance ($d - 2.5\,r_\text{trunk} < 0.3 + 0.8\,r_\text{prop}$) and overlap. Model $m$ is drawn with

$$P(m) \propto w_m^\text{biome}\cdot h_{\text{role}(m)}(\text{canopy}, \text{moisture}, \text{slope}),\qquad
h_\text{fern} = 1.5\,c\,\text{clip}\!\left(\frac{M-0.2}{0.3}\right),\quad h_\text{rock} = k_\text{prov}\big(0.3 + \text{clip}(s/25, 0, 1)\big)$$

Count $= \rho_\text{biome}\,A\,(1 + 0.3\,k_\text{prov})$; props sink by a role fraction of their height.

## 12. GLB quantisation (KHR_mesh_quantization, KHR_texture_transform)
`plandscape/export/gltf.py`

Normals: $\text{int8} = \text{round}(127\,\hat{\mathbf n})$. Card UVs in $[0,1]$: $\text{uint16} = \text{round}(65535\,uv)$.
Tiling UVs (bark, ground) are shifted by whole tiles and scaled by $k = 64$:

$$uv' = \frac{uv - \lfloor \min uv\rfloor}{k}\in[0,1]\ \to\ \text{uint16},\qquad \text{texture transform scale} = k$$

Indices are uint16 when a mesh has fewer than 65,536 vertices.

## 13. Height-blended ground splatting (after Terrain3D, MIT)
`plandscape/ground/surface.py: ground_weights`; `plandscape/textures.py: height_blend`; `viewer/index.html: addSplat`; `plandscape/render.py`

Four materials per vertex, $\mathbf a = (\text{litter}, \text{soil}, \text{grass}, \text{mud})$, from layers the scene already has
(trail $G$, canopy $c$, grass density $d$, water $W$, slope $s$ in degrees), with $g = \text{clip}(1.3G)$:

$$a_\text{litter} = \text{clip}\big(c\,(0.6 + \ell)\big)(1-g),\quad a_\text{soil} = \max\!\big(g,\ \text{clip}(\tfrac{s-25}{20})\big) + 0.25(1-d)(1-c)$$
$$a_\text{grass} = d\,(1 - 0.8c)(1-g),\quad a_\text{mud} = \text{clip}\big(2\,(W * \mathcal N_{2\,\text{m}})\big)\big(1 - \text{clip}(s/45)\big)$$

plus low-frequency noise jitter (amplitude 0.12) so edges wander, then $\sum_i a_i = 1$. Per pixel, with each
grey detail map's own luminance as its height $h_i$ and sharpness $k = 8$:

$$W_i = \frac{(a_i + h_i)^k\,a_i}{\sum_j (a_j + h_j)^k\,a_j},\qquad \text{albedo} = \text{COLOR\_0}\cdot\sum_i W_i\,T_i(\mathbf x_{xy}/2\,\text{m})$$

so grass fills the hollows of the litter and trodden soil breaks through where the trail is strongest, not along
triangle edges. The weights ship as a custom glTF attribute `_SPLAT` (uint8 ×4) and the four textures as material
`extras.splat`; our viewer blends them in the fragment shader, other viewers fall back to the single base texture.
Terrain3D's per-vertex control map holds two IDs plus a blend byte and multiplies by a bilinear weight $b$:
$W = (b + t + h)^k\,b$ with $k = 4 + 60\cdot\text{sharpness}$; ours stores four weights directly.

## 14. Droplet hydraulic erosion, batched (after Sebastian Lague, MIT)
`plandscape/terrain/erosion.py: droplet_erosion` (run after thermal erosion, before D8 creeks)

Heights are normalised to $[0,1]$ ($\tilde z = (z - z_\min)/H$), eroded, and scaled back. Droplets start at keyed
random positions, 0.5 per cell, in batches of 2048 advanced in lockstep for 30 steps. Per step, with fractional
offsets $(f_x, f_y)$ in the cell and corner heights NW, NE, SW, SE:

$$g_x = (h_{NE}-h_{NW})(1-f_y) + (h_{SE}-h_{SW})f_y,\qquad g_y = (h_{SW}-h_{NW})(1-f_x) + (h_{SE}-h_{NE})f_x$$
$$\mathbf d \leftarrow \widehat{\mathbf d\,\iota - \mathbf g\,(1-\iota)}\ (\lVert\cdot\rVert \ge 0.01),\qquad \mathbf p \leftarrow \mathbf p + \mathbf d,\qquad \Delta h = h(\mathbf p_\text{new}) - h(\mathbf p_\text{old})$$
$$c = \max(-\Delta h\,v\,w\,C,\ 0.01)$$

If $s > c$ or $\Delta h > 0$: deposit $\min(\Delta h, s)$ (uphill) or $(s-c)\,k_d$, split bilinearly over the four corners.
Otherwise erode $\min\big((c-s)\,k_e,\ -\Delta h\big)$ over a brush of radius $r$ with weights $w_i \propto 1 - d_i/r$,
never taking more than a node's height. Then $v \leftarrow \sqrt{\max(0,\ v^2 + g\,\Delta h)}$, $w \leftarrow w(1-\epsilon)$.

Constants: inertia $\iota = 0.4$, capacity $C = 4$, $k_e = k_d = 0.3$, $\epsilon = 0.01$, gravity 4, brush $r = 5$
(Lague: $r = 3$, $\iota$ = 0.05–0.3, which carves hair-fine rills at our 1 m cells). Scatter-adds use `np.bincount`.
Strength 0.25 on floodplains and 0.5 on the coastal plain so flat country doesn't gully.

## 15. County road: least-cost route, smoothing, cut and fill (routing after Fantasy-Map-Generator, MIT)
`plandscape/scene/roads.py`; placement in `plandscape/scene/compose.py`

**Route.** Dijkstra on the 8-connected 1 m grid from the west edge to the east edge (end heights keyed per scene).
A step between cells $a$ and $b$ of length $d$ costs

$$w_{ab} = d\cdot\tfrac12\big(k_a + k_b\big),\qquad k = \big(1 + (s/12)^2\big)\,(1 + 8W)\,\big(0.5\ \text{if}\ G > 0.35\big)$$

with slope $s$ in degrees, water $W$ and trail strength $G$, so the road contours around steep ground, avoids
creeks and reuses old paths.

**Smooth.** Twice, every vertex with interior angle $\alpha$ moves toward its neighbours' midpoint $\mathbf m$:
$\mathbf p \leftarrow \mathbf p + f(\mathbf m - \mathbf p)$, with $f = \tfrac23$ if $\alpha < 115°$ and $\tfrac12$ if $\alpha < 135°$.
Then three rounds of Chaikin corner cutting ($\tfrac34\mathbf a + \tfrac14\mathbf b,\ \tfrac14\mathbf a + \tfrac34\mathbf b$) and resampling every 1 m.

**Grade.** Centreline height $z_c$ is the terrain under it, Gaussian-smoothed along the road ($\sigma = 8$ m). With $d$ the
distance from a cell to the centreline (Euclidean distance transform, nearest centre point by `return_indices`)
and road width $W_r = 4.5$ m:

$$z = \begin{cases} z_c + 0.08\big(1 - (2d/W_r)^2\big) - 0.12 & d \le W_r/2 \quad\text{(crowned bed)}\\
z_c - 0.35\sin\!\big(\pi\,(d - W_r/2)/2\big) & W_r/2 < d \le W_r/2 + 2 \quad\text{(ditch)}\\
z_c\,(1 - \beta) + z_\text{terrain}\,\beta,\ \ \beta = \text{smoothstep}\big((d - W_r/2 - 2)/4\big) & \text{beyond (blend back)}\end{cases}$$

**Surface.** A gravel ribbon 3 cm above the crown (12 cm above the bed so the 1 m terrain never pokes through), five
vertices across, UV $(u, v) = (\text{across}\cdot W_r/4,\ s/4)$ with $s$ the distance along the road. Buildings sit
$W_r/2 + 6$ m off the road on its north side, yawed to face it; mailboxes at $W_r/2 + 0.8$ m; the fence runs
$W_r/2 + 3.2$ m out and leaves a 3 m gate at each mailbox.

## 16. Agent scheduling and canopy behaviour (scheduling after Mesa, Apache-2.0)
`plandscape/fauna/agents.py: run, Agent.arrive, spawn`

**Random activation.** Each step $k$ the acting order is a fresh permutation from a keyed stream,
$\pi_k = \text{perm}\big(\text{rng}(\text{"act\_order"}, \text{seed}, k)\big)$, so no species always acts before another
(a coyote no longer always moves before the deer it hunts), and the same seed still replays exactly.
Agent ids are their index in the scene, $\text{id} = |\text{agents so far}|$, never a process-wide counter.

**Canopy activity.** A squirrel that reaches its tree freezes only if it bolted there ($\text{fear} > 0.35$, for
$\mathcal U(4, 12)$ s). Otherwise it picks an activity with weights

$$w = \big(0.5 + 0.8\,\text{hunger},\ 0.25,\ 0.25 + 0.6\,\text{fatigue}\big)\ \text{for}\ (\text{eat}, \text{groom}, \text{rest}),$$

lasting $\mathcal U(6,25)$, $\mathcal U(3,10)$ and $\mathcal U(10,40)$ s. Audit over four seeds: freeze 28 % → under 1 %,
canopy eating 24 %, rest 12 %.

## 17. Curved, trampled grass blades
`plandscape/ground/surface.py: grass_mesh`

Each blade (height $h$, width $w$, heading $\psi$, bend $b \sim \mathcal U(0.15, 0.6)$) is two segments, five vertices,
three triangles, along a quadratic curve with tapering width:

$$\mathbf c(t) = \mathbf p_0 + \hat{\mathbf z}\,h\,t\,\big(1 - \tfrac12 b^2 t\big) + \hat{\mathbf d}_\psi\,h\,b\,t^2,\qquad w(t) = w\,(1 - t),\qquad t \in \{0, \tfrac12, 1\}$$

**Trampling.** With trail strength $g = \text{clip}(1.4\,G)$ under the blade and the travel direction taken
perpendicular to the smoothed trail gradient, $\hat{\mathbf d}_\text{travel} \perp \nabla(G * \mathcal N_1)$ (either sense):

$$\psi \leftarrow (1-g)\,\psi + g\,\psi_\text{travel},\qquad h \leftarrow h\,(1 - 0.65\,g),\qquad b \leftarrow b + (0.95 - b)\,g$$

so blades at path edges are shorter and lie over along the path. Vertex shade rises from 0.7 at the base to 1.08 at the
tip. Three segments cost +2.7 MB per scene for little visible gain at `low`; two segments cost +1.4 MB.

## 18. Rounded crown normals and twig-attached cards (after ez-tree, MIT)
`plandscape/flora/tree.py: _foliage_mesh, _crown_normals`; `plandscape/render.py`; `plandscape/export/gltf.py`

**Twig attachment.** A broadleaf card's anchor sits on its twig, a fraction $\tau \sim \mathcal U(0.35, 1)$ along the
parent→node segment, with a small spread: $\mathbf a = \mathbf p_\text{parent} + \tau(\mathbf p_\text{node} - \mathbf p_\text{parent}) + \mathcal N(0, (0.12L)^2)$
(was $\mathbf p_\text{node} + \mathcal N(0, (0.35L)^2)$, which let cards float off the wood).

**Rounded normals.** Card vertices get the crown's volume normal instead of their flat face normal, so the canopy
shades as one rounded mass, lit on top and darker underneath:

$$\mathbf n = \widehat{k\,\hat{\mathbf r} + (1-k)\,s\,\mathbf n_\text{face}},\qquad \hat{\mathbf r} = \widehat{\mathbf v - \mathbf c_\text{crown}},\quad s = \operatorname{sign}(\mathbf n_\text{face}\cdot\hat{\mathbf r}),\quad k = 0.65$$

Flowers and Spanish moss keep geometric normals. `Mesh.nrm` carries authored normals through transforms
($\mathbf n' = \widehat{R\mathbf n}$), the library (int8) and the GLB; the preview renderer shades authored-normal triangles
with their mean vertex normal, unflipped.

## 19. House siting and place names (siting after Fantasy-Map-Generator, MIT)
`plandscape/scene/names.py: site_scores, scene_names`; `plandscape/scene/compose.py`

**Siting.** Every road point $k$ proposes a plot $W_r/2 + 12$ m off the road; within a $\pm 6$ m footprint

$$s_k = -\frac{\overline{\text{slope}}}{6} - 6\max W - 2\,\big|\Delta z_{\text{plot}-\text{road}} - 1\,\text{m}\big| + 1.5\,e^{-\left(\frac{d_\text{creek} - 30}{20}\right)^2} + \mathcal U(0, 0.3)$$

(flat, dry, a metre above the road, near but not in the creek; the noise only breaks ties). Plots in the outer 12 %
of the tile are excluded; houses take the best scores greedily, at least 30 m apart, then sort west→east.

**Names** are invented by Southern naming patterns rather than a syllable chain, keyed by `rng("names", seed, province)`:
creek = (nature word | family) + regional water word (Branch / Creek / Fork in the hills, Bayou / Slough in the Delta);
road = one of *family* Rd, *nature landform* Rd, *church* Church Rd, Old *landform* Rd, *creek word* Rd;
church = (Pleasant Hill | Mount Zion | New Hope | Shiloh | …) + (Baptist | Methodist | Missionary Baptist | A.M.E. | …);
homestead = "the *family* place". Names go into `scene.json` and are labelled on `map.png`.

## 20. Lattice detiling and leaf flutter (detiling after Terrain3D, MIT; flutter after ez-tree, MIT)
`plandscape/textures.py: detile_sample`; `plandscape/render.py`; `viewer/index.html: detile, addWind`

**Detiling.** A ground texture repeated every 2 m shows a grid from any height. Over a lattice of spacing
$L = 1.5$ tiles, each node $c$ gets a hash, a rotation and an offset

$$h_c = \operatorname{frac}\!\big(\sin(c \cdot (127.1,\ 311.7)) \cdot 43758.5453\big), \qquad \theta_c = 2\pi h_c, \qquad o_c = \big(h_c,\ \operatorname{frac}(7.13\,h_c)\big)$$

and the texel at $p$ (in tiles) samples the texture once per surrounding node, $s_c = T(R(\theta_c)\,p + o_c)$.
The four samples are mixed with bilinear weights $b_c$ sharpened by the samples' own luminance, like the splat (§13):

$$W_c = (b_c + s_c)^{k}\, b_c, \quad k = 8, \qquad T_\text{detiled}(p) = \frac{\sum_c W_c\, s_c}{\sum_c W_c}.$$

$b_c \to 0$ on the far side of every lattice line, so the result is continuous; the luminance term makes the
transition follow pebbles and leaf edges instead of a smear. The viewer runs the same function in GLSL with
`textureGrad` (rotation would otherwise break mip selection); the preview renderer uses the numpy version.

**Leaf flutter.** On top of the existing trunk sway, each leaf card's vertices move along their normal, weighted
by distance from the twig ($v = 1$ at the attachment, $v = 0$ at the tip):

$$w_\text{tip} = \operatorname{clamp}(1 - v,\ 0,\ 1), \qquad f(t) = 0.5\sin(4t + \phi) + 0.3\sin(8t + 1.3\phi) + 0.2\sin(20t + 1.5\phi),$$
$$\Delta p = 0.05\ \text{m}\cdot w_\text{tip}\, f(t)\, \hat n,$$

with $\phi = 2\pi\,\operatorname{frac}(0.37x + 0.71z)$ a per-vertex phase from object position. The twig end never moves, so cards stay attached.

## 21. Creeks as channels: routed, sized, meandered, graded (literature methods; width idea after Fantasy-Map-Generator, MIT)
`plandscape/terrain/channels.py`; `plandscape/terrain/heightfield.py: generate_tile`; `plandscape/scene/compose.py` (water surface); `preview.creek`

Creeks used to be the 1 % of cells with the most flow: grid-aligned strips of one width, broken wherever a pit
stopped the flow, under a water surface of 1 m squares. Now each creek is a polyline carried through six steps.

**1. Routing surface.** *Priority-Flood + ε* (Barnes, Lehman & Mulla 2014) fills every pit. It grows inward from
the tile border in height order, and each newly reached cell $n$, reached from $c$, becomes

$$z'(n) = \max\big(z(n),\ z'(c) + \varepsilon\big), \qquad \varepsilon = 10^{-3}\ \text{m}.$$

Filled ponds are then tilted toward their own centreline, after Garbrecht & Martz (1997), "away from higher
terrain":

$$z_r = \mathrm{PF}\big(\mathrm{PF}(z) - \kappa\,\varepsilon\, d_\text{edge}\big), \qquad \kappa = 0.3,$$

where $d_\text{edge}$ is the distance to the flat's rim. Because $\kappa < 1$, the outlet gradient still wins, so no new pit can form.

**2. Jittered D8.** Plain D8 snaps flow to 8 directions, so a valley trending 10° off an axis drains in a
dead-straight grid line. Each candidate slope is instead scaled by noise keyed per cell and direction, in the
spirit of Rho8 (Fairfield & Leymarie 1991):

$$\tilde S_k = \frac{z - z_k}{\ell_k}\,(1 + \epsilon_k), \qquad \epsilon_k \sim \mathcal U(-0.35, 0.35).$$

The steepest $\tilde S_k$ is the receiver. Flow accumulation $A$ (cells) runs high to low over these receivers.

**3. Trace.** Channel cells satisfy $A \ge A_c = \max(P_{98.8}(A),\ 150)$, at least 3 cells from the tile edge.
- Each head (a channel cell with no channel donor), highest first, is walked downstream until it reaches the edge band or a reach traced before it, which makes a junction.
- Lines shorter than 20 cells that join nothing are dropped.
- A line that runs within 6 m of a bigger kept line for more than 40 % of its length is also dropped, because flow spreading over a fan in parallel threads is one creek, not five.

**4. Size: hydraulic geometry** (Leopold & Maddock 1953; FMG grows river width with flux$^{0.7}$):

$$w = \min\!\big(1.2\,(A/A_c)^{0.5},\ 9\big)\ \text{m}, \qquad d = \min\!\big(0.35\,(A/A_c)^{0.4},\ 1.6\big)\ \text{m}.$$

**5. Meander: a sine-generated curve with Kinoshita's terms** (Langbein & Leopold 1966; Kinoshita 1961;
$J_s = 1/32$, $J_f = 1/192$ after Abad & Garcia 2009). D8 lines are first Gaussian-smoothed ($\sigma$ = 2 cells,
ends pinned) and Chaikin-cut twice. Then, along arc length $s$,

$$\theta(s) = \theta_0 \sin(ks) + \theta_0^3\big(\pm J_s \cos 3ks - J_f \sin 3ks\big), \qquad k = \frac{2\pi}{\lambda}, \quad \lambda = 11\,\bar w,$$
$$\theta_0 = \theta_\text{min} + (\theta_\text{max} - \theta_\text{min})\,\operatorname{clip}\!\left(1 - \frac{S}{0.08}\right), \qquad \theta_\text{min} = 20°, \quad \theta_\text{max} = 80°,$$
$$y(s) = \Big(\int_0^s \sin\theta\, ds' - G_{\lambda/2} * \!\int\Big)\ \cdot\ \operatorname{smoothstep}\!\Big(\frac{\min(s,\ L - s)}{\lambda/2}\Big).$$

- $S$ is the reach's channel slope.
- The offset $y$ is applied along the normal.
- The high-pass $G_{\lambda/2}$ removes drift.
- The smoothstep pins both ends.
- Steep step-pool branches only wander; flat-country creeks loop.
- A tributary's last 20 m is bent onto the meandered point of the stem it joins.
- Flat provinces (floodplain, coastal plain) get one 4.8–7.2 m bayou laid across the tile, meandered the same way.

**6. Grade and cut.** The bank-full level runs only downhill. It is the downstream cumulative minimum of the terrain smoothed
along the reach ($\sigma$ = 4 m),

$$z_b(s) = \min_{s' \le s}\ (G_4 * z)(s'),$$

and a tributary is held at or below the stem's $z_b$ at the junction. With $r$ the exact distance to the nearest
centreline sample (KD-tree over 0.5 m samples),

$$z \leftarrow \begin{cases} \min\!\big(z,\ z_b - d\,(1 - (2r/w)^2)\big) & r \le w/2 \quad\text{(parabolic bed)}\\ \min\!\big(z,\ z_b + 0.6\,(r - w/2)\big) & r > w/2 \quad\text{(bank)}\end{cases}$$

The bank cut is blended back to the untouched slope by a smoothstep over $w + 2$ m. Water stands at
$z_w = z_b - 0.4\,d$, which wets $r < w\sqrt{0.6}/2$. That gives the `water` and `stage` layers.

The surface itself is a ribbon along each reach at $z_w$, 1.15 × the wetted width (the excess tucks under the banks).
Stage is monotone downstream, so water never climbs.

## 22. Near-camera terrain: a two-level clipmap with micro-relief (clipmaps after Losasso & Hoppe 2004, as in Terrain3D, MIT)
`plandscape/terrain/refine.py: windows, build, stitch`; `Heightfield.sample` (patch-aware); `scene/compose.py`

The 1 m tile draws a 1.5 m creek in one or two cells and every bank as a facet. Geometry clipmaps keep resolution
where the eye is. A scene here is static, so the eye is chosen: a window on the focus (grass, props, closeup) and,
unless it overlaps, one on the creek where it is widest. Window size and spacing $h$ come from `detail`: low
24 m at 25 cm, med 32 m at 25 cm, high 48 m at 20 cm, cm 32 m at 10 cm. Windows sit on whole metres.

Inside a window,

$$z_f = B(z) + \tau\,\big(C(z) - B(z) + m\big), \qquad m = 0.04\ \text{m}\cdot \operatorname{fbm}\!\Big(\frac{x}{0.9}, \frac{y}{0.9}\Big)\,(1 - W),$$
$$\tau = \operatorname{smoothstep}\!\Big(\min\!\Big(\frac{d_\text{edge}}{2\ \text{m}},\ 1\Big)\Big).$$

- $B$ is bilinear interpolation of the 1 m grid, which is exactly what the coarse mesh draws along its grid lines.
- $C$ is cubic B-spline interpolation, so hills are round, not faceted.
- $m$ is micro-relief (clods, roots, ant hills), damped in water $W$.
- $\tau$ is 0 on the window border. The fine border vertices therefore lie on the coarse triangles' edges: no crack, no skirt, no T-junction gap wider than float error.

Creeks are then cut again on the fine grid, with the same bed and bank equations as §21, from `hf.channels` (which now
also stores depth) resampled every 5 cm, and blended by $\tau$:

$$z \leftarrow z + \tau\,(1 - P)\,\big(\mathrm{carve}_h(z) - z\big).$$

$P$ protects the graded road bed where the road fords. Banks become smooth curves instead of 1 m steps.

**Stitch.** Coarse triangles whose centroid falls inside a window are dropped. The fine grid is appended with
colours and splat weights bilinearly interpolated from the coarse vertices, and UVs $= xy/\text{tile}$ as on the coarse mesh.
The result is still one terrain mesh, one splat material. `Heightfield.sample` reads heights from the fine patch inside a window,
so grass, ground props and tree trunks placed afterwards sit on the refined ground. At `low` the terrain grows
from 33k to 67k triangles (+0.7 MB per scene).

## 23. Far LOD: cross-billboard impostors with a viewer-faithful bake (billboard LOD as in SpeedTree; three.js `LOD`)
`plandscape/flora/impostor.py: bake, mesh`; `render(alpha, shading, viewer_colour)`; `scene/compose.py`; `viewer/index.html: addLODs`

A tree at 110 m covers a few dozen pixels, but it still costs 5–30k triangles. ez-tree's LOD only thins rings and
segments (`catalog/notes/ez-tree.md`). The far tier here replaces the tree with two crossed, alpha-tested cards
carrying the tree baked from two sides.

**Bake.** The tree (bark + foliage) is rendered orthographically at elevation 0 from azimuth 0° (looking +y) and
90° (looking +x) into the two halves of one RGBA atlas, 2 × 96 × 160 px. With $R$ the crown's horizontal radius and
$H$ the height, the renderer maps a point to pixels by

$$\text{span} = \max\!\Big(\frac{2R}{0.95\,w},\ \frac{H}{0.95\,h}\Big), \qquad u_\text{px} = \frac{w}{2} + \frac{s}{\text{span}}, \qquad v_\text{px} = \frac{h}{2} - \frac{z - H/2}{\text{span}},$$

where $s$ is the coordinate along the card. The quad corners $(\pm R, 0)$ and $(\pm R, H)$ get exactly those UVs, so the baked tree stands
where the mesh tree stands. Transparent texels take the colour of the nearest opaque one (edge padding by
distance-transform indices), so mipmaps don't fringe the cards with sky.

**Viewer-faithful colour.** The first bake was darker and more saturated than the mesh trees beside it. That was not the bake's
light but its colour arithmetic. The preview renderer draws $c\,T/\mu$; the viewer draws COLOR_0 $= \operatorname{clip}(c/\mu, 0, 1)$
(linear) times the sRGB-decoded texture. So the bake now runs unlit and reproduces the viewer:

$$A = \operatorname{encode}\!\big(\operatorname{clip}(c/\mu, 0, 1)\cdot \operatorname{decode}(T)\big), \qquad \operatorname{decode}(x) = x^{2.2},\quad \operatorname{encode}(y) = y^{1/2.2}.$$

Untextured triangles become $\operatorname{encode}(c)$. The cards' vertex colour is the atlas mean, so their COLOR_0 is 1.

**Light.** The atlas holds albedo only. The viewer lights the cards through rounded normals, as for crowns (§18):

$$n = \operatorname{normalize}\big(0.6\,\sigma\,\hat a + (0, 0, \zeta)\big), \qquad \zeta = 0.5 \text{ (top corners)},\ 0.1 \text{ (bottom)},$$

where $\sigma = \pm 1$ is the side and $\hat a$ the card axis.

**Wiring.** Atlases are cached per tree model (`impostor` kind in the library). Each tree node in the GLB names its
impostor mesh in `extras.lod_far` but does not instance it, so viewers without LOD support draw only the real tree.
The viewer swaps each such node for a `THREE.LOD`: the full tree from 0 m, the cards beyond `LOD_FAR` = 110 m
(`?lod=0` turns impostors off). The cards cast alpha-tested shadows. Cost: about 25 KB per tree model (+0.4 MB per scene); 4 triangles
replace a tree.

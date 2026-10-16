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

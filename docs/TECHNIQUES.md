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

## 4. Swept tubes with root flare — bark mesh
`plandscape/flora/tree.py: _bark_mesh`

Ring $k$ of $s$ sides around segment direction $\mathbf{t}$ with frame $(\mathbf{u},\mathbf{w})$:

$$\mathbf{p}_k = \mathbf{c} + r\,f(z,\theta_k)\,(\mathbf{u}\cos\theta_k + \mathbf{w}\sin\theta_k),\qquad
f = 1 + \text{flare}\;e^{-z/0.45}\,\big(1 + 0.45\cos(n_\text{lobe}\theta_k + \phi)\big)$$

**Bark UVs (cylindrical, arc-length):** the seam vertex is duplicated ($s+1$ per ring) so $u$ never wraps,

$$u = \frac{\theta_k}{2\pi}\,\text{reps},\quad \text{reps} = \max\!\big(1,\ \text{round}(2\pi r/\ell)\big),\qquad
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

"""Image textures: leaf-cluster cards, bark and ground detail, imported-model maps.

Meshes keep their vertex colours as the *final* look (the preview renderer and
untextured fallbacks use them). A texture adds detail on top: the GLB exporter
writes COLOR_0 = colour / texture.mean, so texture × COLOR_0 averages back to the
vertex colour. Leaf, bark and ground textures are therefore stored as grey
"detail" maps with mean 0.8, which lets one oak-leaf texture serve summer green,
fall red and spring lime alike.

Texture keys:
  leaf/<LeafSetNNN>    sprig of leaves composited from an ambientCG leaf atlas (alpha-masked)
  needle/<PineNeedlesNNN>  tuft of pine needle fascicles (alpha-masked)
  bark/<BarkNNN>       tileable bark detail (1 m tile)
  ground/<GroundNNN>   tileable forest-floor / pine-straw detail (2 m tile)
  model/<asset key>    an imported model's own colour map (registered by plandscape.models)
  .../procedural       offline fallback for any recipe, so scenes always build

Every texture reserves an opaque patch around SOLID_UV holding its mean colour, so
untextured parts of a textured mesh (flowers, Spanish moss) render as their vertex colour.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from .mesh import SOLID_UV  # noqa: F401  (centre of the reserved 1/8 × 1/8 top-left patch)
from .rng import rng as make_rng
DETAIL_MEAN = 0.8
TILE_M = {"bark": 1.0, "ground": 2.0}

# Leaf shapes chosen to resemble each species' leaf outline (lobed, star, heart, elliptic).
# They are photographs of other species; treat them as stand-ins, not botanical records.
LEAF_SET = {
    "live_oak": "LeafSet001", "water_oak": "LeafSet003", "white_oak": "LeafSet016",
    "sweetgum": "LeafSet010", "tulip_poplar": "LeafSet029", "southern_magnolia": "LeafSet022",
    "flowering_dogwood": "LeafSet018", "eastern_redbud": "LeafSet004",
}
DEFAULT_LEAF = "LeafSet024"
BARK_SET = {
    "live_oak": "Bark012", "white_oak": "Bark012", "water_oak": "Bark007", "loblolly_pine": "Bark014",
    "longleaf_pine": "Bark014", "bald_cypress": "Bark004", "southern_magnolia": "Bark001",
    "sweetgum": "Bark007", "tulip_poplar": "Bark006", "flowering_dogwood": "Bark002", "eastern_redbud": "Bark001",
    "sabal_palmetto": "Bark004",
}
NEEDLE_SET = "PineNeedles001"  # atlas of needle fascicles, used for pine foliage cards
GROUND_SET = {"pine_savanna": "Ground078", "pine_plantation": "Ground078", "hardwood": "ScatteredLeaves009",
              "swamp": "Ground048", "pasture": "Grass004", "lawn": "Grass004", "old_field": "Grass004"}


def leaf_key(species):
    return f"leaf/{LEAF_SET.get(species, DEFAULT_LEAF)}"


def needle_key():
    return f"needle/{NEEDLE_SET}"


def bark_key(species):
    return f"bark/{BARK_SET.get(species, 'Bark012')}"


def card_box(key, store=None):
    """(u0, v0, u1, v1, cover) of a card texture's opaque content; cover = opaque share of that box."""
    t = get(key, store)
    u0, v0, u1, v1 = t.meta.get("bbox", [0, 0, 1, 1])
    H, W = t.rgba.shape[:2]
    a = t.rgba[int(v0 * H):int(v1 * H), int(u0 * W):int(u1 * W), 3] > 127
    return u0, v0, u1, v1, float(a.mean()) if a.size else 0.5


def ground_key(biome):
    return f"ground/{GROUND_SET.get(biome, 'Ground078')}"


@dataclass
class Texture:
    key: str
    rgba: np.ndarray            # (H, W, 4) uint8
    mean: np.ndarray            # (3,) mean colour of opaque texels, 0..1
    alpha: bool                 # needs alpha masking
    data: bytes                 # encoded image for the GLB
    mime: str
    meta: dict = field(default_factory=dict)

    @staticmethod
    def from_rgba(key, rgba, meta=None, jpeg_quality=85):
        rgba = np.ascontiguousarray(rgba, np.uint8)
        a = rgba[..., 3] > 127
        alpha = not a.all()
        mean = rgba[..., :3][a].reshape(-1, 3).mean(0) / 255.0 if a.any() else np.full(3, 0.5)
        meta = dict(meta or {})
        if alpha:  # UV box of the opaque content, outside the reserved solid patch, so cards can be cropped
            H, W = a.shape
            aa = a.copy()
            aa[: H // 8, : W // 8] = False
            ys, xs = np.nonzero(aa)
            if len(xs):
                meta["bbox"] = [round(xs.min() / W, 4), round(ys.min() / H, 4),
                                round((xs.max() + 1) / W, 4), round((ys.max() + 1) / H, 4)]
        buf = io.BytesIO()
        if alpha:
            Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
            mime = "image/png"
        else:
            Image.fromarray(rgba[..., :3], "RGB").save(buf, "JPEG", quality=jpeg_quality, optimize=True)
            mime = "image/jpeg"
        return Texture(key, rgba, mean, alpha, buf.getvalue(), mime, meta)

    @staticmethod
    def from_bytes(key, data, mime, mean, meta=None):
        img = Image.open(io.BytesIO(bytes(data))).convert("RGBA")
        rgba = np.asarray(img, np.uint8)
        return Texture(key, rgba, np.asarray(mean, float), mime == "image/png", bytes(data), mime, dict(meta or {}))

    def sample(self, u, v):
        """Nearest-texel lookup with repeat wrapping; returns (..., 4) float 0..1."""
        H, W = self.rgba.shape[:2]
        x = (np.floor(np.mod(u, 1.0) * W).astype(int)) % W
        y = (np.floor(np.mod(v, 1.0) * H).astype(int)) % H
        return self.rgba[y, x].astype(np.float32) / 255.0


_REGISTRY: dict[str, Texture] = {}


def register(tex: Texture) -> Texture:
    _REGISTRY[tex.key] = tex
    return tex


def get(key: str, store=None) -> Texture | None:
    """Look up a texture, building it through the asset library on first use."""
    if key is None:
        return None
    if key in _REGISTRY:
        return _REGISTRY[key]
    kind, _, src = key.partition("/")
    if kind not in ("leaf", "needle", "bark", "ground"):
        return None  # model/* textures are registered when their model is decoded
    from .assets.store import AssetStore
    store = store or AssetStore()
    enc, dec = texture_codec()
    arrays, e = store.get("texture", dict(key=key))
    if arrays is not None:
        store.hits += 1
        tex = dec(arrays, e.meta)
    else:
        store.misses += 1
        tex = build(key)
        if "fallback" not in tex.meta:  # never cache a stand-in: a networked run must fetch the real one
            a, meta, _ = enc(tex)
            store.put("texture", dict(key=key), a, meta)
    tex.key = key
    return register(tex)


def build(key: str) -> Texture:
    kind, _, src = key.partition("/")
    rgba, meta = None, {}
    if src != "procedural":
        try:
            from .sources.sites import fetch_ambientcg
            maps = fetch_ambientcg(src)
            meta = dict(source=maps["_source"])
            if kind == "leaf":
                rgba = leaf_cluster(_leaf_sprites(maps["Color"], maps["Opacity"]), make_rng("leaf_cluster", src))
            elif kind == "needle":
                rgba = needle_tuft(_leaf_sprites(maps["Color"], maps["Opacity"]), make_rng("needle_tuft", src))
            else:
                rgba = detail(np.asarray(Image.open(maps["Color"]).convert("RGB")),
                              512 if kind == "bark" else 1024, contrast=1.0 if kind == "bark" else 0.7)
        except Exception as e:  # noqa: BLE001 - offline or blocked: fall back, and say so
            meta = dict(fallback=f"{type(e).__name__}: {str(e)[:160]}")
            rgba = None
    if rgba is None:
        r = make_rng("texture", key)
        if kind == "leaf":
            rgba = leaf_cluster(_procedural_sprites(r), r)
        elif kind == "needle":
            rgba = needle_tuft(_procedural_sprites(r, needle=True), r)
        else:
            rgba = _procedural_detail(kind, r)
        meta.setdefault("source", dict(site="procedural"))
    return Texture.from_rgba(key, rgba, meta)


def texture_codec():
    def enc(t: Texture):
        return ({"data": np.frombuffer(t.data, np.uint8)},
                dict(t.meta, mime=t.mime, mean=[round(float(x), 4) for x in t.mean], alpha=t.alpha,
                     size=list(t.rgba.shape[:2])), None)

    def dec(a, meta):  # the caller sets .key; the store keys entries by params, not by name
        return Texture.from_bytes("", a["data"].tobytes(), meta["mime"], meta["mean"], meta)
    return enc, dec


# ── recipes ─────────────────────────────────────────────────────────────────

def _solid_patch(rgba, value):
    n = rgba.shape[0] // 8
    rgba[:n, :n, :3] = value
    rgba[:n, :n, 3] = 255
    return rgba


def detail(rgb: np.ndarray, size: int, contrast=1.0) -> np.ndarray:
    """Grey, tileable detail map with mean DETAIL_MEAN from a colour photo texture."""
    img = Image.fromarray(np.asarray(rgb, np.uint8)).resize((size, size), Image.LANCZOS)
    L = np.asarray(img, np.float32) @ np.array([0.299, 0.587, 0.114], np.float32) / 255.0
    L = DETAIL_MEAN + (L - L.mean()) * (DETAIL_MEAN / max(L.mean(), 1e-3)) * contrast
    g = (np.clip(L, 0, 1) * 255).astype(np.uint8)
    return np.dstack([g, g, g, np.full_like(g, 255)])


def _procedural_detail(kind, r):
    n = 512
    base = ndimage.gaussian_filter(r.uniform(0, 1, (n, n)), 2.0, mode="wrap")
    if kind == "bark":  # vertical furrows
        base = base + 0.8 * ndimage.gaussian_filter(r.uniform(0, 1, (n, n)), (24.0, 1.5), mode="wrap")
    base = (base - base.min()) / max(np.ptp(base), 1e-6)
    return detail(np.dstack([base * 255] * 3).astype(np.uint8), n, contrast=0.8)


def _leaf_sprites(color_path, opacity_path, size=1024):
    """Cut individual leaves out of an atlas: RGBA crops, petiole at the bottom."""
    C = np.asarray(Image.open(color_path).convert("RGB").resize((size, size), Image.LANCZOS))
    A = np.asarray(Image.open(opacity_path).convert("L").resize((size, size), Image.LANCZOS))
    lab, n = ndimage.label(A > 127)
    if n == 0:
        raise ValueError("no leaves in atlas")
    areas = ndimage.sum(np.ones_like(A), lab, np.arange(1, n + 1))
    sprites = []
    for k, sl in enumerate(ndimage.find_objects(lab)):
        if areas[k] < 0.25 * areas.max():
            continue
        m = lab[sl] == k + 1
        rgba = np.dstack([C[sl], np.where(m, A[sl], 0)]).astype(np.uint8)
        if rgba.shape[1] > rgba.shape[0] * 1.6:  # lying sideways (needle atlases): base left → bottom
            rgba = np.ascontiguousarray(np.rot90(rgba, 1))  # counter-clockwise: left column → bottom row
        sprites.append(rgba)
    return sprites


def _procedural_sprites(r, n=6, needle=False):
    out = []
    for _ in range(n):
        if needle:
            im = Image.new("RGBA", (40, 300), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            for k in range(3):
                d.line([20, 299, 20 + (k - 1) * int(r.uniform(4, 14)), 0], fill=(200, 200, 200, 255), width=3)
            out.append(np.asarray(im))
            continue
        w, h = 60, 140
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        g = int(r.uniform(150, 220))
        d.ellipse([4, 4, w - 4, h - 18], fill=(g, g, g, 255))
        d.line([w // 2, h - 20, w // 2, h - 1], fill=(90, 90, 90, 255), width=3)
        d.line([w // 2, 10, w // 2, h - 20], fill=(g - 40, g - 40, g - 40, 255), width=2)
        out.append(np.asarray(im))
    return out


def _to_detail(canvas: Image.Image) -> np.ndarray:
    # shrink the content into the area below the top 1/8 strip, so a card's crop box can
    # never include the reserved solid patch
    n = canvas.size[0]
    inner = canvas.resize((n * 7 // 8, n * 7 // 8), Image.LANCZOS)
    canvas = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    canvas.alpha_composite(inner, (n // 16, n // 8))
    rgba = np.asarray(canvas).astype(np.float32)
    a = rgba[..., 3] > 127
    L = rgba[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32) / 255.0
    m = L[a].mean() if a.any() else 0.5
    g = np.clip(DETAIL_MEAN + (L - m) * (DETAIL_MEAN / max(m, 1e-3)), 0, 1)
    g = np.where(a, g, DETAIL_MEAN)  # no dark fringes when filtering into transparent texels
    out = np.dstack([g, g, g]) * 255
    out = np.dstack([out, np.where(a, 255, 0)]).astype(np.uint8)
    return _solid_patch(out, int(DETAIL_MEAN * 255))


def _place(canvas, sprite, at, length, angle_deg, width_scale=1.0):
    """Paste a sprite with its base (bottom-centre) at `at`, rotated clockwise by angle_deg."""
    h, w = sprite.shape[:2]
    sc = length / h
    leaf = Image.fromarray(sprite, "RGBA").resize((max(2, int(w * sc * width_scale)), max(2, int(length))),
                                                  Image.LANCZOS)
    pad = int(length) + 4
    holder = Image.new("RGBA", (2 * pad, 2 * pad), (0, 0, 0, 0))
    holder.alpha_composite(leaf, (pad - leaf.width // 2, pad - leaf.height))
    holder = holder.rotate(-angle_deg, resample=Image.BICUBIC, center=(pad, pad))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(holder, (int(at[0]) - pad, int(at[1]) - pad), holder)
    return Image.alpha_composite(canvas, layer)


def needle_tuft(sprites, r, size=512, n=26) -> np.ndarray:
    """A pine shoot's brush of needle fascicles fanning out from one point, as an alpha card."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base = np.array([size * 0.5, size * 0.97])
    ImageDraw.Draw(canvas).line([tuple(base), (size * 0.5, size * 0.55)], fill=(80, 70, 60, 255), width=size // 64)
    for k in range(n):
        t = k / max(n - 1, 1)
        at = base + [r.normal(0, size * 0.01), -size * (0.05 + 0.4 * t)]
        ang = r.uniform(-75, 75) * (1 - 0.5 * t)
        canvas = _place(canvas, sprites[int(r.integers(0, len(sprites)))], at, size * r.uniform(0.38, 0.5), ang,
                        width_scale=1.6)
    return _to_detail(canvas)


def leaf_cluster(sprites, r, size=512, n_leaves=15) -> np.ndarray:
    """Composite leaves along a twig into one alpha-masked card, converted to grey detail."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    base = np.array([size * 0.5, size * 0.98])
    tip = np.array([size * r.uniform(0.42, 0.58), size * 0.14])
    bow = r.uniform(-0.08, 0.08) * size
    ts = np.linspace(0, 1, 24)
    twig = base[None] * (1 - ts[:, None]) + tip[None] * ts[:, None]
    twig[:, 0] += bow * np.sin(np.pi * ts)
    d.line([tuple(p) for p in twig], fill=(70, 62, 55, 255), width=max(2, size // 110))
    order = []
    for k in range(n_leaves):
        t = 0.18 + 0.8 * k / max(n_leaves - 1, 1)
        side = 1 if k % 2 else -1
        if k == n_leaves - 1:
            side, t = 0, 1.0
        order.append((t, side))
    for t, side in order:
        i = min(int(t * (len(ts) - 1)), len(ts) - 1)
        L = size * r.uniform(0.27, 0.34) * (1.0 - 0.3 * t)
        ang = (r.normal(0, 8) if side == 0 else side * r.uniform(50, 85)) + r.normal(0, 6)
        canvas = _place(canvas, sprites[int(r.integers(0, len(sprites)))], twig[i], L, ang)
    return _to_detail(canvas)

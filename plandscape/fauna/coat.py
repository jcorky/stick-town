"""Surface kinds for the viewer's coat shader (TECHNIQUES §37): what a body's skin is made of, per vertex.

Each sculpted part carries a glTF attribute _COAT (normalised u8 vec4):

    x = kind / 8        kind ∈ {0 bare (skin, eye, hoof, cloth), 1 fur, 2 feather, 3 shell / scales,
                                4 fur lying along the part's z (legs: hair runs down the limb, not back),
                                5 smooth plumage (feathers at 40 % contrast: a heron, not a turkey)}
    y = s / S_MAX       feature size s (m): hair-strand spacing, feather length, scute or scale size
    z = sheen           rim brightening of fur and feather at grazing view, 0..1
    w = iridescence     view-dependent structural colour (a gobbler's bronze-green-copper), 0..1

The viewer (viewer/coat.js) draws these as albedo detail finer than any mesh the triangle budget allows. A row
of zeros means "not yet set": rig() fills those with the species default; an explicit bare vertex is
(0, 255, 0, 0). Vertices darker than DARK_LUM (eyes, noses, hooves, claws) stay bare.
"""

from __future__ import annotations

import numpy as np

KIND = {"bare": 0, "fur": 1, "feather": 2, "shell": 3, "fur_z": 4, "feather_soft": 5}
S_MAX = 0.05
DARK_LUM = 0.1

# design values: strand spacing and feather size read off close photographs, sheen and iridescence by eye
SURFACE = {
    "white_tailed_deer": ("fur", 0.004, 0.35, 0.0),
    "coyote": ("fur", 0.006, 0.3, 0.0),
    "raccoon": ("fur", 0.006, 0.3, 0.0),
    "gray_squirrel": ("fur", 0.003, 0.35, 0.0),
    "armadillo": ("shell", 0.012, 0.15, 0.0),
    "box_turtle": ("shell", 0.008, 0.1, 0.0),
    "great_blue_heron": ("feather_soft", 0.03, 0.25, 0.0),
    ("wild_turkey", "m"): ("feather", 0.035, 0.2, 0.9),
    ("wild_turkey", "f"): ("feather", 0.03, 0.15, 0.25),
}
BIRD_LEG = ("shell", 0.004, 0.1, 0.0)    # the scutes of a bird's tarsus


def encode(n, kind, size=0.004, sheen=0.0, irid=0.0):
    k = KIND[kind]
    row = [k * 32, 255 if k == 0 else int(np.clip(size / S_MAX * 255, 1, 255)), int(sheen * 255), int(irid * 255)]
    return np.tile(np.array(row, np.uint8), (n, 1))


def coat(m, kind, size=0.004, sheen=0.0, irid=0.0, mask=None):
    """Set m's _COAT: `kind` where `mask` (bool per vertex, default all) and the colour is not dark, bare elsewhere."""
    n = len(m.positions)
    A = encode(n, kind, size, sheen, irid)
    lit = (m.colors @ np.array([0.3, 0.59, 0.11])) >= DARK_LUM
    keep = lit if mask is None else lit & np.asarray(mask, bool)
    A[~keep] = encode(1, "bare")[0]
    m.attrs = dict(m.attrs or {}, _COAT=A)
    return m


def fill(m, kind, size=0.004, sheen=0.0, irid=0.0):
    """Give the not-yet-set vertices of m (zero rows, or no attribute at all) this surface."""
    if m is None or not len(m.positions):
        return m
    cur = (m.attrs or {}).get("_COAT")
    if cur is None:
        return coat(m, kind, size, sheen, irid)
    unset = ~cur.any(1)
    if unset.any():
        tmp = coat(type(m)(m.positions[unset], m.colors[unset], np.zeros((0, 3), np.uint32)), kind, size, sheen, irid)
        cur = cur.copy()
        cur[unset] = tmp.attrs["_COAT"]
        m.attrs = dict(m.attrs, _COAT=cur)
    return m

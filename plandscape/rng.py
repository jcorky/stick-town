"""Hierarchical, order-independent seeding.

Every random decision is keyed by *what* it is for, not *when* it happens:

    rng(world_seed, "tree", species, instance_id)

so generating trees in a different order, or adding a new layer, never
changes anything that already existed. This is what makes "infinite but
reproducible" variation possible: the space of keys is unbounded.
"""

from __future__ import annotations

import hashlib

import numpy as np


def derive_seed(*keys) -> int:
    h = hashlib.blake2b(digest_size=8)
    for k in keys:
        h.update(repr(k).encode("utf-8"))
        h.update(b"\x1f")
    return int.from_bytes(h.digest(), "little")


def rng(*keys) -> np.random.Generator:
    return np.random.default_rng(derive_seed(*keys))

"""Minimal triangle-mesh container shared by every generator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Mesh:
    positions: np.ndarray  # (N,3) float32, world z-up
    colors: np.ndarray     # (N,3) float32 linear-ish RGB 0..1
    indices: np.ndarray    # (M,3) uint32

    @staticmethod
    def empty() -> "Mesh":
        return Mesh(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32),
                    np.zeros((0, 3), np.uint32))

    @property
    def n_tris(self) -> int:
        return int(len(self.indices))

    def normals(self) -> np.ndarray:
        p = self.positions.astype(np.float64)
        n = np.zeros_like(p)
        if len(self.indices):
            a, b, c = (p[self.indices[:, k]] for k in range(3))
            fn = np.cross(b - a, c - a)
            for k in range(3):
                np.add.at(n, self.indices[:, k], fn)
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        n = np.where(ln > 1e-12, n / np.maximum(ln, 1e-12), np.array([0.0, 0.0, 1.0]))
        return n.astype(np.float32)

    def transformed(self, M: np.ndarray) -> "Mesh":
        p = np.c_[self.positions, np.ones(len(self.positions))] @ M.T
        return Mesh(p[:, :3].astype(np.float32), self.colors, self.indices)

    @staticmethod
    def merge(meshes) -> "Mesh":
        meshes = [m for m in meshes if m is not None and len(m.positions)]
        if not meshes:
            return Mesh.empty()
        off, idx = 0, []
        for m in meshes:
            idx.append(m.indices + off)
            off += len(m.positions)
        return Mesh(np.concatenate([m.positions for m in meshes]).astype(np.float32),
                    np.concatenate([m.colors for m in meshes]).astype(np.float32),
                    np.concatenate(idx).astype(np.uint32))


class MeshBuilder:
    """Append-only builder; cheaper than merging thousands of tiny Mesh objects."""

    def __init__(self):
        self.p, self.c, self.i = [], [], []
        self.n = 0

    def add(self, positions, colors, indices):
        positions = np.asarray(positions, np.float32)
        colors = np.broadcast_to(np.asarray(colors, np.float32), positions.shape)
        self.p.append(positions)
        self.c.append(np.array(colors))
        self.i.append(np.asarray(indices, np.uint32) + self.n)
        self.n += len(positions)

    def build(self) -> Mesh:
        if not self.p:
            return Mesh.empty()
        return Mesh(np.concatenate(self.p), np.concatenate(self.c), np.concatenate(self.i))


def box(center, size, color, rot_z=0.0) -> Mesh:
    cx, cy, cz = center
    sx, sy, sz = (s / 2 for s in size)
    v = np.array([[x, y, z] for z in (-sz, sz) for y in (-sy, sy) for x in (-sx, sx)], float)
    c, s = np.cos(rot_z), np.sin(rot_z)
    v = v @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]]) + [cx, cy, cz]
    f = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
         (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]
    # duplicate verts per face for flat shading
    pos, idx = [], []
    for k, (a, b, d) in enumerate(f):
        pos += [v[a], v[b], v[d]]
        idx.append((3 * k, 3 * k + 1, 3 * k + 2))
    return Mesh(np.array(pos, np.float32), np.tile(np.asarray(color, np.float32), (len(pos), 1)),
                np.array(idx, np.uint32))

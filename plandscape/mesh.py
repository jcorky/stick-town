"""Minimal triangle-mesh container shared by every generator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Every texture keeps an opaque patch of its mean colour here (see plandscape.textures), so
# untextured parts of a textured mesh render as their plain vertex colour.
SOLID_UV = (1 / 16, 1 / 16)


@dataclass
class Mesh:
    positions: np.ndarray  # (N,3) float32, world z-up
    colors: np.ndarray     # (N,3) float32 linear-ish RGB 0..1
    indices: np.ndarray    # (M,3) uint32
    uvs: np.ndarray | None = None  # (N,2) float32 texture coordinates, v down (glTF convention)
    texture: str | None = None     # key into plandscape.textures; colours stay the final look
    weights: np.ndarray | None = None  # (N,4) splat weights for height-blended ground (sum to 1)
    splat: tuple | None = None         # 4 texture keys the weights refer to
    nrm: np.ndarray | None = None      # (N,3) authored normals (e.g. rounded crown normals); else geometric

    @staticmethod
    def empty() -> "Mesh":
        return Mesh(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32),
                    np.zeros((0, 3), np.uint32))

    @property
    def n_tris(self) -> int:
        return int(len(self.indices))

    def normals(self) -> np.ndarray:
        if self.nrm is not None:
            return np.asarray(self.nrm, np.float32)
        return self.geometric_normals()

    def geometric_normals(self) -> np.ndarray:
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
        nrm = None
        if self.nrm is not None:
            R = M[:3, :3]
            nrm = self.nrm @ R.T
            nrm = (nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)).astype(np.float32)
        return Mesh(p[:, :3].astype(np.float32), self.colors, self.indices, self.uvs, self.texture,
                    self.weights, self.splat, nrm)

    @staticmethod
    def merge(meshes) -> "Mesh":
        """Concatenate meshes. UVs survive only when every part has them and all share one
        texture; otherwise the result is untextured (vertex colours still carry the look)."""
        meshes = [m for m in meshes if m is not None and len(m.positions)]
        if not meshes:
            return Mesh.empty()
        off, idx = 0, []
        for m in meshes:
            idx.append(m.indices + off)
            off += len(m.positions)
        tex = {m.texture for m in meshes}
        keep_uv = len(tex) == 1 and all(m.uvs is not None for m in meshes)
        return Mesh(np.concatenate([m.positions for m in meshes]).astype(np.float32),
                    np.concatenate([m.colors for m in meshes]).astype(np.float32),
                    np.concatenate(idx).astype(np.uint32),
                    np.concatenate([m.uvs for m in meshes]).astype(np.float32) if keep_uv else None,
                    meshes[0].texture if keep_uv else None)


class MeshBuilder:
    """Append-only builder; cheaper than merging thousands of tiny Mesh objects."""

    def __init__(self, texture: str | None = None):
        self.p, self.c, self.i, self.u = [], [], [], []
        self.n = 0
        self.texture = texture

    def add(self, positions, colors, indices, uvs=None):
        positions = np.asarray(positions, np.float32)
        colors = np.broadcast_to(np.asarray(colors, np.float32), positions.shape)
        self.p.append(positions)
        self.c.append(np.array(colors))
        self.i.append(np.asarray(indices, np.uint32) + self.n)
        self.u.append(None if uvs is None else np.broadcast_to(np.asarray(uvs, np.float32), (len(positions), 2)))
        self.n += len(positions)

    def build(self) -> Mesh:
        if not self.p:
            return Mesh.empty()
        uv = None
        if self.texture and any(u is not None for u in self.u):
            # parts added without UVs sample the texture's solid patch, i.e. show their vertex colour
            uv = np.concatenate([u if u is not None else np.tile(np.float32(SOLID_UV), (len(p), 1))
                                 for u, p in zip(self.u, self.p)])
        return Mesh(np.concatenate(self.p), np.concatenate(self.c), np.concatenate(self.i),
                    uv, self.texture if uv is not None else None)


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

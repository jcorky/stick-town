"""Minimal GLB 2.0 writer (no dependencies).

Supports: meshes with POSITION / NORMAL / COLOR_0, per-mesh materials,
nodes with TRS that reuse meshes (cheap instancing of tree variants), and
linear translation/rotation animations (for animals and people).

World frame is z-up (x east, y north); glTF is y-up. `_to_gltf` converts
(x, y, z) → (x, z, -y), a proper rotation, so winding is preserved.
"""

from __future__ import annotations

import json
import struct

import numpy as np

ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
FLOAT, BYTE, UBYTE, UINT = 5126, 5120, 5121, 5125


def _to_gltf(v):
    v = np.asarray(v, np.float32)
    return np.stack([v[..., 0], v[..., 2], -v[..., 1]], -1)


def yaw_quat(theta):
    """Quaternion (x,y,z,w) for a world-z heading θ, expressed in glTF space."""
    theta = np.asarray(theta, np.float64)
    return np.stack([np.zeros_like(theta), np.sin(theta / 2), np.zeros_like(theta), np.cos(theta / 2)], -1)


class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.views, self.accessors, self.meshes, self.materials, self.nodes = [], [], [], [], []
        self.animations = []
        self.mat_index = {}

    def _view(self, data: bytes, target=None, stride=None):
        while len(self.bin) % 4:
            self.bin += b"\0"
        off = len(self.bin)
        self.bin += data
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target:
            v["target"] = target
        if stride:
            v["byteStride"] = stride
        self.views.append(v)
        return len(self.views) - 1

    def _acc(self, arr, ctype, typ, target=None, normalized=False, minmax=False, stride=None):
        view = self._view(arr.tobytes(), target, stride)
        a = {"bufferView": view, "componentType": ctype, "count": int(arr.shape[0]), "type": typ}
        if normalized:
            a["normalized"] = True
        if minmax:
            a["min"] = arr.min(0).tolist() if arr.ndim > 1 else [float(arr.min())]
            a["max"] = arr.max(0).tolist() if arr.ndim > 1 else [float(arr.max())]
        self.accessors.append(a)
        return len(self.accessors) - 1

    def material(self, name, double=False, rough=0.9, metal=0.0, alpha=1.0):
        if name in self.mat_index:
            return self.mat_index[name]
        m = {"name": name, "doubleSided": double,
             "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, alpha], "metallicFactor": metal, "roughnessFactor": rough}}
        if alpha < 1:
            m["alphaMode"] = "BLEND"
        self.materials.append(m)
        self.mat_index[name] = len(self.materials) - 1
        return self.mat_index[name]

    def mesh(self, mesh, name, material):
        if mesh.n_tris == 0:
            return None
        P = _to_gltf(mesh.positions)
        # normals quantised to int8 (KHR_mesh_quantization): 4 bytes/vertex instead of 12
        N8 = np.zeros((len(P), 4), np.int8)
        N8[:, :3] = np.round(_to_gltf(mesh.normals()) * 127).astype(np.int8)
        C = np.c_[np.clip(mesh.colors, 0, 1) * 255, np.full(len(P), 255)].astype(np.uint8)
        attrs = {"POSITION": self._acc(P, FLOAT, "VEC3", ARRAY_BUFFER, minmax=True),
                 "NORMAL": self._acc(N8, BYTE, "VEC3", ARRAY_BUFFER, normalized=True, stride=4),
                 "COLOR_0": self._acc(C, UBYTE, "VEC4", ARRAY_BUFFER, normalized=True)}
        idx = self._acc(mesh.indices.astype(np.uint32).ravel(), UINT, "SCALAR", ELEMENT_ARRAY_BUFFER)
        self.meshes.append({"name": name, "primitives": [{"attributes": attrs, "indices": idx, "material": material}]})
        return len(self.meshes) - 1

    def node(self, name, mesh=None, translation=None, rotation_z=0.0, scale=1.0, children=None, world=True):
        n = {"name": name}
        if mesh is not None:
            n["mesh"] = mesh
        if translation is not None:
            n["translation"] = (_to_gltf(translation) if world else np.asarray(translation)).tolist()
        if rotation_z:
            n["rotation"] = yaw_quat(rotation_z).tolist()
        if scale != 1.0:
            n["scale"] = [float(scale)] * 3
        if children:
            n["children"] = children
        self.nodes.append(n)
        return len(self.nodes) - 1

    def animate(self, name, tracks):
        """tracks: list of (node_index, times(T,), positions_world(T,3), headings(T,))."""
        samplers, channels = [], []
        for node, t, p, h in tracks:
            ti = self._acc(np.asarray(t, np.float32), FLOAT, "SCALAR", minmax=True)
            pi = self._acc(_to_gltf(p).astype(np.float32), FLOAT, "VEC3")
            q = yaw_quat(np.unwrap(np.asarray(h))).astype(np.float32)
            qi = self._acc(q, FLOAT, "VEC4")
            samplers += [{"input": ti, "output": pi, "interpolation": "LINEAR"},
                         {"input": ti, "output": qi, "interpolation": "LINEAR"}]
            channels += [{"sampler": len(samplers) - 2, "target": {"node": node, "path": "translation"}},
                         {"sampler": len(samplers) - 1, "target": {"node": node, "path": "rotation"}}]
        if channels:
            self.animations.append({"name": name, "samplers": samplers, "channels": channels})

    def save(self, path, extras=None):
        roots = [i for i in range(len(self.nodes)) if not any(i in n.get("children", []) for n in self.nodes)]
        doc = {"asset": {"version": "2.0", "generator": "plandscape"},
               "scene": 0, "scenes": [{"nodes": roots, "extras": extras or {}}],
               "nodes": self.nodes, "meshes": self.meshes, "materials": self.materials,
               "accessors": self.accessors, "bufferViews": self.views,
               "buffers": [{"byteLength": len(self.bin)}]}
        if self.animations:
            doc["animations"] = self.animations
        doc["extensionsUsed"] = doc["extensionsRequired"] = ["KHR_mesh_quantization"]
        js = json.dumps(doc, separators=(",", ":")).encode()
        js += b" " * ((4 - len(js) % 4) % 4)
        binb = bytes(self.bin) + b"\0" * ((4 - len(self.bin) % 4) % 4)
        total = 12 + 8 + len(js) + 8 + len(binb)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
            f.write(struct.pack("<II", len(binb), 0x004E4942) + binb)
        return path

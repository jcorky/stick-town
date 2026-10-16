"""Minimal GLB 2.0 writer (no dependencies).

Supports: meshes with POSITION / NORMAL / COLOR_0 / TEXCOORD_0, per-mesh materials
(optionally with an embedded base-colour texture, alpha-masked for leaf cards),
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
FLOAT, BYTE, UBYTE, USHORT, UINT = 5126, 5120, 5121, 5123, 5125
REPEAT, LINEAR, LINEAR_MIPMAP_LINEAR = 10497, 9729, 9987
UV_TILE = 64.0  # tiling textures (bark, ground): UVs stored ÷64 as uint16, KHR_texture_transform scales back


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
        self.images, self.textures, self.samplers = [], [], []
        self.tex_index = {}
        self.mat_tint = {}  # material → texture mean; COLOR_0 is divided by it
        self.mat_uvscale = {}  # material → UV_TILE for tiling textures
        self.ext_used = {"KHR_mesh_quantization"}

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

    def texture(self, tex):
        """Embed a plandscape.textures.Texture once; returns its glTF texture index."""
        if tex.key in self.tex_index:
            return self.tex_index[tex.key]
        if not self.samplers:
            self.samplers.append({"magFilter": LINEAR, "minFilter": LINEAR_MIPMAP_LINEAR, "wrapS": REPEAT, "wrapT": REPEAT})
        self.images.append({"name": tex.key, "bufferView": self._view(tex.data), "mimeType": tex.mime})
        self.textures.append({"source": len(self.images) - 1, "sampler": 0})
        self.tex_index[tex.key] = len(self.textures) - 1
        return self.tex_index[tex.key]

    def material(self, name, double=False, rough=0.9, metal=0.0, alpha=1.0, texture=None):
        """`texture` (a Texture) adds a base-colour map; one with an alpha channel is alpha-masked."""
        if name in self.mat_index:
            return self.mat_index[name]
        m = {"name": name, "doubleSided": double,
             "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, alpha], "metallicFactor": metal, "roughnessFactor": rough}}
        if alpha < 1:
            m["alphaMode"] = "BLEND"
        if texture is not None:
            ti = {"index": self.texture(texture)}
            if texture.key.split("/")[0] in ("bark", "ground"):
                ti["extensions"] = {"KHR_texture_transform": {"scale": [UV_TILE, UV_TILE]}}
                self.ext_used.add("KHR_texture_transform")
            m["pbrMetallicRoughness"]["baseColorTexture"] = ti
            if texture.alpha:
                m["alphaMode"], m["alphaCutoff"] = "MASK", 0.5
        self.materials.append(m)
        self.mat_index[name] = len(self.materials) - 1
        if texture is not None:
            self.mat_tint[self.mat_index[name]] = np.asarray(texture.mean, np.float32)
            if "extensions" in ti:
                self.mat_uvscale[self.mat_index[name]] = UV_TILE
        return self.mat_index[name]

    def mesh(self, mesh, name, material):
        if mesh.n_tris == 0:
            return None
        P = _to_gltf(mesh.positions)
        tint = self.mat_tint.get(material)
        textured = tint is not None and mesh.uvs is not None
        # normals quantised to int8 (KHR_mesh_quantization): 4 bytes/vertex instead of 12
        N8 = np.zeros((len(P), 4), np.int8)
        N8[:, :3] = np.round(_to_gltf(mesh.normals()) * 127).astype(np.int8)
        col = mesh.colors / np.maximum(tint, 1e-3) if textured else mesh.colors  # texture × COLOR_0 ≈ colour
        C = np.c_[np.clip(col, 0, 1) * 255, np.full(len(P), 255)].astype(np.uint8)
        attrs = {"POSITION": self._acc(P, FLOAT, "VEC3", ARRAY_BUFFER, minmax=True),
                 "NORMAL": self._acc(N8, BYTE, "VEC3", ARRAY_BUFFER, normalized=True, stride=4),
                 "COLOR_0": self._acc(C, UBYTE, "VEC4", ARRAY_BUFFER, normalized=True)}
        if textured:
            uv = np.asarray(mesh.uvs, np.float64)
            k = self.mat_uvscale.get(material)
            if k:  # repeating texture: shift by whole tiles (invisible), then ÷k so it fits uint16
                uv = (uv - np.floor(uv.min(0))) / k
            uv = uv.astype(np.float32)
            if uv.min() >= 0 and uv.max() <= 1:  # quantised (KHR_mesh_quantization): 4 bytes instead of 8
                attrs["TEXCOORD_0"] = self._acc(np.round(uv * 65535).astype(np.uint16), USHORT, "VEC2",
                                                ARRAY_BUFFER, normalized=True)
            else:  # tiling UVs (bark, ground) need repeats beyond 0..1
                attrs["TEXCOORD_0"] = self._acc(uv, FLOAT, "VEC2", ARRAY_BUFFER)
        if len(P) < 65536:  # 16-bit indices halve index data for all but the largest meshes
            idx = self._acc(mesh.indices.astype(np.uint16).ravel(), USHORT, "SCALAR", ELEMENT_ARRAY_BUFFER)
        else:
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
        if self.images:
            doc["images"], doc["textures"], doc["samplers"] = self.images, self.textures, self.samplers
        doc["extensionsUsed"] = sorted(self.ext_used)
        doc["extensionsRequired"] = ["KHR_mesh_quantization"]
        js = json.dumps(doc, separators=(",", ":")).encode()
        js += b" " * ((4 - len(js) % 4) % 4)
        binb = bytes(self.bin) + b"\0" * ((4 - len(self.bin) % 4) % 4)
        total = 12 + 8 + len(js) + 8 + len(binb)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
            f.write(struct.pack("<II", len(binb), 0x004E4942) + binb)
        return path

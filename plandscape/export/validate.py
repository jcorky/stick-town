"""Structural GLB checks (no external validator available offline).

Catches the mistakes that make viewers silently show nothing: views out of
bounds, misaligned offsets, accessors overrunning their views, indices past
the vertex count, bad animation inputs.
"""

from __future__ import annotations

import json
import struct

import numpy as np

SIZES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
COMPS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
DT = {5120: np.int8, 5121: np.uint8, 5125: np.uint32, 5126: np.float32}


def validate_glb(path):
    errs = []
    data = open(path, "rb").read()
    magic, ver, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or ver != 2 or total != len(data):
        return [f"bad header magic={magic:x} ver={ver} total={total} len={len(data)}"]
    jl, jt = struct.unpack_from("<II", data, 12)
    doc = json.loads(data[20:20 + jl])
    bl, bt = struct.unpack_from("<II", data, 20 + jl)
    binb = data[28 + jl:28 + jl + bl]
    if bt != 0x004E4942:
        errs.append("missing BIN chunk")
    for i, v in enumerate(doc["bufferViews"]):
        if v["byteOffset"] % 4:
            errs.append(f"view {i} misaligned")
        if v["byteOffset"] + v["byteLength"] > len(binb):
            errs.append(f"view {i} out of bounds")

    def read(ai):
        a = doc["accessors"][ai]
        v = doc["bufferViews"][a["bufferView"]]
        n = COMPS[a["type"]]
        es = SIZES[a["componentType"]] * n
        stride = v.get("byteStride", es)
        need = stride * (a["count"] - 1) + es
        if need > v["byteLength"]:
            errs.append(f"accessor {ai} overruns its view ({need} > {v['byteLength']})")
            return None
        raw = np.frombuffer(binb, DT[a["componentType"]], count=(stride // SIZES[a["componentType"]]) * a["count"],
                            offset=v["byteOffset"]).reshape(a["count"], -1)
        return raw[:, :n]

    for mi, m in enumerate(doc["meshes"]):
        for p in m["primitives"]:
            pos = read(p["attributes"]["POSITION"])
            idx = read(p["indices"])
            if pos is None or idx is None:
                continue
            if not np.isfinite(pos).all():
                errs.append(f"mesh {mi} has non-finite positions")
            if idx.size and idx.max() >= len(pos):
                errs.append(f"mesh {mi} index {idx.max()} >= {len(pos)} vertices")
            for k, ai in p["attributes"].items():
                if doc["accessors"][ai]["count"] != len(pos):
                    errs.append(f"mesh {mi} attribute {k} count mismatch")
    for an in doc.get("animations", []):
        for s in an["samplers"]:
            t = read(s["input"])
            if t is not None and (np.diff(t.ravel()) <= 0).any():
                errs.append(f"animation '{an['name']}' input times not strictly increasing")
    return errs

"""Licence-gated downloads from asset sites (Poly Haven, ambientCG).

  python -m plandscape.sources.sites probe     # read each site's licence page → catalog/asset_sites.json

Same rule as the repo harvester: a licence is read from the source, never
remembered. `fetch_*` refuse to download from a site whose probe did not find a
permissive licence. Raw downloads go to a local cache (.cache/downloads, git-ignored);
only the processed, budget-sized results enter the asset library.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import time
import urllib.request
import zipfile

from .harvest import PERMISSIVE, ROOT, SIGNATURES

SITES_FILE = os.path.join(ROOT, "catalog", "asset_sites.json")
DOWNLOADS = os.environ.get("PLANDSCAPE_DOWNLOADS", os.path.join(ROOT, ".cache", "downloads"))
UA = {"User-Agent": "plandscape/0.2 (+https://github.com/jcorky/stick-town)"}

SITES = {
    "polyhaven": dict(licence_page="https://polyhaven.com/license", home="https://polyhaven.com"),
    "ambientcg": dict(licence_page="https://docs.ambientcg.com/license/", home="https://ambientcg.com"),
}


def _get(url, timeout=60) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as f:
        return f.read()


def probe():
    """Fetch each licence page, detect the licence and keep a short quote as evidence."""
    out = {}
    for key, s in SITES.items():
        try:
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _get(s["licence_page"]).decode("utf-8", "replace")))
        except Exception as e:  # noqa: BLE001 - recorded, never fatal
            out[key] = dict(s, licence=None, error=str(e)[:200])
            continue
        lic, quote = None, ""
        for name, pat in SIGNATURES:
            m = re.search(pat, text, re.I)
            if m:
                lic = name
                quote = text[max(0, m.start() - 160): m.end() + 160].strip()
                break
        if lic is None and re.search(r"\bCC0\b", text):
            m = re.search(r"\bCC0\b", text)
            lic, quote = "CC0-1.0", text[max(0, m.start() - 160): m.end() + 160].strip()
        out[key] = dict(s, licence=lic, permissive=lic in PERMISSIVE, evidence=quote,
                        probed=time.strftime("%Y-%m-%d"))
    os.makedirs(os.path.dirname(SITES_FILE), exist_ok=True)
    with open(SITES_FILE, "w") as f:
        json.dump(out, f, indent=1)
    return out


def licence(site: str) -> dict:
    """The probed licence record for a site; raises if it is missing or not permissive."""
    try:
        with open(SITES_FILE) as f:
            rec = json.load(f).get(site)
    except FileNotFoundError:
        rec = None
    if not rec or not rec.get("permissive"):
        raise PermissionError(f"{site}: no permissive licence on record; run `python -m plandscape.sources.sites probe`")
    return rec


def _cached(path, url):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = _get(url, timeout=300)
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return path


def fetch_ambientcg(asset_id: str, res: str = "1K-JPG") -> dict:
    """Download (once) an ambientCG material zip; returns {map_name: path, '_source': {...}}."""
    rec = licence("ambientcg")
    if not re.fullmatch(r"[A-Za-z0-9_]+", asset_id):
        raise ValueError(asset_id)
    z = _cached(os.path.join(DOWNLOADS, "ambientcg", f"{asset_id}_{res}.zip"),
                f"https://ambientcg.com/get?file={asset_id}_{res}.zip")
    d = z[:-4]
    if not os.path.isdir(d):
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():  # flat archive; never trust member paths
                if n.lower().endswith((".jpg", ".png")) and "/" not in n and ".." not in n:
                    zf.extract(n, d)
    maps = {}
    for n in os.listdir(d):
        m = re.match(rf"{asset_id}_{res}_(\w+)\.(jpg|png)$", n)
        if m:
            maps[m.group(1)] = os.path.join(d, n)
    maps["_source"] = dict(site="ambientcg", id=asset_id, url=f"https://ambientcg.com/a/{asset_id}",
                           licence=rec["licence"], licence_page=rec["licence_page"])
    return maps


def fetch_polyhaven_model(asset_id: str, res: str = "1k") -> dict:
    """Download (once) a Poly Haven model as glTF + its textures; returns {'gltf': path, '_source': {...}}."""
    rec = licence("polyhaven")
    if not re.fullmatch(r"[A-Za-z0-9_]+", asset_id):
        raise ValueError(asset_id)
    info = json.loads(_get(f"https://api.polyhaven.com/info/{asset_id}"))
    files = json.loads(_get(f"https://api.polyhaven.com/files/{asset_id}"))
    g = files["gltf"][res]["gltf"]
    d = os.path.join(DOWNLOADS, "polyhaven", f"{asset_id}_{res}")
    path = _cached(os.path.join(d, os.path.basename(g["url"])), g["url"])
    for rel, inc in g.get("include", {}).items():
        if ".." in rel or rel.startswith("/"):
            continue
        _cached(os.path.join(d, rel), inc["url"])
    alpha = None  # alpha-masked models (ferns, shrubs) keep their mask in a separate map
    am = files.get("Alpha", {}).get(res, {}).get("jpg")
    if am:
        alpha = _cached(os.path.join(d, "textures", f"{asset_id}_alpha_{res}.jpg"), am["url"])
    return dict(gltf=path, alpha=alpha, _source=dict(site="polyhaven", id=asset_id, url=f"https://polyhaven.com/a/{asset_id}",
                                        licence=rec["licence"], licence_page=rec["licence_page"],
                                        authors=sorted(info.get("authors", {})), polycount=info.get("polycount")))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plandscape.sources.sites")
    ap.add_argument("cmd", choices=["probe"])
    ap.parse_args(argv)
    print(json.dumps(probe(), indent=1))


if __name__ == "__main__":
    main()

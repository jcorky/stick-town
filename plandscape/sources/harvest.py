"""License-gated harvester for public procedural-generation repositories.

  python -m plandscape.sources.harvest probe          # read each repo's LICENSE without cloning it
  python -m plandscape.sources.harvest clone          # shallow-clone permissive repos into .cache/sources
  python -m plandscape.sources.harvest index          # technique index over cloned repos
  python -m plandscape.sources.harvest discover --topic procedural-generation   # GitHub search → candidates.json

Rules: only permissive licences get cloned for adaptation; copyleft repos are
marked study-only; discoveries go to catalog/candidates.json for a human to
approve and are never auto-cloned. Everything records the commit it saw.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CATALOG = os.path.join(ROOT, "catalog", "sources.json")
REPORT = os.path.join(ROOT, "catalog", "harvest_report.json")
CACHE = os.path.join(ROOT, ".cache", "sources")

PERMISSIVE = {"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "Zlib", "CC0-1.0", "Unlicense", "MPL-2.0", "ISC"}

SIGNATURES = [
    ("CC-BY-NC-4.0", r"Attribution-NonCommercial"),
    ("Apache-2.0", r"Apache License,?\s+Version 2\.0"),
    ("GPL-3.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 3"),
    ("GPL-2.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 2"),
    ("LGPL", r"GNU LESSER GENERAL PUBLIC LICENSE"),
    ("AGPL-3.0", r"GNU AFFERO GENERAL PUBLIC LICENSE"),
    ("MPL-2.0", r"Mozilla Public License,? (Version|v\.) ?2\.0"),
    ("CC0-1.0", r"CC0 1\.0|Creative Commons Zero|No Copyright"),
    ("Unlicense", r"This is free and unencumbered software released into the public domain"),
    ("BSD-3-Clause", r"Neither the name of .{0,120} nor the names of"),
    ("BSD-2-Clause", r"Redistributions in binary form must reproduce"),
    ("Zlib", r"provided 'as-is'.{0,400}Permission is granted to anyone to use this software for any purpose"),
    ("ODbL-1.0", r"Open Data Commons Open Database License|ODbL"),
    ("MIT", r"Permission is hereby granted, free of charge"),
    ("ISC", r"Permission to use, copy, modify, and/or distribute this software for any purpose"),
]

TECHNIQUES = {
    "space_colonization": r"space.?coloni[sz]ation|attraction.?points",
    "l_system": r"l.?system|lindenmayer",
    "weber_penn": r"weber.{0,6}penn|sapling",
    "pipe_model": r"pipe.?model|da.?vinci",
    "wind": r"\bwind\b|sway",
    "erosion": r"erosion|hydraulic|thermal",
    "poisson_disk": r"poisson.?dis[ck]|blue.?noise",
    "boids_steering": r"boids|steering|separation.{0,20}cohesion",
    "navmesh": r"navmesh|detour|recast",
    "lod_impostor": r"impostor|billboard|\blod\b|clipmap",
    "grass": r"\bgrass\b|blade",
    "scatter": r"scatter|instanc",
    "wfc": r"wave.?function.?collapse|\bwfc\b",
}


def git(*args, cwd=None, timeout=300):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def detect_license(text: str) -> str:
    for spdx, pat in SIGNATURES:
        if re.search(pat, text, re.I | re.S):
            return spdx
    return "UNKNOWN"


def probe(entry) -> dict:
    """Fetch only the commit tree and the licence blob (no full clone)."""
    d = os.path.join(CACHE, "_probe", entry["id"])
    if not os.path.exists(d):
        r = git("clone", "--depth", "1", "--filter=blob:none", "--no-checkout", "-q", entry["url"], d)
        if r.returncode:
            return dict(id=entry["id"], ok=False, error=r.stderr.strip()[-300:])
    sha = git("rev-parse", "HEAD", cwd=d).stdout.strip()
    names = git("ls-tree", "--name-only", "HEAD", cwd=d).stdout.split()
    lic = [n for n in names if re.match(r"(?i)^(licen[cs]e|copying|unlicense)", n)]
    text = git("show", f"HEAD:{lic[0]}", cwd=d).stdout if lic else ""
    found = detect_license(text) if text else "NONE"
    expected = entry.get("license", "")
    perm = found in PERMISSIVE
    return dict(id=entry["id"], url=entry["url"], ok=True, commit=sha, license_file=lic[0] if lic else None,
                license_found=found, license_expected=expected,
                matches=bool(expected) and expected.split()[0].split("-")[0] == found.split("-")[0],
                permissive=perm, study_only=bool(entry.get("study_only")) or not perm)


def clone(entry, rep):
    if rep.get("study_only") or not rep.get("permissive"):
        return dict(id=entry["id"], cloned=False, reason="study-only or not permissive")
    d = os.path.join(CACHE, entry["id"])
    if not os.path.exists(d):
        r = git("clone", "--depth", "1", "-q", entry["url"], d, timeout=900)
        if r.returncode:
            return dict(id=entry["id"], cloned=False, reason=r.stderr.strip()[-300:])
    return dict(id=entry["id"], cloned=True, path=os.path.relpath(d, ROOT))


def index_repo(path):
    hits = {k: [] for k in TECHNIQUES}
    exts = {}
    for base, dirs, files in os.walk(path):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "build", "dist")]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            exts[ext] = exts.get(ext, 0) + 1
            if ext not in (".py", ".js", ".ts", ".c", ".cpp", ".h", ".hpp", ".cs", ".glsl", ".gd", ".rs", ".md"):
                continue
            p = os.path.join(base, f)
            try:
                txt = open(p, errors="ignore").read(400_000)
            except OSError:
                continue
            for k, pat in TECHNIQUES.items():
                if re.search(pat, txt, re.I):
                    hits[k].append(os.path.relpath(p, path))
    return dict(files=sum(exts.values()), top_ext=sorted(exts.items(), key=lambda kv: -kv[1])[:6],
                techniques={k: v[:25] for k, v in hits.items() if v})


def discover(topics, per_topic=30):
    """GitHub search (REST). Needs network access to api.github.com search; writes candidates only."""
    out = []
    for t in topics:
        q = f"topic:{t} stars:>50"
        r = subprocess.run(["gh", "api", "-X", "GET", "search/repositories", "-f", f"q={q}", "-f", "sort=stars",
                            "-f", f"per_page={per_topic}"], capture_output=True, text=True)
        if r.returncode:
            print(f"discover {t}: {r.stderr.strip()[:200]}", file=sys.stderr)
            continue
        for it in json.loads(r.stdout).get("items", []):
            lic = (it.get("license") or {}).get("spdx_id")
            out.append(dict(url=it["html_url"], stars=it["stargazers_count"], license=lic, topic=t,
                            description=it.get("description"), permissive=lic in PERMISSIVE))
    path = os.path.join(ROOT, "catalog", "candidates.json")
    json.dump(sorted(out, key=lambda x: -x["stars"]), open(path, "w"), indent=1)
    return path, len(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plandscape.sources.harvest")
    ap.add_argument("cmd", choices=["probe", "clone", "index", "discover"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--topic", nargs="*", default=["procedural-generation", "procedural-terrain", "l-systems",
                                                    "tree-generation", "terrain-generation", "boids"])
    a = ap.parse_args(argv)
    cat = json.load(open(CATALOG))
    repos = [r for r in cat["repos"] if not a.only or r["id"] in a.only]
    os.makedirs(CACHE, exist_ok=True)
    report = json.load(open(REPORT)) if os.path.exists(REPORT) else {}
    if a.cmd == "discover":
        print(discover(a.topic))
        return
    for e in repos:
        rep = report.get(e["id"], {})
        if a.cmd in ("probe", "clone") and not rep.get("ok"):
            rep = probe(e)
        if a.cmd == "clone":
            rep.update(clone(e, rep))
        if a.cmd == "index" and rep.get("cloned"):
            rep["index"] = index_repo(os.path.join(ROOT, rep["path"]))
        report[e["id"]] = rep
        flag = "OK " if rep.get("matches") else "?? "
        print(f"{flag}{e['id']:24s} found={rep.get('license_found')} expected={e.get('license')} "
              f"{'STUDY-ONLY' if rep.get('study_only') else ''} {rep.get('error', '')}")
    json.dump(report, open(REPORT, "w"), indent=1)


if __name__ == "__main__":
    main()

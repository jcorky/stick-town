"""Frames of the viewer's wind at fixed times (headless Chromium): an animated GIF and a motion check.

  python3 scripts/wind_frames.py out/monte-sano out/wind.gif [--force 6] [--frames 24] [--dt 0.2] [--tree N]

The wind clock is stepped by hand (Wind.uniforms.uTime), so frames are evenly spaced however slow software
WebGL is. The camera frames one tree (the tallest near the middle unless --tree is given). Prints the mean
absolute pixel change between consecutive frames, a quick check that the shader moves things at all.
"""

from __future__ import annotations

import argparse
import functools
import glob
import http.server
import io
import json
import os
import sys
import threading

import numpy as np
from PIL import Image


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir")
    ap.add_argument("out")
    ap.add_argument("--force", type=float, default=6.0)
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--dt", type=float, default=0.2)
    ap.add_argument("--t0", type=float, default=10.0)
    ap.add_argument("--tree", type=int, default=None)
    ap.add_argument("--dist", type=float, default=1.6, help="camera distance in tree heights")
    ap.add_argument("--size", default="720x540")
    ap.add_argument("--wait", type=float, default=25.0)
    a = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from plandscape.__main__ import write_viewer
    write_viewer(a.scene_dir)
    s = json.load(open(os.path.join(a.scene_dir, "scene.json")))
    trees = s["trees"]
    S = s["plan"]["size_m"]
    if a.tree is None:  # a mid-sized tree near the middle
        def score(t):
            return -abs(t["wind"]["H"] * t["scale"] - 18) - 0.3 * np.hypot(t["x"] - S / 2, t["y"] - S / 2)
        a.tree = int(max(range(len(trees)), key=lambda i: score(trees[i])))
    t = trees[a.tree]
    H = t["wind"]["H"] * t["scale"]
    tgt = [t["x"], t["z"] + 0.55 * H, -t["y"]]  # glTF frame
    # of 16 bearings, the one whose sightline crosses the fewest other crowns, preferring across the wind
    def blocked(b):
        cx_, cy_ = t["x"] + a.dist * H * np.sin(b), t["y"] + a.dist * H * np.cos(b)
        n = 0
        for j, o in enumerate(trees):
            if j == a.tree:
                continue
            r = 0.3 * o["wind"]["H"] * o["scale"]  # rough crown radius
            px, py = o["x"] - cx_, o["y"] - cy_
            vx, vy = t["x"] - cx_, t["y"] - cy_
            u = np.clip((px * vx + py * vy) / (vx * vx + vy * vy), 0, 1)
            n += np.hypot(px - u * vx, py - u * vy) < r + 1
        return n + 0.3 * abs(np.cos(b - np.radians(s["wind"]["from_deg"])))
    ang = min(np.radians(np.arange(0, 360, 22.5)), key=blocked)
    cx, cy = t["x"] + a.dist * H * np.sin(ang), t["y"] + a.dist * H * np.cos(ang)
    Z = np.load(os.path.join(a.scene_dir, "layers.npz"))["z"]  # keep the camera above the ground
    zg = float(Z[int(np.clip(round(cy), 0, Z.shape[0] - 1)), int(np.clip(round(cx), 0, Z.shape[1] - 1))])
    cam = [cx, max(t["z"] + 0.6 * H, zg + 0.5 * H), -cy]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.abspath(a.scene_dir))
    handler.log_message = lambda *x, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    w, h = (int(v) for v in a.size.split("x"))
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0]
    errors, frames = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe, args=["--use-gl=angle", "--use-angle=swiftshader",
                                                         "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        page = b.new_page(viewport=dict(width=w, height=h))
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(f"http://127.0.0.1:{srv.server_port}/index.html?force={a.force}&lod=0")
        page.wait_for_timeout(a.wait * 1000)
        page.evaluate("""([cam, tgt]) => {
            for (const id of ['hud', 'log', 'controls']) document.getElementById(id).style.display = 'none';
            wind = false; playing = false;
            controls.target.set(...tgt); camera.position.set(...cam); camera.near = 0.2; camera.updateProjectionMatrix();
            controls.update();
        }""", [cam, tgt])
        for k in range(a.frames):
            page.evaluate("(t) => { Wind.uniforms.uTime.value = t; renderer.render(scene, camera); }", a.t0 + k * a.dt)
            frames.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB"))
        b.close()
    srv.shutdown()
    for e in errors[:20]:
        print(e)
    arr = np.stack([np.asarray(f, np.float32) for f in frames])
    print("mean |Δ| between frames:", np.round(np.abs(np.diff(arr, axis=0)).mean(axis=(1, 2, 3)), 2).tolist())
    frames[0].save(a.out, save_all=True, append_images=frames[1:], duration=int(a.dt * 1000), loop=0)
    print("saved", a.out, f"tree {a.tree} ({t['species']}, {H:.1f} m)")


if __name__ == "__main__":
    main()

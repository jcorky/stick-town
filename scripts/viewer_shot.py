"""Screenshot the three.js viewer for a scene directory (headless Chromium, software WebGL).

  python3 scripts/viewer_shot.py out/monte-sano out/monte-sano/viewer.png [--wait 25]

Needs the `playwright` package and a Chromium (Claude cloud sessions ship one at /opt/pw-browsers).
Prints browser console errors so shader compile failures are visible.
"""

from __future__ import annotations

import argparse
import functools
import glob
import http.server
import os
import sys
import threading


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir")
    ap.add_argument("out")
    ap.add_argument("--wait", type=float, default=25.0)
    ap.add_argument("--size", default="1280x800")
    ap.add_argument("--query", default="", help="URL query, e.g. lod=0 to turn tree impostors off")
    ap.add_argument("--focus", default="", help="frame one node (e.g. white_tailed_deer_0) at clip time --at")
    ap.add_argument("--at", type=float, default=20.0)
    ap.add_argument("--dist", type=float, default=3.0, help="camera distance in body lengths for --focus")
    a = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from plandscape.__main__ import write_viewer
    write_viewer(a.scene_dir)  # the scene's copy is stale after any viewer edit
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.abspath(a.scene_dir))
    handler.log_message = lambda *x, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    w, h = (int(v) for v in a.size.split("x"))
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0]
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe, args=["--use-gl=angle", "--use-angle=swiftshader",
                                                         "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        page = b.new_page(viewport=dict(width=w, height=h))
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(f"http://127.0.0.1:{srv.server_port}/index.html" + (f"?{a.query}" if a.query else ""))
        page.wait_for_timeout(a.wait * 1000)
        if a.focus:  # stop the clock at --at and put the camera beside the animal, a little above it
            page.evaluate("""([name, at, dist]) => {
                renderer.setAnimationLoop(null);
                for (const id of ['hud', 'log', 'controls']) document.getElementById(id).style.display = 'none';
                if (mixer) mixer.setTime(at);
                const o = scene.getObjectByName(name); const box = new THREE.Box3().setFromObject(o);
                const c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
                const L = Math.max(s.x, s.y, s.z);
                controls.target.copy(c); camera.near = 0.02; camera.updateProjectionMatrix();
                camera.position.set(c.x + dist * L * 0.7, c.y + 0.35 * dist * L, c.z + dist * L * 0.7); controls.update();
                renderer.render(scene, camera);
            }""", [a.focus, a.at, a.dist])
        page.screenshot(path=a.out)
        b.close()
    srv.shutdown()
    for e in errors[:20]:
        print(e)
    print("saved", a.out)


if __name__ == "__main__":
    main()

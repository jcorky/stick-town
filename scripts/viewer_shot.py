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
        page.goto(f"http://127.0.0.1:{srv.server_port}/index.html")
        page.wait_for_timeout(a.wait * 1000)
        page.screenshot(path=a.out)
        b.close()
    srv.shutdown()
    for e in errors[:20]:
        print(e)
    print("saved", a.out)


if __name__ == "__main__":
    main()

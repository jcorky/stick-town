"""Drive the viewer's player mode headless on a fixed clock and print what the animals and people did (§35).

  python3 scripts/play_check.py out/play out/play/check.png [--steps "upwind:deer;wait:20;approach:deer;clap;food;wait:30"]

Each step runs inside the page with the animation loop stopped, advancing the clip, the wind and the player by
0.1 s ticks, so results do not depend on how slow software WebGL is. Steps:
  upwind:<species> / downwind:<species>  put the player 70 m up- or downwind of the first such animal, standing still
  approach:<species>                     walk at it until it flees or is 2.5 m away (up to 90 s)
  back:<m>                               back off m metres
  wait:<s>  clap  food  wave  crouch  run  shot:<name>  (a screenshot next to the output)
"""

from __future__ import annotations

import argparse
import functools
import glob
import http.server
import os
import sys
import threading

DEFAULT = "downwind:white_tailed_deer;wait:15;upwind:white_tailed_deer;wait:15;shot:smell;wait:40;" \
          "approach:white_tailed_deer;shot:flee;wait:30;approach:gray_squirrel;clap;wait:20;food;back:14;crouch;wait:90;" \
          "shot:food;crouch;wave;approach:human;wait:5;wave;wait:8;shot:people"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir")
    ap.add_argument("out")
    ap.add_argument("--steps", default=DEFAULT)
    ap.add_argument("--wait", type=float, default=30.0)
    ap.add_argument("--size", default="1100x700")
    a = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from plandscape.__main__ import write_viewer
    write_viewer(a.scene_dir)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *x, **k):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.abspath(a.scene_dir)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    w, h = (int(v) for v in a.size.split("x"))
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0]
    errors = []
    base, _ = os.path.splitext(a.out)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe, args=["--use-gl=angle", "--use-angle=swiftshader",
                                                         "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        page = b.new_page(viewport=dict(width=w, height=h))
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(f"http://127.0.0.1:{srv.server_port}/index.html?walk")
        page.wait_for_timeout(a.wait * 1000)
        page.evaluate("""() => {
            renderer.setAnimationLoop(null);
            window.tick = (sec) => { for (let k = 0; k < Math.round(sec * 10); k++) {
                if (mixer) mixer.update(0.1); Wind.uniforms.uTime.value += 0.1; Play.update(0.1); controls.update(); } };
            window.first = (sp) => Play.minds.find((m) => m.sp === sp);
        }""")
        for step in a.steps.split(";"):
            k, _, arg = step.partition(":")
            if k in ("upwind", "downwind"):
                page.evaluate("""([k, sp]) => { const m = first(sp); if (!m) return;
                    const [wx, wy] = Wind.dir(), s = k === 'upwind' ? -1 : 1;
                    Play.p.x = m.x + s * 70 * wx; Play.p.y = m.y + s * 70 * wy; Play.p.v = 0; Play.p.target = null;
                    Play.say(`(test) you stand 70 m ${k} of the ${sp.replace(/_/g, ' ')}`); }""", [k, arg])
            elif k == "approach":
                page.evaluate("""(sp) => { const m = first(sp); if (!m) return;
                    for (let i = 0; i < 900; i++) { Play.p.target = [m.x, m.y]; tick(0.1);
                      if (Math.hypot(m.x - Play.p.x, m.y - Play.p.y) < (sp === 'human' ? 2.0 : 2.5) || m.mind.state === 'flee') break; }
                    Play.p.target = null; Play.say(`(test) stopped ${Math.hypot(m.x - Play.p.x, m.y - Play.p.y).toFixed(1)} m from it`); }""", arg)
            elif k == "back":  # walk straight back the way the player faces
                page.evaluate("""(d) => { const p = Play.p; p.target = [p.x - Math.cos(p.h) * d, p.y - Math.sin(p.h) * d];
                    for (let i = 0; i < 300 && p.target; i++) tick(0.1); }""", float(arg))
            elif k == "wait":
                page.evaluate("(s) => tick(s)", float(arg))
            elif k == "shot":
                page.evaluate("() => renderer.render(scene, camera)")
                page.screenshot(path=f"{base}-{arg}.png")
            else:
                page.evaluate("(a) => Play.action(a)", k)
        log = page.evaluate("() => Play.events.slice().reverse()")
        state = page.evaluate("""() => Play.minds.map((m) => `${m.node.name}: ${m.mind.state} alarm ${m.mind.alarm.toFixed(2)}
            habit ${m.mind.habit.toFixed(2)} sens ${m.mind.sens.toFixed(2)} live ${m.live}`)""")
        page.evaluate("() => renderer.render(scene, camera)")
        page.screenshot(path=a.out)
        b.close()
    srv.shutdown()
    for e in errors[:20]:
        print(e)
    print("\n".join(log))
    print("--")
    print("\n".join(state))


if __name__ == "__main__":
    main()

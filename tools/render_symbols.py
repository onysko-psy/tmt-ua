"""Pictures of the candidate figure sets of the symbol coding task
(stimuli/coding-symbol-candidates.json), drawn by the dev page of the app
itself (?mode=dev&tool=coding) at the proposed sizes: for the author to choose
a set (decision 79). One picture per set: the key, every figure in its frame,
and the figures enlarged.

Needs Playwright with Chromium. Usage, from app/:
    python tools/render_symbols.py [px_per_mm]
Writes stimuli/coding-symbols-set-<id>.png; px_per_mm is 6 by default (a
laptop screen is 4-5; at 3.8 the picture is what an ordinary 96 dpi monitor
shows: add the argument and the files get the suffix -px<value>).
"""

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parent.parent


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    px = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    suffix = "" if px == 6.0 else f"-px{px:g}"
    sets = [s["id"] for s in json.loads((APP / "stimuli" / "coding-symbol-candidates.json").read_text())["sets"]]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(APP)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000}, device_scale_factor=1)
        page.add_init_script(
            "localStorage.setItem('tmtua.dev.calibration', JSON.stringify("
            f"{{pxPerMm: {px}, dpr: 1, suspect: false, savedAt: '2026-01-01T00:00:00Z'}}));")
        page.goto(f"http://127.0.0.1:{server.server_port}/?mode=dev&tool=coding")
        page.locator(".coding-set").first.wait_for()
        for set_id in sets:
            name = f"coding-symbols-set-{set_id}{suffix}.png"
            page.locator(f".coding-set[data-set='{set_id}']").screenshot(path=str(APP / "stimuli" / name))
            print("written:", name)
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()

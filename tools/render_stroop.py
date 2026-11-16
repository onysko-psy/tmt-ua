"""Pictures of the candidate looks of the Stroop screen
(stimuli/stroop-candidates.json), drawn by the dev page of the app itself
(?mode=dev&tool=stroop) in real size: for the author to choose (decisions 88,
90). One picture per variant: the screen of a trial, the four words in their
own and in other colours, the colours with their contrast.

Needs Playwright with Chromium. Usage, from app/:
    python tools/render_stroop.py [px_per_mm]
Writes stimuli/stroop-variant-<id>.png; px_per_mm is 5 by default (a laptop
screen is 4-5; at 3.8 the picture is what an ordinary 96 dpi monitor shows:
add the argument and the files get the suffix -px<value>).
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
    px = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    suffix = "" if px == 5.0 else f"-px{px:g}"
    variants = [v["id"] for v in json.loads((APP / "stimuli" / "stroop-candidates.json").read_text())["variants"]]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(APP)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        page.add_init_script(
            "localStorage.setItem('tmtua.dev.calibration', JSON.stringify("
            f"{{pxPerMm: {px}, dpr: 1, suspect: false, savedAt: '2026-01-01T00:00:00Z'}}));")
        page.goto(f"http://127.0.0.1:{server.server_port}/?mode=dev&tool=stroop")
        page.locator(".stroop-variant").first.wait_for()
        for variant in variants:
            name = f"stroop-variant-{variant}{suffix}.png"
            page.locator(f".stroop-variant[data-variant='{variant}']").screenshot(path=str(APP / "stimuli" / name))
            print("written:", name)
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()

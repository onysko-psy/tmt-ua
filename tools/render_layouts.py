"""Pictures of the TMT layouts the app uses (stimuli/tmt-layout.json), drawn by
the app itself at the decided sizes and font: for the record and for the
coursework. One picture per part as the participant sees it after the click
on the cross, and one with the correct path.

Needs Playwright with Chromium. Usage, from app/:
    python tools/render_layouts.py
Writes stimuli/tmt-layout-v<version>-<part>.png and ...-<part>-path.png.
"""

import functools
import http.server
import json
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parent.parent
PX_PER_MM = 6  # 240 mm -> 1440 px
PARTS = ["a", "b", "practice_a", "practice_b"]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    version = json.loads((APP / "stimuli" / "tmt-layout.json").read_text())["layout_version"]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(APP)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.add_init_script(
            "localStorage.setItem('tmtua.dev.calibration', JSON.stringify("
            f"{{pxPerMm: {PX_PER_MM}, dpr: 1, suspect: false, savedAt: '2026-01-01T00:00:00Z'}}));")
        for part in PARTS:
            for path in (False, True):
                choice = {"part": part, "show": {"path": path, "border": True, "cross": False}}
                page.add_init_script(f"localStorage.setItem('tmtua.dev.tmtChoice', {json.dumps(json.dumps(choice))});")
                page.goto(f"http://127.0.0.1:{server.server_port}/?mode=dev&tool=tmt")
                page.locator(".tmt-field").wait_for()
                page.keyboard.press("h")  # hide the panel
                name = f"tmt-layout-v{version}-{part}{'-path' if path else ''}.png"
                page.locator(".tmt-field").screenshot(path=str(APP / "stimuli" / name))
                print("written:", name)
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()

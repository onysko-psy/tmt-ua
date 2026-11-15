"""Shared setup for browser checks: a local server for app/ (or the published
site if TMTUA_BASE_URL is set), Chromium and WebKit, and a fake receiver so
that automatic checks never write into the real spreadsheets.
"""

import functools
import http.server
import json
import os
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

APP_DIR = Path(__file__).resolve().parent.parent
CODE_GS = (APP_DIR / "receiver" / "Code.gs").read_text()
RECEIVER_GLOB = "https://script.google.com/macros/**"

# Chromium does not route beacons through Playwright, so a page closed with
# pending data would beacon it to the real receiver. In checks, sendBeacon
# only records the body in window.__beacons.
RECORD_BEACONS = """window.__beacons = [];
navigator.sendBeacon = (url, blob) => {
    blob.text().then(text => window.__beacons.push(text));
    return true;
};"""


# Where to click in a TMT field that is on the page, in page px: the cross,
# an empty corner of the field, and the centre of every circle in path order.
TMT_POINTS = """() => {
    const svg = document.querySelector('.tmt-run .tmt-field');
    const field = svg.getBoundingClientRect();
    return {
        cross: [field.left + field.width / 2, field.top + field.height / 2],
        corner: [field.left + 3, field.top + 3],
        circles: [...svg.querySelectorAll('.tmt-circle circle')].map(circle => {
            const box = circle.getBoundingClientRect();
            return [box.left + box.width / 2, box.top + box.height / 2];
        }),
    };
}"""

TMT_BLOCKS = {"tmt_a": "TMT, частина A", "tmt_b": "TMT, частина B"}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class FakeReceiver:
    """Answers like the real receiver and records what the app sent.

    reply(body) may be replaced to simulate failures: return a dict to answer
    with it, or None to drop the connection.
    """

    def __init__(self):
        self.accepted = []  # parsed messages answered with ok
        self.requests = []  # (resource type, raw body) of everything that arrived
        self.reply = lambda body: {"ok": True, "receiver_version": "fake"}
        # Playwright's offline mode does not stop intercepted requests, so
        # going offline has to drop them here as well (see go_offline).
        self.offline = False

    def handle(self, route):
        request = route.request
        body = request.post_data or ""
        self.requests.append((request.resource_type, body))
        answer = None if self.offline else self.reply(body)
        if answer is None:
            route.abort()
            return
        if answer.get("ok"):
            self.accepted.append(json.loads(body))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(answer),
                      headers={"Access-Control-Allow-Origin": "*"})

    def blocks(self):
        return [message["block"] for message in self.accepted]


class AppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = None
        cls.base = os.environ.get("TMTUA_BASE_URL")
        if not cls.base:
            handler = functools.partial(QuietHandler, directory=APP_DIR)
            cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=cls.server.serve_forever, daemon=True).start()
            cls.base = f"http://127.0.0.1:{cls.server.server_port}/"
        cls.pw = sync_playwright().start()
        cls.browsers = [cls.pw.chromium.launch(), cls.pw.webkit.launch()]

    @classmethod
    def tearDownClass(cls):
        for browser in cls.browsers:
            browser.close()
        cls.pw.stop()
        if cls.server:
            cls.server.shutdown()

    def new_context(self, browser, init_script=None, **options):
        """A fresh browser profile (own localStorage) with a fake receiver.
        options go to Playwright, e.g. a device to emulate."""
        context = browser.new_context(**options)
        self.addCleanup(context.close)
        receiver = FakeReceiver()
        context.route(RECEIVER_GLOB, receiver.handle)
        context.add_init_script(RECORD_BEACONS)
        if init_script:
            context.add_init_script(init_script)
        return context, receiver

    def set_offline(self, context, receiver, offline):
        """Drops or restores the connection; coming back fires 'online'."""
        receiver.offline = offline
        context.set_offline(offline)

    def open(self, browser, query, block_cdn=False, tamper_cdn=False, context=None):
        """Opens the app; returns the page and a list collecting JS errors."""
        if context is None:
            context, _ = self.new_context(browser)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: msg.type == "error" and errors.append(msg.text))
        if block_cdn:
            page.route("**/cdn.jsdelivr.net/**", lambda route: route.abort())
        if tamper_cdn:
            def tamper(route):
                response = route.fetch()
                route.fulfill(response=response, body=response.text() + "\n;")
            page.route("**/jspsych@*/dist/*.js", tamper)
        page.goto(self.base + query)
        # The app loads its stimuli before the first screen (main.js).
        page.wait_for_function("() => document.documentElement.dataset.tmtuaReady === '1'")
        return page, errors

    def module(self, page, path):
        """Imports one of the app's own modules inside the page."""
        return page.evaluate(f"import('./src/{path}').then(m => JSON.parse(JSON.stringify(m)))")

    def blocks(self, page):
        return page.evaluate("import('./src/blocks.js').then(m => m.BLOCKS.map(b => [b.id, b.label]))")

    def click_through(self, page, labels):
        for label in labels:
            if label in TMT_BLOCKS.values():
                self.pass_tmt(page, label)
                continue
            page.locator(".placeholder", has_text=label).wait_for()
            page.get_by_role("button", name="Далі").click()

    def tmt_lead(self, page, label):
        """The screen before a TMT test (a stand-in for the instructions until T1.3)."""
        return page.locator(".tmt-lead", has_text=label)

    def start_tmt(self, page, label=None):
        """From the screen before a TMT test to the field with the cross;
        returns where to click (TMT_POINTS)."""
        if label:
            self.tmt_lead(page, label).wait_for()
        page.get_by_role("button", name="Почати").click()
        page.locator(".tmt-run").wait_for()
        return page.evaluate(TMT_POINTS)

    def click_tmt(self, page, points, order=None):
        """The bot: clicks the cross, then the circles with these indexes (all
        in path order by default); None in the order is a click beside the
        circles."""
        page.mouse.click(*points["cross"])
        for index in range(len(points["circles"])) if order is None else order:
            page.mouse.click(*(points["corner"] if index is None else points["circles"][index]))

    def pass_tmt(self, page, label=None):
        """Gets through a TMT block without errors."""
        self.click_tmt(page, self.start_tmt(page, label))
        page.locator(".tmt-run").wait_for(state="detached")

    def session_blocks(self, page):
        """(id, label, is a placeholder) of every block, in session order."""
        return page.evaluate(
            "import('./src/blocks.js').then(m => m.BLOCKS.map(b => [b.id, b.label, m.isPlaceholder(b)]))")

    def calibrate(self, page, card_px=380):
        """Drags the corner of the card picture until it is card_px wide (the
        plugin grows the card by twice the drag) and confirms. 380 px is a
        card at 4.44 px/mm, as on a 15" MacBook Air."""
        handle = page.locator("#jspsych-resize-handle")
        box = handle.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + (card_px - 250) / 2, y, steps=5)
        page.mouse.up()
        page.get_by_role("button", name="Готово: розмір збігається").click()

    def pass_block(self, page, block_id, label, placeholder):
        """Gets through one block as a participant on a desktop would."""
        if placeholder:
            page.locator(".placeholder", has_text=label).wait_for()
            page.get_by_role("button", name="Далі").click()
        elif block_id == "calibration":
            self.calibrate(page)
            if "mode=dev" in page.url:  # the 100 mm square, dev only
                page.locator(".dev-square").wait_for()
                page.get_by_role("button", name="Далі").click()
        elif block_id == "fullscreen":
            page.get_by_role("button", name="Увімкнути повноекранний режим").click()
        elif block_id in TMT_BLOCKS:
            self.pass_tmt(page, label)
        elif block_id != "device_check":  # an accepted device sees no screen
            raise AssertionError(f"no way through block {block_id}")

    def wait_delivered(self, page):
        page.wait_for_function("() => window.tmtua.sender.pending() === 0", timeout=15000)

    def assert_valid_for_receiver(self, context, messages):
        """Every message must pass the real receiver's validation."""
        page = context.new_page()
        page.add_script_tag(content=CODE_GS)
        for message in messages:
            self.assertIsNone(page.evaluate("p => validatePayload(p)", message), message)
        page.close()

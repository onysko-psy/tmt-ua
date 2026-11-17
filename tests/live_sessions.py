"""Several whole sessions at the same time against the REAL receiver (task T4.1).

Not part of the automatic test run: it writes rows into the PILOT storage
(mode=dev). The sessions run as separate processes, each with its own
browser, so their messages reach the receiver together (it takes one at a
time under a lock and tells the app to retry when it is busy). Prints the
session ids and codes; then compare the pilot spreadsheet. Run from the app/
folder:

    ../.venv/bin/python tests/live_sessions.py [number of sessions, default 3] [chromium|webkit]
"""

import functools
import http.server
import subprocess
import sys
import threading

from playwright.sync_api import sync_playwright

import sender_live as live
from harness import APP_DIR, QuietHandler


def one_session(browser_name):
    handler = functools.partial(QuietHandler, directory=APP_DIR)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch()
        page = browser.new_context().new_page()
        live.open_app(page, base + "?mode=dev&start=device_check&set.coding.durationMs=4000" + live.STROOP_FAST + live.SART_FAST)
        ids = page.evaluate("window.tmtua.ids")
        live.pass_questionnaires(page)
        live.calibrate(page)
        page.locator(".dev-square").wait_for()
        page.get_by_role("button", name="Далі").click()
        page.get_by_role("button", name="Увімкнути повноекранний режим").click()
        live.pass_tmt(page)
        live.pass_tmt(page)
        live.pass_coding(page, answers=30)
        live.pass_stroop(page)
        plan = live.sart_plan()
        live.pass_sart(page, press3=plan["press3"], omit=plan["omit"])
        live.pass_closing(page, email=None)
        page.get_by_role("button", name="Ні, дякую").click()  # no address: nothing goes to the contacts
        page.locator(".dev-end").wait_for()
        live.wait_delivered(page)
        print(f"{browser_name} session_id={ids['session_id']} participant_code={ids['participant_code']}", flush=True)
        browser.close()


def main():
    args = sys.argv[1:]
    if args and args[0] == "--one":
        return one_session(args[1])
    count = int(args[0]) if args else 3
    browser_name = args[1] if len(args) > 1 else "chromium"
    workers = [
        subprocess.Popen([sys.executable, __file__, "--one", browser_name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(count)
    ]
    failed = 0
    for worker in workers:
        out, _ = worker.communicate()
        print(out.strip())
        failed += worker.returncode != 0
    print(f"{count - failed} of {count} sessions went through")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

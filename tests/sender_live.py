"""Runs dev sessions against the REAL receiver (tasks T0.3, T0.5, T0.6, T1.2).

Not part of the automatic test run: it writes rows into the PILOT storage
(mode=dev). Prints the session ids; then compare the pilot spreadsheet with
the expectations printed at the end. Run from the app/ folder:

    ../.venv/bin/python tests/sender_live.py
"""

import functools
import http.server
import threading

from playwright.sync_api import sync_playwright

from harness import APP_DIR, RECEIVER_GLOB, TMT_POINTS, QuietHandler


def click_through(page, count):
    for _ in range(count):
        page.locator(".placeholder").wait_for()
        text = page.locator(".placeholder").text_content()
        page.get_by_role("button", name="Далі").click()
        page.wait_for_function("t => document.querySelector('.placeholder')?.textContent !== t", arg=text)


def open_app(page, url):
    page.goto(url)
    page.wait_for_function("() => document.documentElement.dataset.tmtuaReady === '1'")


def pass_tmt(page, order=None):
    """Clicks through a TMT test: the cross, then the circles with these
    indexes (all in path order by default); None is a click beside them."""
    page.locator(".tmt-lead").wait_for()
    page.get_by_role("button", name="Почати").click()
    page.locator(".tmt-run").wait_for()
    points = page.evaluate(TMT_POINTS)
    page.mouse.click(*points["cross"])
    for index in range(len(points["circles"])) if order is None else order:
        page.mouse.click(*(points["corner"] if index is None else points["circles"][index]))
        page.wait_for_timeout(40)
    page.locator(".tmt-run").wait_for(state="detached")


def calibrate(page, card_px=380):
    handle = page.locator("#jspsych-resize-handle")
    box = handle.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + (card_px - 250) / 2, y, steps=5)
    page.mouse.up()
    page.get_by_role("button", name="Готово: розмір збігається").click()


def wait_delivered(page):
    page.wait_for_function("() => window.tmtua.sender.pending() === 0", timeout=120_000)


def main():
    handler = functools.partial(QuietHandler, directory=APP_DIR)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    report = []

    with sync_playwright() as pw:
        for browser_type in (pw.chromium, pw.webkit):
            browser = browser_type.launch()
            name = browser_type.name

            # 1. Whole session, connection drops after 7 messages and comes
            # back. device_check shows no screen on a desktop and sends nothing.
            context = browser.new_context()
            page = context.new_page()
            open_app(page, base + "?mode=dev&start=device_check")
            session_id = page.evaluate("window.tmtua.ids.session_id")
            click_through(page, 4)  # consent .. conditions
            calibrate(page)
            page.locator(".dev-square").wait_for()  # the 100 mm square, dev only
            page.get_by_role("button", name="Далі").click()
            page.get_by_role("button", name="Увімкнути повноекранний режим").click()
            pass_tmt(page)  # tmt_a, without errors
            wait_delivered(page)
            context.set_offline(True)
            # tmt_b: 2 instead of А, a click beside, Б again after Б, 1 instead of 3.
            pass_tmt(page, [0, 2, None, 1, 2, 3, 3, 0] + list(range(4, 25)))
            click_through(page, 6)  # coding .. retest_invite
            page.get_by_role("button", name="Далі").click()  # last block
            page.locator(".dev-end").wait_for()
            queued = page.evaluate("window.tmtua.sender.pending()")
            context.set_offline(False)
            wait_delivered(page)
            report.append(f"{name}: full session {session_id} (8 blocks queued offline: {queued == 8})")
            context.close()

            # 2. fetch blocked, page left: only the beacon can deliver.
            context = browser.new_context()
            context.route(RECEIVER_GLOB, lambda route: route.abort()
                          if route.request.resource_type == "fetch" else route.continue_())
            page = context.new_page()
            open_app(page, base + "?mode=dev&only=tmt_a")
            session_id = page.evaluate("window.tmtua.ids.session_id")
            pass_tmt(page)
            page.locator(".dev-end").wait_for()
            page.goto("about:blank")
            page.wait_for_timeout(8000)  # the receiver needs a few seconds
            report.append(f"{name}: beacon only {session_id}")
            context.close()
            browser.close()

    server.shutdown()
    print("\n".join(report))
    print("""
Expected in the pilot sessions sheet:
- each "full session" id: one row, 11 *_placeholder columns equal to 1,
  px_per_mm 4.4393, calibration_card_px 380, calibration_attempts 1,
  calibration_suspect 0, screen_w_mm 288.3, screen_h_mm 162.2,
  fullscreen_status "entered", fullscreen_view_w_mm / _h_mm filled,
  fullscreen_window_checks 0, no status column value, device_* columns filled (device_any_pointer_fine
  among them), session_type "first", last_block "thanks"; for each of tmt_a,
  tmt_b, coding, stroop, sart ten columns <task>_hidden_n, _hidden_ms,
  _blur_n, _blur_ms, _fs_exit_n, _fs_exit_ms, _resize_n, _zoom_n,
  _zoom_blocked_n, _touch_n, all 0 (a headless browser has nothing to leave);
  TMT: layout_version 1; tmt_a_status "complete", tmt_a_time_ms about 1100-2500,
  tmt_a_targets_done 25, tmt_a_errors_n 0, tmt_a_err_wrong_target_n 0,
  tmt_a_repeat_n 0, tmt_a_miss_n 0, six tmt_a_test_* columns equal to 0, no
  tmt_a_err_alternation_n column value; tmt_b_status "complete",
  tmt_b_targets_done 25, tmt_b_errors_n 2, tmt_b_err_alternation_n 1,
  tmt_b_err_wrong_target_n 1, tmt_b_repeat_n 1, tmt_b_miss_n 1, six tmt_b_test_*
  columns equal to 0; in the session's log folder calibration.json with the
  attempts, tmt_a.json and tmt_b.json with "clicks", "trajectory" and "env",
  and a JSON file per other task with "env" inside
- each "beacon only" id: one row with tmt_a_status "complete" and the other tmt_a_* columns""")


if __name__ == "__main__":
    main()

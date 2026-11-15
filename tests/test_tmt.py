"""Checks of the TMT plugin (task T1.2) in Chromium and WebKit: how clicks
are scored, and a bot that goes through the scenarios of docs/14, 3.2 — "A
without errors", "Errors in A", "Alternation in B", "Limit" — and compares
what the app sends with what it did. Also: sizes in mm, the cursor
trajectory, the exits counted for the test alone (decisions 133, 135) and
blocked zoom (decision 132).

Run from the app/ folder: ../.venv/bin/python -m unittest tests.test_tmt -v
"""

import json
import time
import unittest

from playwright.sync_api import expect

from harness import APP_DIR, AppTestCase

FAST = "&set.send.retryBaseMs=100&set.send.retryMaxMs=500"
A = "TMT, частина A"
B = "TMT, частина B"
LAYOUT = json.loads((APP_DIR / "stimuli" / "tmt-layout.json").read_text())

SAVED = "localStorage.setItem('tmtua.dev.calibration', JSON.stringify(" \
    "{pxPerMm: 5, dpr: window.devicePixelRatio, suspect: false, savedAt: '2026-11-15T18:00:00Z'}));"

SCORE = """([labels, order]) => import('./src/tmt/run.js').then(m => {
    const scorer = m.createScorer(labels);
    const results = order.map(index => {
        const r = scorer.click(index);
        return r.result + (r.error_type ? ':' + r.error_type : '');
    });
    return { results, counts: scorer.counts, next: scorer.next(), done: scorer.done() };
})"""

SET_VISIBILITY = """hidden => {
    Object.defineProperty(document, 'visibilityState', {
        configurable: true, get: () => hidden ? 'hidden' : 'visible' });
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
    document.dispatchEvent(new Event('visibilitychange'));
}"""

# Each returns whether the page stopped the browser's own reaction.
KEY = """init => {
    const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init });
    document.body.dispatchEvent(event);
    return event.defaultPrevented;
}"""
WHEEL = """init => {
    const event = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: -20, ...init });
    document.body.dispatchEvent(event);
    return event.defaultPrevented;
}"""
GESTURE = """type => {
    const event = new Event(type, { bubbles: true, cancelable: true });
    document.body.dispatchEvent(event);
    return event.defaultPrevented;
}"""


class ScoringTest(AppTestCase):
    """How clicks are scored (tmt/run.js); no field on the screen."""

    def score(self, labels, order):
        if not hasattr(self, "page"):
            self.page, _ = self.open(self.browsers[0], "?mode=dev")
        return self.page.evaluate(SCORE, [labels, order])

    def test_part_a(self):
        got = self.score("1 2 3 4 5".split(), [0, 1, 3, None, 2, 2, 0, 3, 4])
        self.assertEqual(got["results"], [
            "correct", "correct",
            "error:wrong_target",  # 4 instead of 3
            "miss",  # beside the circles: not an error (decision 63)
            "correct",
            "repeat",  # 3 again, the line ends there: not an error (decision 134)
            "error:wrong_target",  # 1, an earlier circle of the path
            "correct", "correct",
        ])
        self.assertEqual(got["counts"], {"errors": 2, "wrong_target": 2, "alternation": 0, "repeat": 1, "miss": 1})
        self.assertTrue(got["done"])

    def test_part_b(self):
        got = self.score("1 А 2 Б 3".split(), [0, 2, 4, 3, 1, 0, 1, 3, 2, 3, 4])
        self.assertEqual(got["results"], [
            "correct",
            "error:alternation",  # 2 where А is due: a number instead of a letter
            "error:alternation",  # 3 where А is due
            "error:wrong_target",  # Б where А is due: a letter, but not the next one
            "correct",
            "error:wrong_target",  # 1 where 2 is due
            "repeat",  # А again
            "error:alternation",  # Б where 2 is due: a letter instead of a number
            "correct", "correct", "correct",
        ])
        self.assertEqual(got["counts"], {"errors": 5, "wrong_target": 2, "alternation": 3, "repeat": 1, "miss": 0})
        self.assertTrue(got["done"])

    def test_nothing_counts_before_the_end_as_done(self):
        got = self.score("1 2 3".split(), [0, None, None])
        self.assertEqual((got["next"], got["done"]), (1, False))
        self.assertEqual(got["counts"]["miss"], 2)

    def test_letters_of_part_b_are_letters(self):
        """Every label of the layouts file is told apart as a number or a
        letter, Ґ, Є and І among them (decision 121)."""
        page, _ = self.open(self.browsers[0], "?mode=dev")
        labels = LAYOUT["layouts"]["b"]["labels"]
        kinds = page.evaluate("labels => import('./src/tmt/run.js').then(m => labels.map(m.labelKind))", labels)
        self.assertEqual(kinds, ["number", "letter"] * 12 + ["number"])
        self.assertEqual("".join(labels[1::2]), "АБВГҐДЕЄЖЗИІ")


class TmtRunTest(AppTestCase):
    def open_part(self, browser, block, extra="", **options):
        context, receiver = self.new_context(browser, **options)
        page, errors = self.open(browser, f"?mode=dev&only={block}{FAST}{extra}", context=context)
        return context, receiver, page, errors

    def result_of(self, page, receiver, block):
        page.locator(".dev-end").wait_for()
        self.wait_delivered(page)
        [message] = [m for m in receiver.accepted if m["block"] == block]
        return message["summary"], message["log"]

    def test_a_without_errors(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, "tmt_a")
                points = self.start_tmt(page, A)

                # Before the click on the cross: the cross and the hint, no circles.
                circles = page.locator(".tmt-run .tmt-circle")
                self.assertEqual(circles.count(), 25)
                expect(circles.first).to_be_hidden()
                expect(page.locator(".tmt-start-hint")).to_have_text("Клацніть хрестик, щоб почати")
                self.assertEqual(page.locator(".tmt-corner-label").count(), 0)  # only in the practice
                page.mouse.click(*points["corner"])  # not the cross: nothing starts
                expect(circles.first).to_be_hidden()
                page.wait_for_timeout(800)  # looking at the cross is not test time (decision 59)

                page.mouse.click(*points["cross"])
                started = time.monotonic()
                expect(circles.first).to_be_visible()
                self.assertEqual(page.locator(".tmt-cross").count(), 0)
                self.assertEqual(page.locator(".tmt-start-hint").count(), 0)
                for index, point in enumerate(points["circles"]):
                    if index == 12:
                        page.wait_for_timeout(700)
                    page.mouse.click(*point)
                    if index == 12:
                        self.assertEqual(page.locator(".tmt-line").count(), 12)
                stopwatch = (time.monotonic() - started) * 1000

                summary, log = self.result_of(page, receiver, "tmt_a")
                self.assertEqual(summary["tmt_a_status"], "complete")
                self.assertEqual(summary["tmt_a_targets_done"], 25)
                for key in ["errors_n", "err_wrong_target_n", "repeat_n", "miss_n"]:
                    self.assertEqual(summary[f"tmt_a_{key}"], 0, key)
                self.assertNotIn("tmt_a_err_alternation_n", summary)  # nothing alternates in part A
                self.assertGreater(summary["tmt_a_time_ms"], 700)
                self.assertAlmostEqual(summary["tmt_a_time_ms"], stopwatch, delta=250)
                self.assertEqual(summary["layout_version"], "1")
                for key in ["hidden_n", "hidden_ms", "blur_n", "blur_ms", "fs_exit_n", "fs_exit_ms"]:
                    self.assertEqual(summary[f"tmt_a_test_{key}"], 0, key)
                self.assertEqual(summary["tmt_a_zoom_blocked_n"], 0)

                # The log: every click with what was due, what was clicked, when and where.
                clicks = log["clicks"]
                labels = LAYOUT["layouts"]["a"]["labels"]
                self.assertEqual([c["expected"] for c in clicks], labels)
                self.assertEqual([c["target"] for c in clicks], labels)
                self.assertEqual({c["result"] for c in clicks}, {"correct"})
                self.assertEqual({c["pointer"] for c in clicks}, {"mouse"})
                times = [c["t"] for c in clicks]
                self.assertEqual(times, sorted(times))
                self.assertEqual(times[-1], summary["tmt_a_time_ms"])
                self.assertGreater(times[12] - times[11], 650)  # the pause is in the log
                # mm from the field centre; a browser reports whole pixels, here 0.26 mm each.
                for click, (x, y) in zip(clicks, LAYOUT["layouts"]["a"]["points"]):
                    self.assertAlmostEqual(click["x"], x * 1.5, delta=0.5)
                    self.assertAlmostEqual(click["y"], y * 1.5, delta=0.5)
                self.assertEqual((log["part"], log["layout_id"], log["layout_version"]), ("a", "a-1", "1"))
                self.assertEqual((log["field_mm"], log["circle_mm"], log["letter_mm"]), ([240, 150], 11, 4.5))
                self.assertEqual((log["time_limit_ms"], log["trajectory_hz"]), (300000, 30))
                self.assertEqual(log["cross_stray_n"], 1)
                self.assertGreater(log["cross_wait_ms"], 750)
                self.assertLess(times[0], 300)  # the clock starts at the click on the cross
                self.assertTrue(log["fits"])
                self.assertEqual(log["scale_source"], "fallback")
                self.assertEqual([e["type"] for e in log["env"]["events"]], ["test_start", "test_end"])

                # jsPsych's own data keep the counts only.
                [trial] = page.evaluate(
                    "window.tmtua.jsPsych.data.get().values().filter(t => t.trial_type === 'tmtua-tmt')")
                self.assertEqual((trial["part"], trial["status"], trial["targets_done"]), ("a", "complete", 25))
                self.assertNotIn("clicks", trial)
                self.assertNotIn("trajectory", trial)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_errors_in_a(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, "tmt_a")
                points = self.start_tmt(page, A)
                circles, corner = points["circles"], points["corner"]
                page.mouse.click(*points["cross"])
                page.mouse.click(*circles[0])
                page.mouse.click(*circles[5])  # 6 instead of 2
                page.mouse.click(*circles[7])  # 8 instead of 2
                # Both stay red, and no line is drawn, until the right click.
                self.assertEqual(
                    page.locator(".tmt-wrong").evaluate_all("nodes => nodes.map(n => n.dataset.label)"), ["6", "8"])
                self.assertEqual(page.locator(".tmt-line").count(), 0)
                stroke = page.locator(".tmt-wrong circle").first.evaluate("node => getComputedStyle(node).stroke")
                self.assertEqual(stroke, "rgb(200, 16, 46)")
                for _ in range(3):
                    page.mouse.click(*corner)  # beside the circles: no highlight
                self.assertEqual(page.locator(".tmt-wrong").count(), 2)
                page.mouse.click(*circles[5], button="right")  # only the main button clicks
                page.mouse.click(*circles[1])
                self.assertEqual(page.locator(".tmt-wrong").count(), 0)
                self.assertEqual(page.locator(".tmt-line").count(), 1)
                page.mouse.dblclick(*circles[2])  # a double click on the right circle
                self.assertEqual(page.locator(".tmt-wrong").count(), 0)
                self.assertEqual(page.locator(".tmt-line").count(), 2)
                for point in circles[3:]:
                    page.mouse.click(*point)

                summary, log = self.result_of(page, receiver, "tmt_a")
                self.assertEqual(summary["tmt_a_status"], "complete")
                self.assertEqual(summary["tmt_a_errors_n"], 2)
                self.assertEqual(summary["tmt_a_err_wrong_target_n"], 2)
                self.assertEqual(summary["tmt_a_miss_n"], 3)
                self.assertEqual(summary["tmt_a_repeat_n"], 1)
                self.assertEqual(summary["tmt_a_targets_done"], 25)
                self.assertEqual(
                    [(c["expected"], c["target"], c["result"], c.get("error_type")) for c in log["clicks"][:9]],
                    [("1", "1", "correct", None),
                     ("2", "6", "error", "wrong_target"),
                     ("2", "8", "error", "wrong_target"),
                     ("2", None, "miss", None), ("2", None, "miss", None), ("2", None, "miss", None),
                     ("2", "2", "correct", None),
                     ("3", "3", "correct", None),
                     ("4", "3", "repeat", None)])
                self.assertEqual(len(log["clicks"]), 31)  # 25 right, 2 wrong, 3 beside, 1 repeated
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_alternation_in_b(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, "tmt_b")
                points = self.start_tmt(page, B)
                circles = points["circles"]
                page.mouse.click(*points["cross"])
                page.mouse.click(*circles[0])
                page.mouse.click(*circles[2])  # 2 instead of А
                self.assertEqual(
                    page.locator(".tmt-wrong").evaluate_all("nodes => nodes.map(n => n.dataset.label)"), ["2"])
                self.assertEqual(page.locator(".tmt-line").count(), 0)
                for point in circles[1:]:
                    page.mouse.click(*point)

                summary, log = self.result_of(page, receiver, "tmt_b")
                self.assertEqual(summary["tmt_b_status"], "complete")
                self.assertEqual(summary["tmt_b_err_alternation_n"], 1)
                self.assertEqual(summary["tmt_b_err_wrong_target_n"], 0)
                self.assertEqual(summary["tmt_b_errors_n"], 1)
                self.assertEqual(summary["tmt_b_targets_done"], 25)
                self.assertNotIn("layout_version", summary)  # goes with part A
                wrong = log["clicks"][1]
                self.assertEqual((wrong["expected"], wrong["target"], wrong["result"], wrong["error_type"]),
                                 ("А", "2", "error", "alternation"))
                self.assertEqual([c["target"] for c in log["clicks"] if c["result"] == "correct"],
                                 LAYOUT["layouts"]["b"]["labels"])
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_time_limit(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, "tmt_a", "&set.tmt.timeLimitMs=1200")
                points = self.start_tmt(page, A)
                self.click_tmt(page, points, order=[0, 1, 2, 9])
                # The part stops by itself; the participant is told and goes on.
                expect(page.locator(".screen")).to_contain_text("Час на цю частину вийшов")
                self.assertEqual(page.locator(".tmt-run").count(), 0)
                page.get_by_role("button", name="Далі").click()

                summary, log = self.result_of(page, receiver, "tmt_a")
                self.assertEqual(summary["tmt_a_status"], "timeout")
                self.assertEqual(summary["tmt_a_time_ms"], 1200)
                self.assertEqual(summary["tmt_a_targets_done"], 3)
                self.assertEqual(summary["tmt_a_errors_n"], 1)
                self.assertGreaterEqual(log["elapsed_ms"], 1200)
                self.assertLess(log["elapsed_ms"], 1700)
                self.assertEqual(log["time_limit_ms"], 1200)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_sizes_in_mm_and_the_edge_of_a_circle(self):
        """With a calibration of 5 px/mm the field is 240x150 mm, and a
        click counts for a circle exactly within its 11 mm."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(
                    browser, "tmt_a", init_script=SAVED, viewport={"width": 1400, "height": 900})
                points = self.start_tmt(page, A)
                field = page.locator(".tmt-run .tmt-field").bounding_box()
                self.assertAlmostEqual(field["width"], 240 * 5, delta=1)
                self.assertAlmostEqual(field["height"], 150 * 5, delta=1)
                # In the middle of the page.
                self.assertAlmostEqual(field["x"] + field["width"] / 2, 700, delta=1)
                self.assertAlmostEqual(field["y"] + field["height"] / 2, 450, delta=1)
                circle = page.locator(".tmt-run .tmt-circle circle").first.bounding_box()
                self.assertAlmostEqual(circle["width"], 11 * 5, delta=1)

                circles = points["circles"]
                page.mouse.click(*points["cross"])
                page.mouse.click(circles[0][0] + 5.2 * 5, circles[0][1])  # 5.2 mm from the centre: inside
                page.mouse.click(circles[1][0], circles[1][1] - 5.8 * 5)  # 5.8 mm: beside
                for point in circles[1:]:
                    page.mouse.click(*point)
                summary, log = self.result_of(page, receiver, "tmt_a")
                self.assertEqual((summary["tmt_a_errors_n"], summary["tmt_a_miss_n"]), (0, 1))
                self.assertEqual([c["result"] for c in log["clicks"][:3]], ["correct", "miss", "correct"])
                self.assertEqual(log["px_per_mm"], 5)
                self.assertEqual(log["scale_source"], "dev_saved")
                self.assertEqual(log["field_px"], [1200, 750])
                self.assertEqual(log["page_px"], [1400, 900])
                self.assertEqual(errors, [])

    def test_cursor_trajectory(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, "tmt_a")
                points = self.start_tmt(page, A)
                circles = points["circles"]
                page.mouse.move(*points["corner"])  # before the start: not recorded
                page.mouse.click(*points["cross"])
                # About 1.2 s of steady movement to circle 1, a move every 10 ms.
                (x0, y0), (x1, y1) = points["cross"], circles[0]
                for step in range(1, 81):
                    page.mouse.move(x0 + (x1 - x0) * step / 80, y0 + (y1 - y0) * step / 80)
                    page.wait_for_timeout(10)
                for point in circles:
                    page.mouse.click(*point)
                summary, log = self.result_of(page, receiver, "tmt_a")

                trajectory = log["trajectory"]
                first_click = log["clicks"][0]
                self.assertEqual(trajectory[0][0], 0)  # starts at the click on the cross...
                self.assertAlmostEqual(trajectory[0][1], 0, delta=0.5)  # ...in the centre of the field
                self.assertAlmostEqual(trajectory[0][2], 0, delta=0.5)
                times = [t for t, _, _ in trajectory]
                self.assertEqual(times, sorted(times))
                moving = [sample for sample in trajectory if 0 < sample[0] < first_click["t"]]
                # About 30 samples a second (decision 61), not one per move.
                rate = len(moving) / (first_click["t"] / 1000)
                self.assertGreater(rate, 15, (len(moving), first_click["t"]))
                self.assertLess(rate, 36, (len(moving), first_click["t"]))
                gaps = sorted(b[0] - a[0] for a, b in zip(moving, moving[1:]))
                self.assertGreater(gaps[len(gaps) // 2], 20)  # the usual gap is about 33 ms
                # The path is a straight line from the cross to circle 1, in mm.
                tx, ty = first_click["x"], first_click["y"]
                length = (tx ** 2 + ty ** 2) ** 0.5
                for t, x, y in moving:
                    along = (x * tx + y * ty) / length
                    across = abs(x * ty - y * tx) / length
                    self.assertGreater(along, -0.6)
                    self.assertLess(along, length + 0.6)
                    self.assertLess(across, 0.6, (t, x, y))
                self.assertGreater(len({(x, y) for _, x, y in moving}), 20)  # and it does move along it
                # Every click is on the trajectory as well.
                for click in log["clicks"]:
                    self.assertIn([click["t"], click["x"], click["y"]], trajectory)
                self.assertEqual(errors, [])

    def test_exits_during_the_test_are_counted_apart(self):
        """Decisions 133 and 135: leaving the tab, losing focus and leaving
        fullscreen are counted for the whole task and, apart, for the test
        itself, from the click on the cross to the last circle."""
        away = "() => window.dispatchEvent(new Event('blur'))"
        back = "() => window.dispatchEvent(new Event('focus'))"
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, "tmt_a")
                self.tmt_lead(page, A).wait_for()
                # Before the test: away once.
                page.evaluate(away)
                page.evaluate(SET_VISIBILITY, True)
                page.wait_for_timeout(300)
                page.evaluate(SET_VISIBILITY, False)
                page.evaluate(back)

                points = self.start_tmt(page)
                circles = points["circles"]
                page.mouse.click(*points["cross"])
                for point in circles[:5]:
                    page.mouse.click(*point)
                # During the test: away once more, and focus lost one more time.
                page.evaluate(away)
                page.evaluate(SET_VISIBILITY, True)
                page.wait_for_timeout(400)
                page.evaluate(SET_VISIBILITY, False)
                page.evaluate(back)
                page.evaluate(away)
                page.wait_for_timeout(200)
                page.evaluate(back)
                for point in circles[5:]:
                    page.mouse.click(*point)

                summary, log = self.result_of(page, receiver, "tmt_a")
                self.assertEqual(summary["tmt_a_status"], "complete")  # the test went on (decision 62)
                self.assertEqual(summary["tmt_a_hidden_n"], 2)
                self.assertEqual(summary["tmt_a_blur_n"], 3)
                self.assertGreaterEqual(summary["tmt_a_hidden_ms"], 650)
                self.assertEqual(summary["tmt_a_test_hidden_n"], 1)
                self.assertGreaterEqual(summary["tmt_a_test_hidden_ms"], 350)
                self.assertLess(summary["tmt_a_test_hidden_ms"], 650)
                self.assertEqual(summary["tmt_a_test_blur_n"], 2)
                self.assertGreaterEqual(summary["tmt_a_test_blur_ms"], 550)
                self.assertEqual(summary["tmt_a_test_fs_exit_n"], 0)
                self.assertEqual(log["during_test"]["hidden_n"], 1)
                self.assertEqual(
                    [e["type"] for e in log["env"]["events"]],
                    ["blur", "hidden", "visible", "focus", "test_start",
                     "blur", "hidden", "visible", "focus", "blur", "focus", "test_end"])
                self.assertGreater(summary["tmt_a_time_ms"], 600)  # the clock did not stop
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])


class ZoomBlockTest(AppTestCase):
    """Decision 132: during a task the keys and the pinch that change the
    page scale do nothing, and each try is recorded."""

    def test_zoom_keys_and_pinch_are_blocked_during_a_task(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, "?mode=dev&only=tmt_a" + FAST, context=context)
                self.tmt_lead(page, A).wait_for()

                # Cmd or Ctrl with "+", "-", "=", "0", whatever the keyboard layout.
                self.assertTrue(page.evaluate(KEY, {"key": "=", "code": "Equal", "ctrlKey": True}))
                self.assertTrue(page.evaluate(KEY, {"key": "-", "code": "Minus", "metaKey": True}))
                self.assertTrue(page.evaluate(KEY, {"key": "0", "code": "Digit0", "metaKey": True}))
                self.assertTrue(page.evaluate(KEY, {"key": "+", "code": "NumpadAdd", "ctrlKey": True}))
                self.assertTrue(page.evaluate(KEY, {"key": "є", "code": "Equal", "ctrlKey": True}))  # by its place
                # A held key repeats: still blocked, counted once.
                self.assertTrue(page.evaluate(KEY, {"key": "=", "code": "Equal", "ctrlKey": True, "repeat": True}))
                # Other keys are left alone.
                self.assertFalse(page.evaluate(KEY, {"key": "=", "code": "Equal"}))
                self.assertFalse(page.evaluate(KEY, {"key": "a", "code": "KeyA", "ctrlKey": True}))
                self.assertFalse(page.evaluate(KEY, {"key": "1", "code": "Digit1", "metaKey": True}))

                # A pinch in Chrome, Edge and Firefox: a burst of wheel events with ctrlKey. One try.
                for _ in range(6):
                    self.assertTrue(page.evaluate(WHEEL, {"ctrlKey": True}))
                page.wait_for_timeout(700)
                self.assertTrue(page.evaluate(WHEEL, {"ctrlKey": True}))  # another pinch
                self.assertFalse(page.evaluate(WHEEL, {}))  # plain scrolling is left alone

                # A pinch in Safari.
                for kind in ["gesturestart", "gesturechange", "gestureend"]:
                    self.assertTrue(page.evaluate(GESTURE, kind))

                self.pass_tmt(page)
                page.locator(".dev-end").wait_for()
                self.wait_delivered(page)
                [message] = [m for m in receiver.accepted if m["block"] == "tmt_a"]
                self.assertEqual(message["summary"]["tmt_a_zoom_blocked_n"], 8)
                self.assertEqual(message["summary"]["tmt_a_zoom_n"], 0)
                blocked = [e["how"] for e in message["log"]["env"]["events"] if e["type"] == "zoom_blocked"]
                self.assertEqual(blocked, ["keys"] * 5 + ["wheel"] * 2 + ["gesture"])
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_outside_the_tasks_zoom_is_left_alone(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors = self.open(browser, "?mode=dev&only=consent")
                page.locator(".placeholder").wait_for()
                self.assertFalse(page.evaluate(KEY, {"key": "=", "code": "Equal", "ctrlKey": True}))
                self.assertFalse(page.evaluate(WHEEL, {"ctrlKey": True}))
                self.assertFalse(page.evaluate(GESTURE, "gesturestart"))
                self.assertEqual(errors, [])

    def test_the_check_page_shows_a_blocked_try(self):
        browser = self.browsers[0]
        page, errors = self.open(browser, "?mode=dev&tool=env")
        page.locator(".env-events").wait_for(state="attached")
        self.assertTrue(page.evaluate(KEY, {"key": "=", "code": "Equal", "metaKey": True}))
        expect(page.locator(".env-events")).to_contain_text("спробу змінити масштаб заблоковано · клавіші")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

"""Checks of the SART task (task T3.3): the fixed sequences, the scoring, the
time of the digit and the mask in frames, what counts as an answer (the space
bar), the training with its hints and its repeat, the main part, the countdown,
the same stimuli at the retest, the data sent, and the monitor around the task.
In Chromium and WebKit; the sequence checks need no browser.

Run from the app/ folder: ../.venv/bin/python -m unittest discover -s tests -p "test_sart.py" -v
"""

import importlib.util
import json
import statistics
import unittest
from pathlib import Path

from harness import AppTestCase

APP = Path(__file__).resolve().parent.parent
SEQUENCE = json.loads((APP / "stimuli" / "sart-sequence.json").read_text())
LOOK = json.loads((APP / "stimuli" / "sart-look.json").read_text())
CANDIDATES = json.loads((APP / "stimuli" / "sart-candidates.json").read_text())
CODE = "k3m8q7w2xz"  # a participant code of the first session, for the retest link
MAIN = SEQUENCE["main"]
PRACTICE = SEQUENCE["practice"]

# Columns of the table the block adds besides the 10 of the monitor.
COLUMNS = {
    "sart_practice_attempts_n", "sart_practice_omissions_1", "sart_practice_omissions_2",
    "sart_practice_commissions_1", "sart_practice_commissions_2", "sart_look_version", "sart_sequence_version",
    "sart_commission_n", "sart_commission_rate", "sart_omission_n", "sart_omission_rate", "sart_hit_n",
    "sart_withhold_n", "sart_rt_mean_ms", "sart_rt_sd_ms", "sart_rt_cv", "sart_fast_n", "sart_extra_n",
    "sart_time_ms", "sart_refresh_hz", "sart_digit_frames", "sart_digit_mean_ms", "sart_digit_dev_mean_ms",
    "sart_digit_dev_max_ms", "sart_mask_mean_ms",
    # the exits during the main part itself (decision 168)
    "sart_test_hidden_n", "sart_test_hidden_ms", "sart_test_blur_n", "sart_test_blur_ms",
    "sart_test_fs_exit_n", "sart_test_fs_exit_ms",
}
# Shortened runs: fewer trials, a short mask (never a shorter digit), a short countdown and feedback.
FAST = ("&set.sart.mainTrials=12&set.sart.practiceTrials=6&set.sart.maskMs=100&set.sart.countdownMs=200"
        "&set.sart.feedbackMs=40&set.sart.measureFrames=12")
FAST18 = FAST.replace("practiceTrials=6", "practiceTrials=18")
SLOW = FAST.replace("maskMs=100", "maskMs=1200")  # the real mask: a trial is 1.45 s, long enough to be caught by a wait

PHASES = """() => {
    window.__phases = [];
    window.__hints = [];
    new MutationObserver(() => {
        const stage = document.querySelector('.sart-run');
        if (!stage) return;
        const last = window.__phases[window.__phases.length - 1];
        if (!last || last[0] !== stage.dataset.phase || last[2] !== stage.dataset.trial) {
            window.__phases.push([stage.dataset.phase, performance.now(), stage.dataset.trial, stage.dataset.feedback ?? null]);
            const hint = [...stage.querySelectorAll('.sart-hint text')].map(t => t.textContent).join(' ');
            if (stage.dataset.phase === 'feedback') window.__hints.push(hint);
        }
    }).observe(document.body, { subtree: true, childList: true, attributes: true,
        attributeFilter: ['data-phase', 'data-trial', 'data-feedback'] });
}"""


def load_tool():
    spec = importlib.util.spec_from_file_location("sart_sequence", APP / "tools" / "sart_sequence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digits(items):
    return [t[0] for t in items]


class SequenceTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_main_part_225_trials_every_digit_25_times_no_digit_twice_in_a_row(self):
        self.assertEqual(len(MAIN), 225)
        for d in range(1, 10):
            self.assertEqual(digits(MAIN).count(d), 25, d)
        self.assertEqual(digits(MAIN).count(3) / 225, 25 / 225)  # 11% threes
        self.assertFalse(any(a[0] == b[0] for a, b in zip(MAIN, MAIN[1:])))

    def test_every_digit_in_every_size_five_times_and_every_block_of_45_is_balanced(self):
        for d in range(1, 10):
            for s in range(5):
                self.assertEqual(MAIN.count([d, s]), 5, (d, s))  # the 3 in all five sizes
        for start in range(0, 225, 45):
            block = MAIN[start:start + 45]
            self.assertEqual(sorted(map(tuple, block)), sorted((d, s) for d in range(1, 10) for s in range(5)), start)

    def test_no_more_than_three_trials_of_one_size_in_a_row(self):
        run = best = 0
        for a, b in zip([None] + MAIN, MAIN):
            run = run + 1 if a is not None and a[1] == b[1] else 1
            best = max(best, run)
        self.assertLessEqual(best, 3)

    def test_the_practice_lists(self):
        self.assertEqual(len(PRACTICE), 2)  # the second is for the repeat
        for items in PRACTICE:
            self.assertEqual(len(items), 18)
            for d in range(1, 10):
                self.assertEqual(digits(items).count(d), 2, d)  # two threes among them
            self.assertFalse(any(a[0] == b[0] for a, b in zip(items, items[1:])))
            sizes = [t[1] for t in items]
            self.assertTrue(all(3 <= sizes.count(s) <= 4 for s in range(5)))
            threes = [i for i, t in enumerate(items) if t[0] == 3]
            self.assertGreaterEqual(threes[0], 3)
            self.assertGreaterEqual(threes[1] - threes[0], 4)
        self.assertNotEqual(PRACTICE[0], PRACTICE[1])

    def test_the_file_is_what_the_generator_writes_and_fits_the_look(self):
        self.assertEqual(self.tool.generate(), SEQUENCE)
        self.assertEqual(self.tool.check(SEQUENCE), [])
        self.assertEqual(SEQUENCE["look_version"], LOOK["look_version"])
        self.assertEqual(SEQUENCE["sequence_version"], 1)
        self.assertEqual(SEQUENCE["nogo_digit"], 3)
        self.assertEqual(SEQUENCE["sizes"], len(LOOK["digit_cap_mm"]))

    def test_the_look_is_variant_1_of_the_candidates(self):
        # Decision 156: the author chose variant 1.
        variant = next(v for v in CANDIDATES["variants"] if v["id"] == "1")
        self.assertEqual(LOOK["variant"], "1")
        for key, value in variant.items():
            if key not in ("id", "name"):
                self.assertEqual(LOOK[key], value, key)
        self.assertEqual(LOOK["area"], {"w": 240, "h": 150})
        # The five sizes keep the proportions of the original font sizes (48, 72, 94, 100, 120 pt).
        for mm, pt in zip(LOOK["digit_cap_mm"], LOOK["original_pt"]):
            self.assertAlmostEqual(mm / LOOK["digit_cap_mm"][-1], pt / 120, delta=0.01)
        self.assertLess(max(LOOK["digit_cap_mm"]), 150 * 0.3)  # the biggest digit leaves room in the area
        self.assertGreaterEqual(LOOK["mask_mm"], max(LOOK["digit_cap_mm"]))  # the mask covers it

    def test_the_checker_catches_broken_sequences(self):
        main = [list(t) for t in MAIN]
        same = [list(t) for t in main]
        same[1][0] = same[0][0]  # the digit twice in a row
        self.assertTrue(self.tool.problems_in_main(same))
        self.assertTrue(self.tool.problems_in_main(main[:-1]))
        swapped = [list(t) for t in main]
        swapped[0], swapped[100] = swapped[100], swapped[0]  # the counts hold, the blocks do not
        self.assertTrue(self.tool.problems_in_main(swapped))
        size = [list(t) for t in main]
        size[0][1] = (size[0][1] + 1) % 5  # a pair appears twice in a block
        self.assertTrue(self.tool.problems_in_main(size))
        practice = [list(t) for t in PRACTICE[0]]
        self.assertEqual(self.tool.problems_in_practice(practice), [])
        practice[3][0] = practice[2][0]
        self.assertTrue(self.tool.problems_in_practice(practice))
        self.assertTrue(self.tool.problems_in_practice(practice[:-1]))


class ScoreTest(AppTestCase):
    SUMMARIZE = "args => import('./src/sart/score.js').then(m => m.summarize(args.trials, args.limits))"
    LIMITS = {"digitMs": 250}

    def trial(self, type_, rt=None, digit_ms=250, mask_ms=1200, fast=0, extra=0):
        return {"type": type_, "rt_ms": rt, "digit_ms": digit_ms, "mask_ms": mask_ms, "fast_n": fast, "extra_n": extra}

    def summarize(self, page, trials):
        return page.evaluate(self.SUMMARIZE, {"trials": trials, "limits": self.LIMITS})

    def test_commissions_omissions_rates_and_the_reaction_time_of_the_hits(self):
        trials = [
            self.trial("hit", 300), self.trial("hit", 400), self.trial("hit", 500),
            self.trial("omission"),
            self.trial("commission", 250),  # the press on a 3 is no hit and its time is not in the mean
            self.trial("withhold"),
            self.trial("withhold", fast=2), self.trial("hit", 500, extra=1),
        ]
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                r = self.summarize(page, trials)
                self.assertEqual((r["hit_n"], r["omission_n"], r["commission_n"], r["withhold_n"]), (4, 1, 1, 2))
                self.assertEqual((r["go_n"], r["nogo_n"]), (5, 3))
                self.assertEqual(r["omission_rate"], 0.2)  # of the digits other than 3
                self.assertEqual(r["commission_rate"], 0.333)  # of the 3s
                self.assertEqual(r["rt_mean_ms"], 425)
                self.assertAlmostEqual(r["rt_sd_ms"], 95.7, delta=0.05)  # sample SD of 300, 400, 500, 500
                self.assertAlmostEqual(r["rt_cv"], 0.225, delta=0.001)
                self.assertEqual((r["fast_n"], r["extra_n"]), (2, 1))

    def test_the_reaction_time_values_are_empty_without_hits(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                r = self.summarize(page, [self.trial("omission"), self.trial("withhold")])
                self.assertIsNone(r["rt_mean_ms"])
                self.assertIsNone(r["rt_sd_ms"])
                self.assertIsNone(r["rt_cv"])
                one = self.summarize(page, [self.trial("hit", 300)])
                self.assertEqual(one["rt_mean_ms"], 300)
                self.assertIsNone(one["rt_sd_ms"])  # a SD needs two values
                empty = self.summarize(page, [])
                self.assertIsNone(empty["omission_rate"])
                self.assertIsNone(empty["digit_mean_ms"])

    def test_the_deviation_of_the_digit_time_from_250_ms(self):
        trials = [self.trial("hit", 300, digit_ms=250), self.trial("hit", 300, digit_ms=252), self.trial("hit", 300, digit_ms=233.3)]
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                r = self.summarize(page, trials)
                self.assertEqual(r["digit_mean_ms"], 245.1)
                self.assertEqual(r["digit_dev_mean_ms"], 6.2)  # (0 + 2 + 16.7) / 3
                self.assertEqual(r["digit_dev_max_ms"], 16.7)
                self.assertEqual(r["mask_mean_ms"], 1200)

    def test_which_outcome_a_press_gives(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                got = page.evaluate("""() => import('./src/sart/score.js').then(m => [
                    m.outcomeOf(3, true, 3), m.outcomeOf(3, false, 3), m.outcomeOf(7, true, 3), m.outcomeOf(7, false, 3)])""")
                self.assertEqual(got, ["commission", "withhold", "hit", "omission"])

    def test_the_number_of_frames_follows_the_frame_time(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                plan = lambda ms: page.evaluate(
                    "ms => import('./src/sart/score.js').then(m => m.planFrames(ms, { digitMs: 250, maskMs: 1200 }))", ms)
                self.assertEqual(plan(1000 / 60), {"digit": 15, "total": 87})  # 250 ms and 1450 ms on 60 Hz
                self.assertEqual(plan(1000 / 120), {"digit": 30, "total": 174})  # and on 120 Hz
                self.assertEqual(plan(1000 / 144), {"digit": 36, "total": 209})
                self.assertEqual(plan(1000 / 59.94), {"digit": 15, "total": 87})
                self.assertEqual(plan(1000 / 75), {"digit": 19, "total": 109})

    def test_the_frame_time_is_the_median_gap_and_ignores_a_few_slow_frames(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                frame = lambda stamps: page.evaluate(
                    "stamps => import('./src/sart/score.js').then(m => m.frameTimeFrom(stamps))", stamps)
                clean = [i * 8.3333 for i in range(45)]
                self.assertAlmostEqual(frame(clean), 8.3333, delta=0.001)
                slow = list(clean)
                for i in range(20, 45):  # two stalls of 100 ms
                    slow[i] += 100 if i < 30 else 200
                self.assertAlmostEqual(frame(slow), 8.3333, delta=0.001)
                self.assertIsNone(frame(clean[:8]))  # too few frames
                self.assertIsNone(frame([i * 100 for i in range(45)]))  # 10 Hz: no screen


class SartTestCase(AppTestCase):
    def open_sart(self, browser, extra=FAST, retest=False, tracked=False, **options):
        context, receiver = self.new_context(browser, **options)
        link = f"?mode=dev&only=sart{'&r=' + CODE if retest else ''}{extra}"
        page, errors = self.open(browser, link, context=context)
        page.get_by_role("button", name="Почати тренування").wait_for()
        if tracked:
            page.evaluate(PHASES)
        return page, errors, context, receiver

    def result(self, page, receiver):
        """Waits for the end of the block; returns (summary, log) of its message."""
        page.locator(".dev-end").wait_for()
        self.wait_delivered(page)
        [message] = [m for m in receiver.accepted if m["block"] == "sart"]
        return message["summary"], message["log"]

    def main_part(self, page, **plan):
        """The bot through the main part; waits for the end of the run."""
        self.bot_sart(page, **plan)

    def shown(self, page, trial=None):
        selector = ".sart-run[data-shown='1']" + (f"[data-trial='{trial}']" if trial is not None else "")
        page.locator(selector).wait_for()


class LookTest(SartTestCase):
    def test_the_screen_is_white_in_mm_with_five_digit_sizes_in_the_proportions_of_the_original(self):
        sizes = """() => new Promise(resolve => {
            const seen = {};
            const stage = document.querySelector('.sart-run');
            const read = () => {
                const digit = stage.querySelector('.sart-digit');
                if (digit) seen[digit.dataset.size] = [Number(digit.getAttribute('font-size')),
                    digit.getBoundingClientRect().height, digit.getBBox().x + digit.getBBox().width / 2];
                if (!document.querySelector('.sart-run')) return;
                if (Object.keys(seen).length === 5) { obs.disconnect(); resolve(seen); }
            };
            const obs = new MutationObserver(read);
            obs.observe(stage, { subtree: true, childList: true });
            setTimeout(() => { obs.disconnect(); resolve(seen); }, 40000);
        })"""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_sart(browser, FAST + "&set.sart.practiceTrials=18")
                px = page.evaluate("() => window.tmtua.ctx.scale().pxPerMm")
                page.get_by_role("button", name="Почати тренування").click()
                page.locator(".sart-run").wait_for()
                self.assertEqual(page.evaluate("() => getComputedStyle(document.querySelector('.sart-run')).backgroundColor"),
                                 "rgb(255, 255, 255)")
                area = page.locator(".sart-area").bounding_box()
                self.assertAlmostEqual(area["width"], 240 * px, delta=1)
                self.assertAlmostEqual(area["height"], 150 * px, delta=1)
                seen = page.evaluate(sizes)
                self.assertEqual(sorted(seen), ["0", "1", "2", "3", "4"])
                cap = 0.7  # Montserrat: capital height as a share of the font size (fonts.json)
                for size, (font_size, _, centre) in seen.items():
                    self.assertAlmostEqual(font_size * cap, LOOK["digit_cap_mm"][int(size)], delta=0.1)  # the height in mm
                    self.assertAlmostEqual(centre, 120, delta=2)  # centred horizontally on the area
                largest = seen["4"][0]
                for size, pt in enumerate(LOOK["original_pt"]):
                    self.assertAlmostEqual(seen[str(size)][0] / largest, pt / 120, delta=0.01)
                self.assertEqual(errors, [])

    def test_the_mask_is_a_ring_with_a_cross_of_44_mm_in_the_middle(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                # the real mask (1.2 s): with the short test mask the wait can miss it on a busy machine
                page, errors, _, _ = self.open_sart(browser, SLOW)
                self.start_sart_training(page)
                page.locator(".sart-run[data-phase='mask']").wait_for()
                box = page.locator(".sart-mask").evaluate("g => { const b = g.getBBox(); return [b.x + b.width / 2, b.y + b.height / 2, b.width]; }")
                self.assertAlmostEqual(box[0], 120, delta=0.5)
                self.assertAlmostEqual(box[1], 75, delta=0.5)
                self.assertAlmostEqual(box[2], 44 - 1.2, delta=0.5)  # the ring without its line width
                self.assertEqual(page.locator(".sart-mask circle").count(), 1)
                self.assertEqual(page.locator(".sart-mask path").count(), 1)  # the two diagonals
                self.assertEqual(page.locator(".sart-digit").count(), 0)  # a digit and the mask are never together
                self.assertEqual(errors, [])


class FramesTest(SartTestCase):
    def run_main(self, browser, extra=FAST):
        page, errors, context, receiver = self.open_sart(browser, extra)
        self.start_sart(page)
        self.bot_sart(page)
        summary, log = self.result(page, receiver)
        return page, errors, summary, log

    def test_the_digit_is_15_frames_and_250_ms_on_a_60_hz_screen(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                _, errors, summary, log = self.run_main(browser)
                timing = log["main"]["timing"]
                self.assertTrue(timing["measure_ok"])
                self.assertGreater(timing["refresh_hz"], 55)
                self.assertLess(timing["refresh_hz"], 65)
                self.assertEqual(timing["digit_frames"], 15)
                self.assertEqual(summary["sart_digit_frames"], 15)
                self.assertEqual(timing["total_frames"], round(350 / timing["frame_ms"]))  # with the short test mask
                for trial in log["main"]["trials"]:
                    self.assertAlmostEqual(trial["digit_ms"], 250, delta=17, msg=trial)  # within a frame
                    self.assertAlmostEqual(trial["mask_ms"], 100, delta=17, msg=trial)
                self.assertLess(summary["sart_digit_dev_mean_ms"], 5)
                self.assertAlmostEqual(summary["sart_digit_mean_ms"], 250, delta=5)
                self.assertEqual(errors, [])

    def test_a_faked_120_hz_screen_gets_30_frames_for_the_same_250_ms(self):
        # The screen of the test is 60 Hz; the measured frame time is replaced, so the plan is
        # the one of a 120 Hz screen: 30 frames of 8.33 ms. The picture changes only on real
        # frames, so the time stays 250 ms.
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                _, errors, summary, log = self.run_main(browser, FAST + "&set.sart.frameMsOverride=8.3333")
                timing = log["main"]["timing"]
                self.assertEqual(timing["digit_frames"], 30)
                self.assertEqual(timing["total_frames"], 42)  # 350 ms with the short mask
                self.assertEqual(timing["override_ms"], 8.3333)
                self.assertGreater(timing["refresh_hz"], 55)  # what was measured is still recorded
                self.assertEqual(summary["sart_digit_frames"], 30)
                for trial in log["main"]["trials"]:
                    self.assertAlmostEqual(trial["digit_ms"], 250, delta=17, msg=trial)
                self.assertEqual(errors, [])

    def test_a_trial_lasts_1450_ms_with_the_real_mask(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_sart(browser, FAST.replace("maskMs=100", "maskMs=1200") + "&set.sart.mainTrials=8")
                self.start_sart(page)
                self.bot_sart(page)
                summary, log = self.result(page, receiver)
                trials = log["main"]["trials"]
                for first, second in zip(trials, trials[1:]):
                    self.assertAlmostEqual(second["t_ms"] - first["t_ms"], 1450, delta=20)
                    self.assertAlmostEqual(first["digit_ms"], 250, delta=17)
                    self.assertAlmostEqual(first["mask_ms"], 1200, delta=20)
                self.assertAlmostEqual(summary["sart_time_ms"], 8 * 1450, delta=60)
                self.assertEqual(errors, [])

    def test_the_whole_main_part_of_225_trials_in_real_time(self):
        # 225 x 1.45 s = 5.4 minutes, so only in the first browser.
        browser = self.browsers[0]
        page, errors, context, receiver = self.open_sart(browser, FAST + "&set.sart.maskMs=1200&set.sart.mainTrials=225&set.sart.countdownMs=3000&set.sart.measureFrames=40")
        self.start_sart(page)
        self.bot_sart(page, delay=400)
        summary, log = self.result(page, receiver)
        trials = log["main"]["trials"]
        self.assertEqual(len(trials), 225)
        self.assertEqual([[t["digit"], t["size"]] for t in trials], MAIN)
        self.assertAlmostEqual(summary["sart_time_ms"], 225 * 1450, delta=2000)  # a frame of 16.69 ms (59.9 Hz) makes the trial 1451.6 ms
        self.assertEqual((summary["sart_hit_n"], summary["sart_omission_n"], summary["sart_commission_n"], summary["sart_withhold_n"]),
                         (200, 0, 0, 25))
        self.assertLess(summary["sart_digit_dev_mean_ms"], 3)
        # A busy machine may drop a frame now and then (the real time is recorded, so it shows):
        # not more than a few digits off by more than a frame, none by more than six frames.
        off = [(t["i"], t["digit_ms"], t["mask_ms"]) for t in trials if abs(t["digit_ms"] - 250) > 17]
        self.assertLessEqual(len(off), 3, off)
        self.assertLess(summary["sart_digit_dev_max_ms"], 100, off)
        self.assertEqual(errors, [])

    def test_the_countdown_is_three_seconds_of_text_and_a_bar_without_digits(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_sart(browser, FAST + "&set.sart.countdownMs=3000", tracked=True)
                self.start_sart_training(page)
                self.bot_sart(page)
                page.get_by_role("button", name="Почати", exact=True).click()
                page.locator(".sart-run[data-phase='prepare']").wait_for()
                self.assertEqual(page.locator(".sart-countdown text").text_content(), "Приготуйтеся…")
                page.wait_for_timeout(1500)
                share = page.locator(".sart-bar").evaluate("e => Number(e.getAttribute('width')) / 80")
                self.assertAlmostEqual(share, 0.5, delta=0.15)  # the bar shrinks over the three seconds
                self.assertEqual(page.locator(".sart-digit").count(), 0)  # no digits
                page.locator(".sart-run[data-phase='digit']").wait_for()
                when = {(p[0], p[2]): p[1] for p in page.evaluate("window.__phases")}
                self.assertAlmostEqual(when[("digit", "0")] - when[("prepare", None)], 3000, delta=200)
                self.assertEqual(page.locator(".sart-countdown text").count(), 0)  # the countdown is gone
                self.bot_sart(page)
                self.assertEqual(errors, [])


class KeysTest(SartTestCase):
    def test_a_real_space_press_is_a_response_and_on_a_3_a_false_response(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, SLOW)
                self.start_sart(page)
                self.shown(page, 0)  # the first digit of the main part is a 3
                self.assertEqual(MAIN[0][0], 3)
                page.wait_for_timeout(150)  # a press sooner than 100 ms after the digit is no answer
                page.keyboard.press("Space")
                self.shown(page, 1)
                self.assertNotEqual(MAIN[1][0], 3)
                page.wait_for_timeout(150)
                page.keyboard.press("Space")
                self.bot_sart(page, omit=list(range(1, 12)), press3=[])
                summary, log = self.result(page, receiver)
                trials = log["main"]["trials"]
                self.assertEqual((trials[0]["type"], trials[1]["type"]), ("commission", "hit"))
                self.assertTrue(trials[0]["pressed"] and trials[0]["rt_ms"] is not None)
                self.assertEqual(summary["sart_commission_n"], 1)
                self.assertEqual(summary["sart_hit_n"], 1)
                self.assertEqual(summary["sart_omission_n"], 10 - sum(1 for t in MAIN[2:12] if t[0] == 3))
                self.assertEqual(errors, [])

    def test_presses_that_are_no_answer_are_logged_with_their_reason(self):
        many = """() => {
            const press = (code, options = {}) => window.dispatchEvent(new KeyboardEvent('keydown',
                { code, key: code, bubbles: true, cancelable: true, ...options }));
            press('Space', { ctrlKey: true });
            press('Space', { metaKey: true });
            press('KeyA');
            press('Enter');
            press('Space', { repeat: true });
        }"""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, SLOW)
                self.start_sart(page)
                self.shown(page, 0)  # a 3: nothing must be pressed
                page.evaluate(many)
                self.bot_sart(page, delay=200, fast={"1": 40}, double=[2], hold=[3])
                summary, log = self.result(page, receiver)
                trials = log["main"]["trials"]
                reasons = [k["reason"] for k in log["main"]["keys"]]
                self.assertEqual(reasons[:5], ["modifier", "modifier", "not_space", "not_space", "repeat"])
                self.assertEqual(trials[0]["type"], "withhold")  # none of them was a press on the 3
                self.assertEqual(trials[1]["type"], "omission")  # a press 40 ms after the digit is no answer
                self.assertEqual(trials[1]["fast_n"], 1)
                self.assertEqual(trials[2]["type"], "hit")
                self.assertEqual(trials[2]["extra_n"], 1)  # the second press of the trial
                self.assertEqual(trials[3]["type"], "hit")
                self.assertEqual(trials[3]["extra_n"], 0)  # held down: the repeat is no press
                self.assertEqual((summary["sart_fast_n"], summary["sart_extra_n"]), (1, 1))
                by_reason = {}
                for k in log["main"]["keys"]:
                    by_reason.setdefault(k["reason"], []).append(k)
                self.assertEqual(len(by_reason["fast"]), 1)
                self.assertLess(by_reason["fast"][0]["rt_ms"], 100)
                self.assertEqual(len(by_reason["second"]), 1)
                self.assertEqual(by_reason["second"][0]["i"], 2)
                self.assertEqual(len(by_reason["repeat"]), 2)  # the one sent by hand and the held one
                self.assertEqual(errors, [])

    def test_a_press_in_the_countdown_is_no_answer(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, SLOW + "&set.sart.countdownMs=1500")
                self.start_sart_training(page)
                self.bot_sart(page)
                page.get_by_role("button", name="Почати", exact=True).click()
                page.locator(".sart-run[data-phase='prepare']").wait_for()
                self.sart_press(page)
                self.bot_sart(page)
                summary, log = self.result(page, receiver)
                self.assertEqual([k["reason"] for k in log["main"]["keys"]], ["before_start"])
                self.assertEqual(log["main"]["trials"][0]["type"], "withhold")
                self.assertEqual(errors, [])

    def test_the_space_bar_is_kept_from_scrolling_and_from_pressing_a_button(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_sart(browser, SLOW)
                self.start_sart_training(page)
                got = page.evaluate("""() => {
                    const down = new KeyboardEvent('keydown', { code: 'Space', cancelable: true });
                    const up = new KeyboardEvent('keyup', { code: 'Space', cancelable: true });
                    const other = new KeyboardEvent('keydown', { code: 'KeyA', cancelable: true });
                    window.dispatchEvent(down); window.dispatchEvent(up); window.dispatchEvent(other);
                    return [down.defaultPrevented, up.defaultPrevented, other.defaultPrevented,
                            document.activeElement === document.body];
                }""")
                self.assertEqual(got, [True, True, False, True])  # no button holds the focus
                self.bot_sart(page)
                self.assertEqual(errors, [])


class TrainingTest(SartTestCase):
    def test_a_missed_digit_and_a_press_on_the_3_show_their_hint_under_the_mask_after_the_trial(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_sart(browser, FAST + "&set.sart.maskMs=1200&set.sart.feedbackMs=400", tracked=True)
                self.assertEqual(PRACTICE[0][3][0], 3)
                self.start_sart_training(page)
                self.bot_sart(page, omit=[0], press3=[3])
                page.get_by_role("button", name="Почати", exact=True).wait_for()
                self.assertEqual(page.evaluate("window.__hints"), ["Ви не натиснули пробіл.", "Це була 3, на неї не натискайте."])
                phases = page.evaluate("window.__phases")
                names = [(p[0], p[2]) for p in phases]
                self.assertEqual(names[:6], [("prepare", None), ("digit", "0"), ("mask", "0"), ("feedback", "0"), ("digit", "1"), ("mask", "1")])
                when = {(p[0], p[2]): p[1] for p in phases}
                self.assertAlmostEqual(when[("feedback", "0")] - when[("digit", "0")], 1450, delta=80)  # after the trial
                self.assertAlmostEqual(when[("digit", "1")] - when[("feedback", "0")], 400, delta=80)  # the pause
                kinds = [p[3] for p in phases if p[0] == "feedback"]
                self.assertEqual(kinds, ["omission", "commission"])
                self.assertEqual(errors, [])

    def test_the_hint_is_grey_5_mm_and_under_the_mask(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_sart(browser, FAST + "&set.sart.maskMs=300&set.sart.feedbackMs=1500")
                self.start_sart_training(page)
                page.locator(".sart-run[data-phase='feedback']").wait_for()  # the first digit is not pressed
                self.assertEqual(page.locator(".sart-mask").count(), 1)  # the mask stays
                hint = page.locator(".sart-hint text").first
                self.assertEqual(hint.text_content(), "Ви не натиснули пробіл.")
                self.assertEqual(hint.get_attribute("fill"), "#6B6B6B")
                self.assertAlmostEqual(float(hint.get_attribute("y")) - 75, 50 + 2.5, delta=0.5)  # 50 mm below the middle
                self.bot_sart(page)
                self.assertEqual(errors, [])

    def test_no_hint_for_right_answers_and_no_rightly_message(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_sart(browser, FAST18, tracked=True)
                self.start_sart_training(page)
                self.bot_sart(page)
                page.get_by_role("button", name="Почати", exact=True).wait_for()
                self.assertEqual(page.evaluate("window.__hints"), [])
                self.assertFalse([p for p in page.evaluate("window.__phases") if p[0] == "feedback"])
                self.assertNotIn("Правильно", page.content())
                self.assertEqual(errors, [])

    def omissions(self, items, count):
        return [i for i, t in enumerate(items) if t[0] != 3][:count]

    def test_nine_misses_of_sixteen_mean_one_repeat_with_the_other_list_then_the_main_part_in_any_case(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, FAST18)
                self.start_sart(page, omit_trials=self.omissions(PRACTICE[0], 9), repeat=True)
                self.bot_sart(page)
                summary, log = self.result(page, receiver)
                attempts = log["practice"]["attempts"]
                self.assertEqual(len(attempts), 2)
                self.assertEqual(summary["sart_practice_attempts_n"], 2)
                self.assertEqual(summary["sart_practice_omissions_1"], 9)
                self.assertEqual(summary["sart_practice_omissions_2"], 0)
                self.assertEqual([[t["digit"], t["size"]] for t in attempts[0]["trials"]], PRACTICE[0])
                self.assertEqual([[t["digit"], t["size"]] for t in attempts[1]["trials"]], PRACTICE[1])  # another list
                self.assertEqual(summary["sart_hit_n"] + summary["sart_withhold_n"], 12)  # the main part ran
                self.assertEqual(errors, [])

    def test_the_repeat_screen_text_and_that_the_main_part_follows_even_after_a_failed_repeat(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, FAST18)
                self.start_sart_training(page)
                self.bot_sart(page, omit=self.omissions(PRACTICE[0], 12))
                page.get_by_text("Потренуймося ще раз. Натискайте пробіл на кожну цифру, крім 3.").wait_for()
                page.get_by_role("button", name="Почати тренування").click()
                page.locator(".sart-run").wait_for()
                self.bot_sart(page, omit=self.omissions(PRACTICE[1], 16))  # the repeat fails too
                page.get_by_text("Тренування завершено.").wait_for()  # no second repeat: on to the main part
                page.get_by_role("button", name="Почати", exact=True).click()
                self.bot_sart(page)
                summary, _ = self.result(page, receiver)
                self.assertEqual(summary["sart_practice_attempts_n"], 2)
                self.assertGreaterEqual(summary["sart_practice_omissions_2"], 9)
                self.assertEqual(errors, [])

    def test_eight_misses_and_all_the_false_responses_do_not_repeat_the_training(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                for plan in ({"omit": self.omissions(PRACTICE[0], 8)}, {"press3": [i for i, t in enumerate(PRACTICE[0]) if t[0] == 3]}):
                    page, errors, _, receiver = self.open_sart(browser, FAST18)
                    self.start_sart_training(page)
                    self.bot_sart(page, **plan)
                    page.get_by_text("Тренування завершено.").wait_for()  # straight to the main part
                    page.get_by_role("button", name="Почати", exact=True).click()
                    self.bot_sart(page)
                    summary, _ = self.result(page, receiver)
                    self.assertEqual(summary["sart_practice_attempts_n"], 1, plan)
                    self.assertIsNone(summary["sart_practice_omissions_2"])
                    page.context.close()  # a page in the background gets no animation frames in WebKit

    def test_the_practice_is_18_trials_with_two_3s_and_the_default_threshold_is_nine(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _, _, _ = self.open_sart(browser, "")
                params = page.evaluate("() => window.tmtuaParams.sart")
                self.assertEqual((params["practiceTrials"], params["practiceRepeatAtOmissions"], params["mainTrials"]), (18, 9, 225))
                self.assertEqual((params["digitMs"], params["maskMs"], params["countdownMs"], params["fastMs"]), (250, 1200, 3000, 100))
                self.assertEqual(params["feedbackMs"], 1500)
                self.assertEqual(params["frameMsOverride"], 0)


class MainPartTest(SartTestCase):
    def test_the_counts_the_rates_and_the_reaction_time_follow_the_answers(self):
        n = 40
        threes = [i for i, t in enumerate(MAIN[:n]) if t[0] == 3]
        others = [i for i, t in enumerate(MAIN[:n]) if t[0] != 3]
        press3 = threes[:2]  # two false responses
        omit = others[3:8]  # five misses
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, FAST + f"&set.sart.mainTrials={n}")
                self.start_sart(page)
                self.bot_sart(page, press3=press3, omit=omit, delay=200)
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["sart_commission_n"], 2)
                self.assertEqual(summary["sart_omission_n"], 5)
                self.assertEqual(summary["sart_withhold_n"], len(threes) - 2)
                self.assertEqual(summary["sart_hit_n"], len(others) - 5)
                self.assertEqual(summary["sart_commission_rate"], round(2 / len(threes), 3))
                self.assertEqual(summary["sart_omission_rate"], round(5 / len(others), 3))
                hits = [t["rt_ms"] for t in log["main"]["trials"] if t["type"] == "hit"]
                self.assertEqual(len(hits), summary["sart_hit_n"])
                self.assertAlmostEqual(summary["sart_rt_mean_ms"], statistics.mean(hits), delta=0.1)
                self.assertAlmostEqual(summary["sart_rt_sd_ms"], statistics.stdev(hits), delta=0.1)
                self.assertAlmostEqual(summary["sart_rt_cv"], statistics.stdev(hits) / statistics.mean(hits), delta=0.001)
                self.assertAlmostEqual(summary["sart_rt_mean_ms"], 200, delta=45)  # the press was 200 ms after the digit
                self.assertEqual(len(log["main"]["trials"]), n)
                types = [t["type"] for t in log["main"]["trials"]]
                for i in press3:
                    self.assertEqual(types[i], "commission")
                for i in omit:
                    self.assertEqual(types[i], "omission")
                self.assertEqual(errors, [])

    def test_the_reaction_time_runs_from_the_drawn_digit_to_the_press(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, SLOW + "&set.sart.mainTrials=6")
                self.start_sart(page)
                self.bot_sart(page, delay=500)
                summary, log = self.result(page, receiver)
                for t in log["main"]["trials"]:
                    if t["type"] == "hit":
                        self.assertAlmostEqual(t["rt_ms"], 500, delta=40, msg=t)  # not from the start of the run, not from the previous digit
                self.assertAlmostEqual(summary["sart_rt_mean_ms"], 500, delta=40)
                self.assertEqual(errors, [])

    def test_no_hint_and_no_pause_in_the_main_part_even_after_errors(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, FAST + "&set.sart.feedbackMs=900")
                self.start_sart(page)
                page.evaluate(PHASES)
                self.bot_sart(page, omit=[1, 2, 3], press3=[0])
                summary, log = self.result(page, receiver)
                self.assertFalse([p for p in page.evaluate("window.__phases") if p[0] == "feedback"])
                self.assertEqual(page.evaluate("window.__hints"), [])
                self.assertAlmostEqual(summary["sart_time_ms"], 12 * 350, delta=60)  # 900 ms of pause nowhere
                self.assertEqual(errors, [])

    def test_the_sequence_is_the_fixed_one_and_every_trial_is_logged(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, FAST + "&set.sart.mainTrials=30")
                self.start_sart(page)
                self.bot_sart(page)
                summary, log = self.result(page, receiver)
                trials = log["main"]["trials"]
                self.assertEqual([[t["digit"], t["size"]] for t in trials], MAIN[:30])
                self.assertEqual([t["size_mm"] for t in trials], [LOOK["digit_cap_mm"][t[1]] for t in MAIN[:30]])
                for t in trials:
                    for key in ("i", "digit", "size", "size_mm", "type", "pressed", "rt_ms", "t_ms", "digit_ms", "mask_ms", "fast_n", "extra_n"):
                        self.assertIn(key, t)
                    self.assertIsNotNone(t["digit_ms"])
                    self.assertIsNotNone(t["mask_ms"])
                self.assertEqual(trials[0]["t_ms"], 0)
                self.assertEqual(log["sequence"], {"version": 1, "seed": SEQUENCE["seed"], "main_length": 225, "nogo_digit": 3})
                self.assertEqual(errors, [])

    def test_the_run_is_in_the_during_test_span_of_the_log(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_sart(browser, SLOW + "&set.sart.countdownMs=700")
                self.start_sart_training(page)
                self.bot_sart(page)
                page.get_by_role("button", name="Почати", exact=True).click()
                page.locator(".sart-run[data-phase='prepare']").wait_for()
                page.evaluate("() => window.dispatchEvent(new Event('blur'))")  # in the countdown: outside the span
                page.wait_for_timeout(100)
                page.evaluate("() => window.dispatchEvent(new Event('focus'))")
                self.shown(page, 0)
                page.evaluate("() => window.dispatchEvent(new Event('blur'))")  # in the main part itself
                page.wait_for_timeout(200)
                page.evaluate("() => window.dispatchEvent(new Event('focus'))")
                self.bot_sart(page)
                summary, log = self.result(page, receiver)
                during = log["main"]["during_test"]
                self.assertEqual(during["blur_n"], 1)
                self.assertGreaterEqual(during["blur_ms"], 150)
                self.assertEqual(summary["sart_blur_n"], 2)  # the whole block
                self.assertEqual(summary["sart_test_blur_n"], 1)  # decision 168: the main part only
                self.assertEqual(summary["sart_test_blur_ms"], during["blur_ms"])
                for key in ("hidden_n", "hidden_ms", "fs_exit_n", "fs_exit_ms"):
                    self.assertEqual(summary[f"sart_test_{key}"], 0, key)
                self.assertEqual(errors, [])


class DevPagesTest(AppTestCase):
    def test_the_looks_page_shows_the_variants_and_sends_nothing(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, "?mode=dev&tool=sart", context=context)
                page.locator(".sart-variant").first.wait_for()
                self.assertEqual(page.locator(".sart-variant").count(), 3)
                self.assertEqual(page.locator(".sart-variant .sart-sizes .sart-cell").count(), 3 * 10)  # 3 and 8 in five sizes
                self.assertEqual(page.locator(".sart-variant").first.locator(".sart-figure").count(), 6)
                page.wait_for_timeout(300)
                self.assertEqual(receiver.accepted, [])
                self.assertEqual(errors, [])

    def test_the_timing_page_runs_60_trials_and_reports_the_frames(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, "?mode=dev&tool=sart-timing&set.sart.maskMs=100&set.sart.countdownMs=200&set.sart.measureFrames=12", context=context)
                page.locator("#sart-timing-start").click()
                page.locator("#sart-timing-text").wait_for(timeout=60000)
                text = page.locator("#sart-timing-text").input_value()
                self.assertIn("measured frame", text)
                self.assertIn("plan: digit 15 frames", text)
                self.assertIn("digit ms: mean 25", text)
                result = page.evaluate("window.tmtuaSartTiming")
                self.assertEqual(len(result["trials"]), 60)
                self.assertEqual(result["digit_frames"], 15)
                self.assertEqual(receiver.accepted, [])
                self.assertEqual(errors, [])


class SessionTest(SartTestCase):
    def test_the_block_is_a_task_with_a_fullscreen_gate_and_the_same_in_the_retest(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                first = {b[0]: b for b in self.session_blocks(page)}
                retest = {b[0]: b for b in self.session_blocks(page, retest=True)}
                self.assertFalse(first["sart"][2])  # no longer a placeholder
                self.assertFalse(retest["sart"][2])
                self.assertFalse([b for b in self.session_blocks(page) if b[2]])  # no placeholder is left
                self.assertEqual(page.evaluate(
                    "import('./src/blocks.js').then(m => [m.BLOCKS, m.RETEST_BLOCKS].map(l => l.find(b => b.id === 'sart').isTask))"),
                    [True, True])
                ids = [b[0] for b in self.session_blocks(page)]
                self.assertEqual(ids.index("sart"), ids.index("stroop") + 1)

    def test_the_instruction_starts_with_the_end_of_stroop_and_the_texts_are_those_of_the_draft(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_sart(browser)
                text = page.locator(".screen").inner_text()
                self.assertTrue(text.startswith("Тест Струпа завершено."), text)
                self.assertIn("Завдання з цифрами", text)
                self.assertEqual(page.locator(".screen strong").all_inner_texts(), ["Завдання з цифрами", "крім цифри 3"])
                self.assertEqual(errors, [])

    def test_the_retest_has_the_same_look_and_the_same_sequence(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                first = {}
                for retest in (False, True):
                    page, errors, context, receiver = self.open_sart(browser, FAST18, retest=retest)
                    self.start_sart(page, omit_trials=self.omit(9), repeat=True)  # nine misses: the repeat
                    self.bot_sart(page)
                    summary, log = self.result(page, receiver)
                    first[retest] = (log["look"], log["sequence"], [[t["digit"], t["size"]] for t in log["main"]["trials"]],
                                     [[[t["digit"], t["size"]] for t in a["trials"]] for a in log["practice"]["attempts"]],
                                     summary["sart_look_version"], summary["sart_sequence_version"], log["sizes_mm"])
                    context.close()  # a page in the background gets no animation frames in WebKit
                self.assertEqual(first[False], first[True])
                self.assertEqual(first[True][4:6], ("1", "1"))
                self.assertEqual(first[True][2], MAIN[:12])
                self.assertEqual(first[True][3], PRACTICE)

    def omit(self, count):
        return [i for i, t in enumerate(PRACTICE[0]) if t[0] != 3][:count]

    def test_the_summary_has_exactly_the_documented_columns_and_the_receiver_accepts_it(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_sart(browser)
                self.start_sart(page)
                self.bot_sart(page)
                summary, log = self.result(page, receiver)
                own = {k for k in summary if k.startswith("sart_") and not k.startswith(
                    ("sart_hidden", "sart_blur", "sart_fs_exit", "sart_resize", "sart_zoom", "sart_touch", "sart_idle"))}
                self.assertEqual(own, COLUMNS)
                self.assertEqual(summary["sart_look_version"], "1")
                self.assertEqual(summary["sart_sequence_version"], "1")
                self.assertEqual(summary["sart_practice_attempts_n"], 1)
                env = {k for k in summary if k.startswith("sart_") and k not in COLUMNS}
                self.assertEqual(len(env), 11)  # the monitor's columns
                self.assertEqual(log["look"], {"version": 1, "variant": "1", "bg": "#FFFFFF", "fg": "#000000"})
                self.assertEqual(log["sizes_mm"]["digit_cap"], LOOK["digit_cap_mm"])
                self.assertEqual(log["limits"], {"digit_ms": 250, "mask_ms": 100, "feedback_ms": 40, "countdown_ms": 200, "fast_ms": 100, "measure_frames": 12})
                self.assertEqual(log["main"]["timing"]["digit_frames"], 15)
                self.assertEqual(len(log["practice"]["attempts"][0]["trials"]), 6)
                self.assertEqual(log["practice"]["attempts"][0]["timing"]["digit_frames"], 15)
                self.assert_valid_for_receiver(context, [m for m in receiver.accepted if m["block"] == "sart"])
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

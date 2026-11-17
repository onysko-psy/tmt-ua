"""Checks of the Stroop task (task T3.2): the fixed sequences, the scoring of
the Stroop effect, the trial (dot, word, plates, limit, pauses), what counts
as an answer, the training with its feedback and its repeat, the main part,
the same stimuli at the retest, the data sent, and the monitor around the
task. In Chromium and WebKit; the sequence checks need no browser.

Run from the app/ folder: ../.venv/bin/python -m unittest discover -s tests -p "test_stroop.py" -v
"""

import importlib.util
import json
import unittest
from pathlib import Path

from harness import AppTestCase

APP = Path(__file__).resolve().parent.parent
SEQUENCE = json.loads((APP / "stimuli" / "stroop-sequence.json").read_text())
LOOK = json.loads((APP / "stimuli" / "stroop-colors.json").read_text())
CANDIDATES = json.loads((APP / "stimuli" / "stroop-candidates.json").read_text())
CODE = "k3m8q7w2xz"  # a participant code of the first session, for the retest link
ORDER = ["red", "green", "blue", "yellow"]
INSTRUMENTAL = {"red": "червоним", "green": "зеленим", "blue": "синім", "yellow": "жовтим"}
WORD_EM = {"red": 6.164, "green": 5.24, "blue": 3.509, "yellow": 4.907}  # Montserrat SemiBold, width in em

# Columns of the table the block adds besides the 10 of the monitor.
CONDITION_COLUMNS = {f"stroop_{c}_{k}" for c in ("congruent", "incongruent") for k in ("correct_n", "errors_n", "timeouts_n", "rt_ms")}
COLUMNS = CONDITION_COLUMNS | {
    "stroop_practice_attempts_n", "stroop_practice_correct_1", "stroop_practice_correct_2",
    "stroop_colors_version", "stroop_sequence_version",
    "stroop_effect_ms", "stroop_correct_n", "stroop_errors_n", "stroop_timeouts_n",
    "stroop_miss_n", "stroop_time_ms",
    # the exits during the main part itself (decision 168)
    "stroop_test_hidden_n", "stroop_test_hidden_ms", "stroop_test_blur_n", "stroop_test_blur_ms",
    "stroop_test_fs_exit_n", "stroop_test_fs_exit_ms",
}
FAST = "&set.stroop.itiMs=20&set.stroop.feedbackMs=40"

PHASES = """() => {
    window.__phases = [];
    new MutationObserver(() => {
        const stage = document.querySelector('.stroop-run');
        if (!stage) return;
        const last = window.__phases[window.__phases.length - 1];
        if (!last || last[0] !== stage.dataset.phase || last[2] !== stage.dataset.trial)
            window.__phases.push([stage.dataset.phase, performance.now(), stage.dataset.trial]);
    }).observe(document.body, { subtree: true, childList: true, attributes: true,
        attributeFilter: ['data-phase', 'data-trial'] });
}"""


def load_tool():
    spec = importlib.util.spec_from_file_location("stroop_sequence", APP / "tools" / "stroop_sequence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def condition(trial):
    return "congruent" if trial[0] == trial[1] else "incongruent"


def mean(values):
    return sum(values) / len(values)


class SequenceTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_main_part_96_trials_half_congruent_every_word_and_ink_equally_often(self):
        main = SEQUENCE["main"]
        self.assertEqual(len(main), 96)
        self.assertEqual(sum(condition(t) == "congruent" for t in main), 48)
        for color in ORDER:
            self.assertEqual(sum(t[0] == color for t in main), 24, color)
            self.assertEqual(sum(t[1] == color for t in main), 24, color)
            self.assertEqual(sum(t == [color, color] for t in main), 12, color)
        pairs = {(w, i): sum(t == [w, i] for t in main) for w in ORDER for i in ORDER if w != i}
        self.assertEqual(set(pairs.values()), {4})  # every incongruent pair four times

    def test_the_ink_never_repeats_in_a_row_and_the_conditions_are_mixed(self):
        main = SEQUENCE["main"]
        self.assertFalse(any(a[1] == b[1] for a, b in zip(main, main[1:])))
        run = best = 0
        for a, b in zip([None] + main, main):
            run = run + 1 if a is not None and condition(a) == condition(b) else 1
            best = max(best, run)
        self.assertLessEqual(best, 4)

    def test_every_block_of_24_is_balanced(self):
        main = SEQUENCE["main"]
        for start in range(0, 96, 24):
            block = main[start:start + 24]
            self.assertEqual(sum(condition(t) == "congruent" for t in block), 12, start)
            for color in ORDER:
                self.assertEqual(block.count([color, color]), 3, (start, color))
            self.assertEqual(len({tuple(t) for t in block if condition(t) == "incongruent"}), 12, start)

    def test_the_practice_lists(self):
        self.assertEqual(len(SEQUENCE["practice"]), 2)  # the second is for the repeat
        for items in SEQUENCE["practice"]:
            self.assertEqual(len(items), 12)
            self.assertEqual(sum(condition(t) == "congruent" for t in items), 6)
            for color in ORDER:
                self.assertEqual(sum(t[1] == color for t in items), 3, color)  # every colour three times
                self.assertEqual(sum(t[0] == color for t in items), 3, color)
            self.assertFalse(any(a[1] == b[1] for a, b in zip(items, items[1:])))
        self.assertNotEqual(SEQUENCE["practice"][0], SEQUENCE["practice"][1])

    def test_the_file_is_what_the_generator_writes_and_fits_the_colours(self):
        self.assertEqual(self.tool.generate(), SEQUENCE)
        self.assertEqual(self.tool.check(SEQUENCE), [])
        self.assertEqual(SEQUENCE["colors_version"], LOOK["colors_version"])
        self.assertEqual(SEQUENCE["sequence_version"], 1)
        self.assertEqual(SEQUENCE["order"], LOOK["order"])

    def test_the_look_is_variant_1_of_the_candidates(self):
        # Decision 151: the author chose variant 1.
        variant = next(v for v in CANDIDATES["variants"] if v["id"] == "1")
        self.assertEqual(CANDIDATES["chosen"], "1")
        self.assertEqual(LOOK["variant"], "1")
        for key, value in variant.items():
            if key not in ("id", "name"):
                self.assertEqual(LOOK[key], value, key)
        self.assertEqual(LOOK["area"], {"w": 240, "h": 150})

    def test_the_checker_catches_broken_sequences(self):
        main = [list(t) for t in SEQUENCE["main"]]
        same = [list(t) for t in main]
        same[1][1] = same[0][1]  # the ink twice in a row
        self.assertTrue(self.tool.problems_in_main(same))
        self.assertTrue(self.tool.problems_in_main(main[:-1]))
        swapped = [list(t) for t in main]
        swapped[0], swapped[30] = swapped[30], swapped[0]  # the counts hold, the blocks do not
        self.assertTrue(self.tool.problems_in_main(swapped))
        changed = [list(t) for t in main]
        index = next(i for i, t in enumerate(changed) if t == ["red", "red"])
        changed[index] = ["red", "green"]  # a congruent trial became incongruent
        self.assertTrue(self.tool.problems_in_main(changed))
        practice = [list(t) for t in SEQUENCE["practice"][0]]
        self.assertEqual(self.tool.problems_in_practice(practice), [])
        practice[3][1] = practice[2][1]
        self.assertTrue(self.tool.problems_in_practice(practice))
        self.assertTrue(self.tool.problems_in_practice(practice[:-1]))


class ScoreTest(AppTestCase):
    SUMMARIZE = "trials => import('./src/stroop/score.js').then(m => m.summarize(trials))"

    def trial(self, condition, type_, rt):
        return {"condition": condition, "type": type_, "rt_ms": rt}

    def test_the_effect_is_incongruent_minus_congruent_over_correct_trials(self):
        trials = [
            self.trial("congruent", "correct", 400), self.trial("congruent", "correct", 500), self.trial("congruent", "correct", 600),
            self.trial("congruent", "error", 150),  # an error does not count in the mean
            self.trial("incongruent", "correct", 700), self.trial("incongruent", "correct", 800),
            self.trial("incongruent", "error", 900), self.trial("incongruent", "timeout", None),
            self.trial("incongruent", "timeout", None),
        ]
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                result = page.evaluate(self.SUMMARIZE, trials)
                self.assertEqual(result["effect_ms"], 250)
                self.assertEqual(result["congruent"], {"n": 4, "correct_n": 3, "errors_n": 1, "timeouts_n": 0, "rt_ms": 500})
                self.assertEqual(result["incongruent"], {"n": 5, "correct_n": 2, "errors_n": 1, "timeouts_n": 2, "rt_ms": 750})
                self.assertEqual((result["correct_n"], result["errors_n"], result["timeouts_n"]), (5, 2, 2))

    def test_the_mean_is_rounded_to_a_tenth_and_the_effect_is_empty_without_correct_trials(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                result = page.evaluate(self.SUMMARIZE, [
                    self.trial("congruent", "correct", 400.1), self.trial("congruent", "correct", 400.2),
                    self.trial("congruent", "correct", 400.4), self.trial("incongruent", "correct", 500)])
                self.assertEqual(result["congruent"]["rt_ms"], 400.2)
                self.assertEqual(result["effect_ms"], 99.8)
                empty = page.evaluate(self.SUMMARIZE, [
                    self.trial("congruent", "correct", 400), self.trial("incongruent", "error", 600),
                    self.trial("incongruent", "timeout", None)])
                self.assertIsNone(empty["incongruent"]["rt_ms"])
                self.assertIsNone(empty["effect_ms"])
                self.assertEqual(empty["incongruent"]["n"], 2)
                self.assertEqual(page.evaluate(self.SUMMARIZE, [])["effect_ms"], None)


class StroopTestCase(AppTestCase):
    def open_stroop(self, browser, extra="", retest=False, tracked=False, **options):
        context, receiver = self.new_context(browser, **options)
        link = f"?mode=dev&only=stroop{'&r=' + CODE if retest else ''}{extra}"
        page, errors = self.open(browser, link, context=context)
        page.get_by_role("button", name="Почати тренування").wait_for()
        if tracked:
            page.evaluate(PHASES)
        return page, errors, context, receiver

    def result(self, page, receiver):
        """Waits for the end of the block; returns (summary, log) of its message."""
        page.locator(".dev-end").wait_for()
        self.wait_delivered(page)
        [message] = [m for m in receiver.accepted if m["block"] == "stroop"]
        return message["summary"], message["log"]

    def phase(self, page, name, trial=None):
        selector = f".stroop-run[data-phase='{name}']" + (f"[data-trial='{trial}']" if trial is not None else "")
        page.locator(selector).wait_for()

    def drawn(self, page):
        page.locator(".stroop-word[data-shown='1']").wait_for()


class TrialTest(StroopTestCase):
    def test_the_screen_is_dark_with_a_dot_and_four_plates_and_no_hint(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_stroop(browser, "&set.stroop.itiMs=3000")
                self.start_stroop_training(page)
                self.assertEqual(page.evaluate("() => getComputedStyle(document.querySelector('.stroop-run')).backgroundColor"),
                                 "rgb(43, 43, 43)")  # #2B2B2B
                plates = page.locator(".stroop-plate")
                self.assertEqual(plates.evaluate_all("els => els.map(e => e.dataset.color)"), ORDER)
                self.assertEqual(plates.evaluate_all("els => els.map(e => e.getAttribute('fill'))"),
                                 [LOOK["colors"][c] for c in ORDER])
                self.assertEqual(page.locator(".stroop-word").count(), 0)  # the word comes after the pause
                self.assertEqual(page.locator(".stroop-dot-visible").count(), 1)  # the dot is there from the start
                self.assertEqual(page.locator(".stroop-hint").count(), 0)  # no "press the dot" hint (decision 170)
                self.assertEqual(page.locator(".stroop-dot-hit").count(), 0)  # the dot takes no clicks
                self.assertEqual(errors, [])

    def test_sizes_are_in_mm(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_stroop(browser)
                px = page.evaluate("() => window.tmtua.ctx.scale().pxPerMm")
                self.start_stroop_training(page)
                area = page.locator(".stroop-area").bounding_box()
                self.assertAlmostEqual(area["width"], 240 * px, delta=1)
                self.assertAlmostEqual(area["height"], 150 * px, delta=1)
                plate = page.locator(".stroop-plate").first.bounding_box()
                self.assertAlmostEqual(plate["width"], 36 * px, delta=1)
                self.assertAlmostEqual(plate["height"], 22 * px, delta=1)
                self.assertAlmostEqual(page.locator(".stroop-dot-visible").bounding_box()["width"], 6 * px, delta=1)
                word, ink = self.stroop_word(page)
                width = page.locator(".stroop-word").evaluate("e => e.getBBox().width")  # user units are mm
                self.assertAlmostEqual(width, WORD_EM[word] * 12 / 0.7, delta=3)
                # The word is above the dot, centred on it (in mm of the area).
                box = page.locator(".stroop-word").evaluate("e => { const b = e.getBBox(); return { x: b.x, y: b.y, w: b.width, h: b.height }; }")
                self.assertAlmostEqual(box["x"] + box["w"] / 2, 120, delta=1.5)
                self.assertLess(box["y"] + box["h"], 75 - 3 - 10)  # the dot's centre is at 75 mm, its radius 3 mm
                dot = page.locator(".stroop-dot-visible").bounding_box()
                # Every plate is below the dot.
                for p in page.locator(".stroop-plate").all():
                    self.assertGreater(p.bounding_box()["y"], dot["y"] + dot["height"])
                ink_fill = page.locator(".stroop-word").get_attribute("fill")
                self.assertEqual(ink_fill, LOOK["colors"][ink])
                self.assertEqual(errors, [])

    def test_the_word_comes_by_itself_after_the_pause_and_the_dot_takes_no_click(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_stroop(browser, "&set.stroop.itiMs=700", tracked=True)
                self.start_stroop_training(page)
                self.assertEqual(page.locator(".stroop-run").get_attribute("data-phase"), "pause")
                self.stroop_click(page, ".stroop-dot-visible")  # the dot is no button
                self.assertEqual(page.locator(".stroop-run").get_attribute("data-phase"), "pause")
                self.stroop_word(page)
                self.assertEqual(page.locator(".stroop-run").get_attribute("data-phase"), "word")
                when = {(p[0], p[2]): p[1] for p in page.evaluate("window.__phases")}
                self.assertAlmostEqual(when[("word", "0")] - when[("pause", "0")], 700, delta=150)
                self.assertEqual(errors, [])

    def test_a_correct_press_a_wrong_press_and_the_feedback_in_training(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_stroop(browser, "&set.stroop.itiMs=250&set.stroop.feedbackMs=400", tracked=True)
                self.start_stroop_training(page)
                _, ink = self.stroop_word(page)
                self.stroop_plate(page, ink)
                self.phase(page, "feedback")
                self.assertEqual(page.locator(".stroop-feedback").get_attribute("data-kind"), "correct")
                self.assertEqual(page.locator(".stroop-feedback").text_content(), "Правильно")
                self.assertEqual(page.locator(".stroop-word").count(), 0)  # the word goes at the answer
                word, ink = self.stroop_word(page)
                wrong = ORDER[(ORDER.index(ink) + 1) % 4]
                self.stroop_plate(page, wrong)
                self.phase(page, "feedback")
                self.assertEqual(page.locator(".stroop-feedback").get_attribute("data-kind"), "error")
                lines = page.locator(".stroop-feedback text").all_text_contents()
                self.assertEqual(len(lines), 1)  # one line: it fits the area
                self.assertEqual(lines[0], f"Неправильно: слово надруковане {INSTRUMENTAL[ink]} кольором.")
                # The feedback is in the neutral colour, not in one of the four.
                self.assertNotIn(page.locator(".stroop-feedback text").first.get_attribute("fill"), LOOK["colors"].values())
                self.phase(page, "word", 2)
                phases = page.evaluate("window.__phases")
                names = [(p[0], p[2]) for p in phases]
                self.assertEqual(names[:6], [("pause", "0"), ("word", "0"), ("feedback", "0"),
                                             ("pause", "1"), ("word", "1"), ("feedback", "1")])
                when = {(p[0], p[2]): p[1] for p in phases}
                self.assertAlmostEqual(when[("pause", "1")] - when[("feedback", "0")], 400, delta=120)  # the feedback, 0.9 s in the sessions
                self.assertAlmostEqual(when[("word", "1")] - when[("pause", "1")], 250, delta=120)  # the pause before the next word, 1.2 s in the sessions
                self.assertEqual(errors, [])

    def test_the_word_waits_five_seconds_and_a_late_trial_is_a_miss_with_its_own_feedback(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_stroop(browser, "&set.stroop.responseLimitMs=350&set.stroop.feedbackMs=600&set.stroop.itiMs=100")
                self.start_stroop_training(page)
                self.stroop_word(page)
                self.phase(page, "feedback")
                self.assertEqual(page.locator(".stroop-feedback").get_attribute("data-kind"), "timeout")
                self.assertEqual(page.locator(".stroop-feedback").text_content(), "Час вийшов. Відповідайте трохи швидше.")
                self.assertEqual(page.locator(".stroop-word").count(), 0)
                self.assertEqual(errors, [])

    def test_the_limit_in_the_sessions_is_five_seconds_the_pause_1200_ms_the_feedback_900_ms(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _, _, _ = self.open_stroop(browser)
                params = page.evaluate("() => window.tmtuaParams.stroop")
                self.assertEqual((params["responseLimitMs"], params["itiMs"], params["feedbackMs"]), (5000, 1200, 900))
                self.assertEqual((params["practiceTrials"], params["practiceMinCorrect"], params["mainTrials"]), (12, 9, 96))

    def test_presses_that_are_no_answer_are_ignored_and_counted_apart(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_stroop(browser, FAST)
                self.start_stroop(page)
                _, ink = self.stroop_word(page)
                page.mouse.click(40, 40)  # beside the plates
                page.mouse.click(40, 600)
                self.stroop_click(page, ".stroop-dot-visible")  # the dot is no plate either
                page.mouse.click(*[v + 1 for v in (0, 0)])
                page.wait_for_timeout(100)
                self.assertEqual(page.locator(".stroop-run").get_attribute("data-phase"), "word")  # still waiting
                page.mouse.click(*self.plate_centre(page, ORDER[(ORDER.index(ink) + 1) % 4]), button="right")  # not the main button
                page.wait_for_timeout(100)
                self.assertEqual(page.locator(".stroop-run").get_attribute("data-phase"), "word")
                self.stroop_plate(page, ink)  # now the answer
                self.bot_stroop(page)
                summary, log = self.result(page, receiver)
                first = log["main"]["trials"][0]
                self.assertEqual((first["type"], first["resp"], first["ok"]), ("correct", ink, True))
                self.assertEqual(first["miss_n"], 4)  # (40, 40), (40, 600), the dot, (1, 1)
                self.assertEqual([s["where"] for s in first["stray"] if s["where"] != "pause"], ["outside"] * 4)
                self.assertEqual(summary["stroop_miss_n"], 4)
                self.assertNotIn("stroop_dot_repeat_n", summary)
                self.assertEqual(summary["stroop_errors_n"], 0)
                self.assertEqual(errors, [])

    def plate_centre(self, page, color):
        box = page.locator(f".stroop-plate[data-color='{color}']").bounding_box()
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def test_a_press_in_the_pause_is_no_answer(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_stroop(browser, "&set.stroop.itiMs=400&set.stroop.feedbackMs=40")
                self.start_stroop_training(page)
                _, ink = self.stroop_word(page)
                self.stroop_plate(page, ink)
                self.phase(page, "pause")
                self.stroop_plate(page, "green")  # a plate in the pause
                self.stroop_click(page, ".stroop-plate[data-color='red']")
                self.drawn(page)
                self.assertEqual(page.locator(".stroop-run").get_attribute("data-trial"), "1")
                self.assertEqual(page.locator(".stroop-run").get_attribute("data-phase"), "word")  # the presses in the pause answered nothing
                self.assertEqual(errors, [])


class MainPartTest(StroopTestCase):
    def test_correct_errors_and_timeouts_are_counted_per_condition(self):
        wrong, timeout = [3, 10, 11, 40], [7, 60]
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_stroop(browser, FAST + "&set.stroop.responseLimitMs=250")
                self.start_stroop(page)
                self.bot_stroop(page, wrong=wrong, timeout=timeout, delay={"congruent": 10, "incongruent": 60})
                summary, log = self.result(page, receiver)
                main = SEQUENCE["main"]
                cond = [condition(t) for t in main]
                for c in ("congruent", "incongruent"):
                    own = [i for i in range(96) if cond[i] == c]
                    self.assertEqual(summary[f"stroop_{c}_errors_n"], len([i for i in own if i in wrong]), c)
                    self.assertEqual(summary[f"stroop_{c}_timeouts_n"], len([i for i in own if i in timeout]), c)
                    self.assertEqual(summary[f"stroop_{c}_correct_n"], 48 - len([i for i in own if i in wrong + timeout]), c)
                self.assertEqual(summary["stroop_errors_n"], 4)
                self.assertEqual(summary["stroop_timeouts_n"], 2)
                self.assertEqual(summary["stroop_correct_n"], 90)
                trials = log["main"]["trials"]
                self.assertEqual(len(trials), 96)
                self.assertEqual([[t["word"], t["ink"]] for t in trials], main)
                self.assertEqual([t["type"] for t in trials].count("timeout"), 2)
                for i in wrong:
                    self.assertEqual(trials[i]["type"], "error")
                    self.assertNotEqual(trials[i]["resp"], trials[i]["ink"])
                for i in timeout:
                    self.assertIsNone(trials[i]["rt_ms"])
                    self.assertIsNone(trials[i]["resp"])
                # The effect is recomputed here from the trials in the log, correct ones only.
                rts = {c: [t["rt_ms"] for t in trials if t["condition"] == c and t["type"] == "correct"]
                       for c in ("congruent", "incongruent")}
                self.assertAlmostEqual(summary["stroop_congruent_rt_ms"], mean(rts["congruent"]), delta=0.06)
                self.assertAlmostEqual(summary["stroop_incongruent_rt_ms"], mean(rts["incongruent"]), delta=0.06)
                self.assertAlmostEqual(summary["stroop_effect_ms"], mean(rts["incongruent"]) - mean(rts["congruent"]), delta=0.16)
                self.assertGreater(summary["stroop_effect_ms"], 30)  # the bot answers 50 ms slower on incongruent trials
                self.assertLess(summary["stroop_effect_ms"], 120)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_the_reaction_time_runs_from_the_drawn_word_to_the_press(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_stroop(browser, FAST)
                self.start_stroop(page)
                self.bot_stroop(page, delay={"congruent": 120, "incongruent": 120}, limit=3)
                self.bot_stroop(page)
                _, log = self.result(page, receiver)
                for trial in log["main"]["trials"][:3]:
                    self.assertGreaterEqual(trial["rt_ms"], 115)
                    self.assertLess(trial["rt_ms"], 200)
                self.assertEqual(errors, [])

    def test_no_feedback_and_no_hint_in_the_main_part(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_stroop(browser, "&set.stroop.itiMs=300&set.stroop.feedbackMs=40")
                self.start_stroop(page)
                page.evaluate(PHASES)  # from the main part on
                self.assertEqual(page.locator(".stroop-hint").count(), 0)
                _, ink = self.stroop_word(page)
                self.stroop_plate(page, ORDER[(ORDER.index(ink) + 1) % 4])  # a wrong answer
                self.phase(page, "pause")
                self.assertEqual(page.locator(".stroop-feedback").count(), 0)
                self.assertEqual(page.locator(".stroop-word").count(), 0)
                self.assertNotEqual(page.locator(".stroop-dot").evaluate("e => getComputedStyle(e).display"), "none")  # the dot stays
                self.phase(page, "word", 1)
                phases = page.evaluate("window.__phases")
                main = [p for p in phases if p[0] == "feedback"]
                self.assertEqual(main, [])
                when = {(p[0], p[2]): p[1] for p in phases}
                self.assertAlmostEqual(when[("word", "1")] - when[("pause", "1")], 300, delta=120)
                self.assertEqual(errors, [])

    def test_the_sequence_is_the_fixed_one_and_every_trial_is_logged(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_stroop(browser, FAST)
                self.start_stroop(page)
                self.bot_stroop(page)
                summary, log = self.result(page, receiver)
                trials = log["main"]["trials"]
                self.assertEqual([[t["word"], t["ink"]] for t in trials], SEQUENCE["main"])
                self.assertEqual([t["i"] for t in trials], list(range(96)))
                self.assertEqual({t["type"] for t in trials}, {"correct"})
                times = [t["t_ms"] for t in trials]
                self.assertEqual(times, sorted(times))
                for t in trials:
                    self.assertEqual(set(t), {"i", "word", "ink", "condition", "type", "resp", "ok", "rt_ms",
                                              "t_ms", "miss_n", "stray"})
                    self.assertEqual(t["condition"], condition([t["word"], t["ink"]]))
                    self.assertEqual(t["resp"], t["ink"])
                    self.assertGreater(t["rt_ms"], 0)
                self.assertEqual(log["main"]["status"], "complete")
                self.assertEqual(log["main"]["trials_n"], 96)
                self.assertEqual(summary["stroop_time_ms"], log["main"]["time_ms"])
                self.assertGreaterEqual(summary["stroop_time_ms"], times[-1])
                self.assertEqual(errors, [])

    def test_the_run_is_in_the_during_test_span_of_the_log(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_stroop(browser, FAST + "&set.stroop.responseLimitMs=400")
                self.start_stroop(page)
                page.evaluate("() => window.dispatchEvent(new Event('blur'))")
                page.wait_for_timeout(200)
                page.evaluate("() => window.dispatchEvent(new Event('focus'))")
                self.bot_stroop(page, limit=2)
                self.bot_stroop(page)
                summary, log = self.result(page, receiver)
                during = log["main"]["during_test"]
                self.assertEqual(during["blur_n"], 1)
                self.assertGreaterEqual(during["blur_ms"], 150)
                self.assertEqual(summary["stroop_blur_n"], 1)  # the whole block
                self.assertEqual(summary["stroop_test_blur_n"], 1)  # decision 168: the main part only
                self.assertEqual(summary["stroop_test_blur_ms"], during["blur_ms"])
                for key in ("hidden_n", "hidden_ms", "fs_exit_n", "fs_exit_ms"):
                    self.assertEqual(summary[f"stroop_test_{key}"], 0, key)
                self.assertEqual(errors, [])


class TrainingTest(StroopTestCase):
    def start(self, page, wrong=(), timeout=()):
        """The first training attempt with the given trials answered wrongly or not at all."""
        page.get_by_role("button", name="Почати тренування").click()
        page.locator(".stroop-run[data-started='1']").wait_for()
        self.bot_stroop(page, wrong=list(wrong), timeout=list(timeout))

    def test_nine_correct_of_twelve_means_no_repeat(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_stroop(browser, FAST + "&set.stroop.responseLimitMs=250")
                self.start(page, wrong=[1, 2], timeout=[5])  # nine correct
                page.get_by_text("Тренування завершено.").wait_for()
                page.get_by_role("button", name="Почати", exact=True).click()
                self.drawn(page)
                self.bot_stroop(page)
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["stroop_practice_attempts_n"], 1)
                self.assertEqual(summary["stroop_practice_correct_1"], 9)
                self.assertIsNone(summary["stroop_practice_correct_2"])
                attempts = log["practice"]["attempts"]
                self.assertEqual(len(attempts), 1)
                self.assertEqual([[t["word"], t["ink"]] for t in attempts[0]["trials"]], SEQUENCE["practice"][0])
                self.assertEqual((attempts[0]["errors_n"], attempts[0]["timeouts_n"]), (2, 1))
                self.assertEqual(errors, [])

    def test_eight_correct_means_one_repeat_with_the_other_list_then_the_main_part_in_any_case(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_stroop(browser, FAST + "&set.stroop.responseLimitMs=250")
                self.start(page, wrong=[1, 2], timeout=[5, 6])  # eight correct
                page.get_by_text("Потренуймося ще раз. Натискайте плашку того кольору, яким надруковано слово, а не того, що слово означає.").wait_for()
                page.get_by_role("button", name="Почати тренування").click()
                self.drawn(page)
                self.bot_stroop(page, wrong=[0, 1, 2, 3, 4, 5, 6, 7])  # the repeat is poor too
                page.get_by_text("Тренування завершено.").wait_for()  # the main part follows in any case, no second repeat
                self.assertEqual(page.get_by_role("button", name="Почати тренування").count(), 0)
                page.get_by_role("button", name="Почати", exact=True).click()
                self.drawn(page)
                self.bot_stroop(page)
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["stroop_practice_attempts_n"], 2)
                self.assertEqual(summary["stroop_practice_correct_1"], 8)
                self.assertEqual(summary["stroop_practice_correct_2"], 4)
                attempts = log["practice"]["attempts"]
                self.assertEqual([[t["word"], t["ink"]] for t in attempts[0]["trials"]], SEQUENCE["practice"][0])
                self.assertEqual([[t["word"], t["ink"]] for t in attempts[1]["trials"]], SEQUENCE["practice"][1])
                self.assertEqual([a["attempt"] for a in attempts], [1, 2])
                self.assertEqual(log["main"]["trials_n"], 96)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])


class InstructionTest(StroopTestCase):
    def test_the_instruction_starts_with_the_end_of_the_coding_and_shows_the_example_in_red(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_stroop(browser)
                paragraphs = page.locator(".screen p").all_text_contents()
                self.assertEqual(paragraphs[0], "Завдання із символами завершено.")
                self.assertEqual(paragraphs[1], "Тест Струпа")
                example = page.locator(".stroop-example")
                self.assertEqual(example.text_content(), "СИНІЙ")
                self.assertEqual(example.evaluate("e => getComputedStyle(e).color"), "rgb(255, 65, 54)")  # #FF4136
                self.assertEqual(errors, [])


class SessionTest(StroopTestCase):
    def test_the_block_is_a_task_with_a_fullscreen_gate_and_the_same_in_the_retest(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                first = {b[0]: b for b in self.session_blocks(page)}
                retest = {b[0]: b for b in self.session_blocks(page, retest=True)}
                self.assertFalse(first["stroop"][2])  # no longer a placeholder
                self.assertFalse(retest["stroop"][2])
                self.assertEqual(page.evaluate(
                    "import('./src/blocks.js').then(m => [m.BLOCKS, m.RETEST_BLOCKS].map(l => l.find(b => b.id === 'stroop').isTask))"),
                    [True, True])
                self.assertEqual([b[0] for b in self.session_blocks(page)].index("stroop"),
                                 [b[0] for b in self.session_blocks(page)].index("coding") + 1)

    def test_the_retest_has_the_same_colours_and_the_same_sequence(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                first = {}
                for retest in (False, True):
                    page, errors, context, receiver = self.open_stroop(browser, FAST, retest=retest)
                    self.start_stroop(page, wrong_trials=[0, 1, 2, 3], repeat=True)  # eight correct: the repeat
                    self.bot_stroop(page)
                    summary, log = self.result(page, receiver)
                    first[retest] = (log["colors"], log["sequence"], [[t["word"], t["ink"]] for t in log["main"]["trials"]],
                                     [[t["word"], t["ink"]] for a in log["practice"]["attempts"] for t in a["trials"]],
                                     summary["stroop_colors_version"], summary["stroop_sequence_version"])
                    context.close()  # a page in the background gets no animation frames in WebKit
                self.assertEqual(first[False], first[True])
                self.assertEqual(first[True][4:], ("1", "1"))
                self.assertEqual(first[True][2], SEQUENCE["main"])

    def test_the_summary_has_exactly_the_documented_columns(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, receiver = self.open_stroop(browser, FAST)
                self.start_stroop(page)
                self.bot_stroop(page)
                summary, log = self.result(page, receiver)
                own = {k for k in summary if k.startswith("stroop_") and not k.startswith(
                    ("stroop_hidden", "stroop_blur", "stroop_fs_exit", "stroop_resize", "stroop_zoom", "stroop_touch", "stroop_idle"))}
                self.assertEqual(own, COLUMNS)
                self.assertEqual(summary["stroop_colors_version"], "1")
                self.assertEqual(summary["stroop_sequence_version"], "1")
                self.assertEqual(summary["stroop_practice_attempts_n"], 1)
                env = {k for k in summary if k.startswith("stroop_") and k not in COLUMNS}
                self.assertEqual(len(env), 11)  # the monitor's columns
                self.assertEqual(log["colors"]["hex"], LOOK["colors"])
                self.assertEqual(log["colors"]["bg"], "#2B2B2B")
                self.assertEqual(log["sequence"]["version"], 1)
                self.assertEqual(log["limits"], {"response_limit_ms": 5000, "iti_ms": 20, "feedback_ms": 40})
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

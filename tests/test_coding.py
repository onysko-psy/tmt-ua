"""Checks of the symbol coding task (task T3.1): the fixed sequence, the
scoring of the main part, which keys count as answers, the 90 s limit, the
training with its repeat, the same stimuli at the retest, the data sent,
and the monitor around the task. In Chromium and WebKit; the sequence checks
need no browser.

Run from the app/ folder: ../.venv/bin/python -m unittest discover -s tests -p "test_coding.py" -v
"""

import importlib.util
import json
import unittest
from pathlib import Path

from harness import AppTestCase

APP = Path(__file__).resolve().parent.parent
SEQUENCE = json.loads((APP / "stimuli" / "coding-sequence.json").read_text())
SYMBOLS = json.loads((APP / "stimuli" / "coding-symbols.json").read_text())
CODE = "k3m8q7w2xz"  # a participant code of the first session, for the retest link

# Columns of the table the block adds besides the 10 of the monitor.
COLUMNS = {
    "coding_practice_attempts_n", "coding_practice_errors_1", "coding_practice_errors_2",
    "coding_symbols_version", "coding_sequence_version",
    "coding_correct_n", "coding_errors_n", "coding_answers_n", "coding_extra_keys_n",
    "coding_time_ms", "coding_sequence_exhausted",
    # the exits during the 90 s themselves (decision 165)
    "coding_test_hidden_n", "coding_test_hidden_ms", "coding_test_blur_n", "coding_test_blur_ms",
    "coding_test_fs_exit_n", "coding_test_fs_exit_ms",
}


def load_tool():
    spec = importlib.util.spec_from_file_location("coding_sequence", APP / "tools" / "coding_sequence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SequenceTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_180_items_each_symbol_20_times_never_twice_in_a_row(self):
        items = SEQUENCE["items"]
        self.assertEqual(len(items), 180)
        for symbol in range(1, 10):
            self.assertEqual(items.count(symbol), 20, symbol)
        self.assertFalse(any(a == b for a, b in zip(items, items[1:])))

    def test_the_symbols_are_equally_frequent_wherever_one_stops(self):
        items = SEQUENCE["items"]
        for stop in (45, 63, 90, 117):  # a typical range of results is 50-90
            counts = [items[:stop].count(s) for s in range(1, 10)]
            self.assertLessEqual(max(counts) - min(counts), 1, (stop, counts))

    def test_the_practice_lists(self):
        self.assertEqual(len(SEQUENCE["practice"]), 2)  # the second is for the repeat
        for items in SEQUENCE["practice"]:
            self.assertEqual(len(items), 10)
            self.assertEqual(set(items), set(range(1, 10)))
            self.assertFalse(any(a == b for a, b in zip(items, items[1:])))
        self.assertNotEqual(SEQUENCE["practice"][0], SEQUENCE["practice"][1])

    def test_the_file_is_what_the_generator_writes_and_fits_the_figures(self):
        self.assertEqual(self.tool.generate(), SEQUENCE)
        self.assertEqual(self.tool.check(SEQUENCE), [])
        self.assertEqual(SEQUENCE["symbols_version"], SYMBOLS["symbols_version"])
        self.assertEqual(SEQUENCE["sequence_version"], 1)

    def test_the_checker_catches_broken_sequences(self):
        items = list(SEQUENCE["items"])
        twice = items[:]
        twice[1] = twice[0]
        self.assertTrue(self.tool.problems_in_main(twice))
        short = items[:-1]
        self.assertTrue(self.tool.problems_in_main(short))
        skewed = items[:]
        i = skewed.index(1, 40)
        skewed[i] = 2  # a 1 became a 2: the counts are 19 and 21
        self.assertTrue(self.tool.problems_in_main(skewed))
        self.assertTrue(self.tool.problems_in_practice([1, 2, 3, 4, 5, 6, 7, 8, 9, 9]))
        self.assertTrue(self.tool.problems_in_practice([1, 2, 3, 4, 5, 6, 7, 8, 1, 2]))


class CodingTestCase(AppTestCase):
    def open_coding(self, browser, extra="", retest=False, **options):
        context, receiver = self.new_context(browser, **options)
        link = f"?mode=dev&only=coding{'&r=' + CODE if retest else ''}{extra}"
        page, errors = self.open(browser, link, context=context)
        page.get_by_role("button", name="Почати тренування").wait_for()
        return page, errors, context, receiver

    def result(self, page, receiver):
        """Waits for the end of the block; returns (summary, log) of its message."""
        page.locator(".dev-end").wait_for()
        self.wait_delivered(page)
        [message] = [m for m in receiver.accepted if m["block"] == "coding"]
        return message["summary"], message["log"]

    def main_part(self, page, wrong=0):
        self.start_coding(page, wrong)

    def key(self, page, code, **event):
        """One synthetic key press on the page, as the participant's key."""
        page.evaluate("([code, event]) => window.dispatchEvent(new KeyboardEvent('keydown', "
                      "{ code, bubbles: true, ...event }))", [code, event])

    def drawn(self, page):
        """Waits until the figure in the frame is on the screen."""
        page.locator(".coding-frame[data-shown='1']").wait_for()


class MainPartTest(CodingTestCase):
    def test_correct_errors_and_answers_are_counted(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=1500")
                self.main_part(page)
                self.bot_coding(page, 12, wrong=[2, 5])  # then the time runs out
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_correct_n"], 10)
                self.assertEqual(summary["coding_errors_n"], 2)
                self.assertEqual(summary["coding_answers_n"], 12)
                self.assertEqual(summary["coding_extra_keys_n"], 0)
                self.assertEqual(summary["coding_sequence_exhausted"], 0)
                self.assertEqual(summary["coding_time_ms"], 1500)
                main = log["main"]
                self.assertEqual(main["status"], "complete")
                self.assertEqual([a["ok"] for a in main["answers"]].count(False), 2)
                self.assertEqual([a["i"] for a in main["answers"] if not a["ok"]], [2, 5])
                # a wrong digit moves on to the next figure at once (decision 81)
                self.assertEqual([a["symbol"] for a in main["answers"]], SEQUENCE["items"][:12])
                for answer in main["answers"]:
                    self.assertGreaterEqual(answer["rt_ms"], 0)
                times = [a["t_ms"] for a in main["answers"]]
                self.assertEqual(times, sorted(times))
                self.assertEqual(set(summary) & {"coding_correct_n"}, {"coding_correct_n"})
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_the_whole_sequence_ends_the_main_part_at_once(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser)
                self.main_part(page)
                self.bot_coding(page, 1000, wrong=[0, 100, 179])
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_answers_n"], 180)
                self.assertEqual(summary["coding_correct_n"], 177)
                self.assertEqual(summary["coding_errors_n"], 3)
                self.assertEqual(summary["coding_sequence_exhausted"], 1)
                self.assertLess(summary["coding_time_ms"], 90000)
                self.assertEqual(log["main"]["status"], "exhausted")
                self.assertEqual(errors, [])

    def test_the_limit_is_90_s_by_default_and_changes_only_in_dev(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, _, _ = self.open_coding(browser)
                self.assertEqual(page.evaluate("window.tmtua.params.coding.durationMs"), 90000)
                page2, _ = self.open(browser, "?mode=pilot&set.coding.durationMs=1000")
                self.assertEqual(page2.evaluate("window.tmtua?.params?.coding.durationMs ?? 90000"), 90000)

    def test_clock_starts_when_the_first_figure_is_drawn(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=1200")
                page.evaluate("window.__t = performance.now()")
                self.start_coding_training(page)
                self.pass_coding_training(page)
                page.get_by_role("button", name="Почати", exact=True).click()
                page.locator(".coding-frame").wait_for()
                started = page.evaluate("performance.now()")
                # the main part ends 1.2 s after its first figure, not later
                page.locator(".coding-run").wait_for(state="detached", timeout=3000)
                ended = page.evaluate("performance.now()")
                self.assertLess(ended - started, 1200 + 400)
                self.assertGreater(ended - started, 1000)
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_answers_n"], 0)
                self.assertEqual(summary["coding_correct_n"], 0)
                self.assertEqual(log["main"]["answers"], [])
                self.assertEqual(errors, [])


class KeysTest(CodingTestCase):
    def test_top_row_and_numeric_pad_both_answer_by_the_place_of_the_key(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=6000")
                self.main_part(page)
                for number in range(6):  # real key presses, a trusted event
                    digit = self.coding_symbol(page)
                    self.drawn(page)
                    self.coding_press(page, digit, numpad=bool(number % 2))
                    page.wait_for_function(
                        "d => document.querySelector('.coding-frame').dataset.symbol !== String(d)", arg=digit)
                # another layout: the digit key gives another character, the place is the same
                digit = self.coding_symbol(page)
                self.drawn(page)
                self.key(page, f"Digit{digit}", key="&")
                page.wait_for_timeout(60)
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_correct_n"], 7)
                self.assertEqual(summary["coding_errors_n"], 0)
                self.assertEqual(summary["coding_extra_keys_n"], 0)
                self.assertEqual(errors, [])

    def test_other_keys_are_no_answers_and_no_errors_but_are_kept(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=4000")
                self.main_part(page)
                self.drawn(page)
                shown = self.coding_symbol(page)
                for key in ["KeyA", "Space", "Enter", "Digit0", "Numpad0", "ArrowUp", "Escape"]:
                    self.key(page, key)
                self.key(page, f"Digit{shown}", ctrlKey=True)  # Ctrl+digit: a browser shortcut
                self.key(page, f"Digit{shown}", metaKey=True)
                self.key(page, f"Digit{shown}", altKey=True)
                self.key(page, f"Digit{shown}", repeat=True)  # a held key
                self.assertEqual(self.coding_symbol(page), shown)  # still the same figure
                self.coding_press(page, shown)  # the real answer still works
                page.wait_for_function(
                    "d => document.querySelector('.coding-frame').dataset.symbol !== String(d)", arg=shown)
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_correct_n"], 1)
                self.assertEqual(summary["coding_errors_n"], 0)
                self.assertEqual(summary["coding_answers_n"], 1)
                self.assertEqual(summary["coding_extra_keys_n"], 11)
                reasons = [k["reason"] for k in log["main"]["extra_keys"]]
                self.assertEqual(reasons, ["not_digit"] * 7 + ["modifier"] * 3 + ["repeat"])
                self.assertEqual([k["code"] for k in log["main"]["extra_keys"]][:3], ["KeyA", "Space", "Enter"])
                self.assertEqual(errors, [])

    def test_a_key_before_the_next_figure_is_drawn_is_not_an_answer(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=2000")
                self.main_part(page)
                self.drawn(page)
                # Two presses in one task: the figure after the first is not drawn yet.
                page.evaluate("""() => {
                    const d = document.querySelector('.coding-frame').dataset.symbol;
                    for (let i = 0; i < 2; i++)
                        window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Digit' + d, bubbles: true }));
                }""")
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_answers_n"], 1)
                self.assertEqual(summary["coding_errors_n"], 0)
                self.assertEqual([k["reason"] for k in log["main"]["extra_keys"]], ["before_shown"])
                self.assertEqual(errors, [])

    def test_a_key_after_the_time_is_up_is_not_an_answer(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=1000")
                self.main_part(page)
                self.drawn(page)
                # The page is busy past the limit, so its timer cannot fire: the
                # key is judged by the time it was pressed.
                page.evaluate("""() => {
                    const end = performance.now() + 1300;
                    while (performance.now() < end) {}
                    const d = document.querySelector('.coding-frame').dataset.symbol;
                    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Digit' + d, bubbles: true }));
                }""")
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_answers_n"], 0)
                self.assertEqual(summary["coding_correct_n"], 0)
                self.assertEqual(summary["coding_extra_keys_n"], 1)
                self.assertEqual(log["main"]["extra_keys"][0]["reason"], "late")
                self.assertEqual(summary["coding_time_ms"], 1000)
                self.assertEqual(errors, [])


class TrainingTest(CodingTestCase):
    def test_a_wrong_digit_gives_the_hint_and_the_right_one_has_to_be_pressed(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser)
                texts = self.module(page, "texts.uk.js")["texts"]["coding"]
                self.start_coding_training(page)
                self.drawn(page)
                first = self.coding_symbol(page)
                self.assertEqual(page.locator(".coding-wrong").evaluate("e => getComputedStyle(e).visibility"), "hidden")
                self.coding_press(page, first % 9 + 1)
                page.wait_for_timeout(60)
                self.assertEqual(page.locator(".coding-wrong").evaluate("e => getComputedStyle(e).visibility"), "visible")
                self.assertEqual(page.locator(".coding-wrong").inner_text(), texts["trainingWrong"])
                self.assertEqual(self.coding_symbol(page), first)  # the figure stays
                self.coding_press(page, first)
                page.wait_for_function("d => document.querySelector('.coding-frame').dataset.symbol !== String(d)", arg=first)
                self.assertEqual(page.locator(".coding-wrong").evaluate("e => getComputedStyle(e).visibility"), "hidden")
                self.assertEqual(page.locator(".coding-hint").inner_text(), texts["keyHint"])
                self.assertEqual(errors, [])

    def test_two_errors_do_not_repeat_the_training(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=600")
                self.main_part(page, wrong=2)
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_practice_attempts_n"], 1)
                self.assertEqual(summary["coding_practice_errors_1"], 2)
                self.assertIsNone(summary["coding_practice_errors_2"])
                self.assertEqual(len(log["practice"]["attempts"]), 1)
                self.assertEqual(errors, [])

    def test_three_errors_repeat_the_training_once_with_another_list(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=600")
                texts = self.module(page, "texts.uk.js")["texts"]["coding"]
                self.start_coding_training(page)
                self.pass_coding_training(page, wrong=3)
                self.assertIn(texts["trainingRepeat"][3:-4], page.locator(".screen").inner_html())
                page.get_by_role("button", name="Почати тренування").click()
                page.locator(".coding-frame").wait_for()
                self.pass_coding_training(page, wrong=4)  # wrong again: no third attempt
                self.assertIn(texts["main"][3:19], page.locator(".screen").inner_html())  # the main part follows
                page.get_by_role("button", name="Почати", exact=True).click()
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_practice_attempts_n"], 2)
                self.assertEqual(summary["coding_practice_errors_1"], 3)
                self.assertEqual(summary["coding_practice_errors_2"], 4)
                first, second = log["practice"]["attempts"]
                self.assertEqual([a["symbol"] for a in first["answers"] if a["ok"]], SEQUENCE["practice"][0])
                self.assertEqual([a["symbol"] for a in second["answers"] if a["ok"]], SEQUENCE["practice"][1])
                self.assertEqual(first["errors_n"], 3)
                self.assertEqual(first["status"], "done")
                self.assertEqual(errors, [])

    def test_the_training_has_no_time_limit(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=500")
                self.start_coding_training(page)
                page.wait_for_timeout(1500)  # longer than the main part's limit
                self.assertEqual(page.locator(".coding-frame").count(), 1)
                self.assertEqual(errors, [])


class StimuliAndDataTest(CodingTestCase):
    def test_the_first_session_and_the_retest_show_the_same_figures_in_the_same_order(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                shown = []
                for retest in (False, True):
                    page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=1500", retest=retest)
                    self.main_part(page)
                    self.bot_coding(page, 25)
                    summary, log = self.result(page, receiver)
                    shown.append([a["symbol"] for a in log["main"]["answers"]])
                    context.close()  # a page in the background gets no animation frames
                    self.assertEqual(summary["coding_symbols_version"], "1")
                    self.assertEqual(summary["coding_sequence_version"], "1")
                    self.assertEqual(log["symbols"]["set"], "K")
                    self.assertEqual(log["symbols"]["ids"], [f"k{i}" for i in range(1, 10)])
                    self.assertEqual(log["sequence"]["length"], 180)
                    self.assertEqual(errors, [])
                self.assertEqual(shown[0], shown[1])
                self.assertEqual(shown[0], SEQUENCE["items"][:25])

    def test_retest_and_first_session_have_the_coding_block(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                self.assertIn("coding", [b[0] for b in self.session_blocks(page, retest=True)])
                self.assertIn("coding", [b[0] for b in self.session_blocks(page)])
                self.assertFalse([b for b in self.session_blocks(page) if b[0] == "coding" and b[2]])  # not a placeholder

    def test_what_is_sent(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=1200")
                self.main_part(page, wrong=3)
                self.bot_coding(page, 20, wrong=[4])
                summary, log = self.result(page, receiver)
                env = {k for k in summary if k.startswith(("coding_hidden", "coding_blur", "coding_fs_exit", "coding_resize",
                                                            "coding_zoom", "coding_touch", "coding_idle"))}
                self.assertEqual({k for k in summary if k.startswith("coding_")}, COLUMNS | env)
                self.assertEqual(len(env), 11)
                self.assertEqual(summary["coding_practice_attempts_n"], 2)
                self.assertEqual(summary["coding_correct_n"], 19)
                for key in ["symbols", "sequence", "sizes_mm", "scale_source", "practice", "main", "env"]:
                    self.assertIn(key, log)
                self.assertEqual(log["sizes_mm"], {"figure": 14, "key_cell": 22, "key_digit": 5, "frame": 28})
                self.assertEqual(set(log["main"]["answers"][0]), {"i", "symbol", "pressed", "ok", "rt_ms", "t_ms"})
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])


class ScreenTest(CodingTestCase):
    def test_the_key_and_the_frame_are_in_mm_and_fit_a_small_laptop(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(
                    browser, init_script="localStorage.setItem('tmtua.dev.calibration', JSON.stringify("
                    "{pxPerMm: 4.44, dpr: window.devicePixelRatio, suspect: false, savedAt: '2026-11-16T10:00:00Z'}));",
                    viewport={"width": 1366, "height": 600})
                page, errors = self.open(browser, "?mode=dev&only=coding", context=context)
                self.start_coding_training(page)
                key = page.locator(".coding-key").bounding_box()
                frame = page.locator(".coding-frame").bounding_box()
                self.assertAlmostEqual(key["width"], 9 * 22 * 4.44, delta=1)
                self.assertAlmostEqual(frame["width"], 28 * 4.44, delta=1)
                self.assertEqual(page.locator(".coding-key [data-digit]").all_text_contents(), [str(i) for i in range(1, 10)])
                run = page.locator(".coding-run").bounding_box()
                self.assertLessEqual(key["y"] + key["height"], frame["y"])
                self.assertGreaterEqual(key["y"], run["y"])
                self.assertLessEqual(page.locator(".coding-hint").bounding_box()["y"] + 40, run["y"] + run["height"])
                # Nothing but the key, the figure and the hint: no timer, no counter.
                self.assertEqual(page.locator(".coding-run").inner_text().split(), ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
                                 + page.locator(".coding-hint").inner_text().split())
                self.assertEqual(errors, [])


class MonitorTest(CodingTestCase):
    def test_leaving_around_the_task_is_recorded_and_the_main_part_has_its_own_span(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=1500")
                page.evaluate("() => window.dispatchEvent(new Event('blur'))")  # in the instruction
                page.wait_for_timeout(250)
                page.evaluate("() => window.dispatchEvent(new Event('focus'))")
                self.main_part(page)
                page.evaluate("() => window.dispatchEvent(new Event('blur'))")  # in the main part
                page.wait_for_timeout(300)
                page.evaluate("() => window.dispatchEvent(new Event('focus'))")
                summary, log = self.result(page, receiver)
                self.assertEqual(summary["coding_blur_n"], 2)
                self.assertGreaterEqual(summary["coding_blur_ms"], 500)
                types = [e["type"] for e in log["env"]["events"]]
                self.assertEqual(types.count("test_start"), 1)
                self.assertEqual(types.count("test_end"), 1)
                self.assertEqual(log["main"]["during_test"]["blur_n"], 1)
                self.assertGreaterEqual(log["main"]["during_test"]["blur_ms"], 250)
                # The same in the table (decision 165): only the main part, not the instruction before it.
                self.assertEqual(summary["coding_test_blur_n"], 1)
                self.assertGreaterEqual(summary["coding_test_blur_ms"], 250)
                self.assertEqual(summary["coding_test_blur_ms"], log["main"]["during_test"]["blur_ms"])
                for key in ("hidden_n", "hidden_ms", "fs_exit_n", "fs_exit_ms"):
                    self.assertEqual(summary[f"coding_test_{key}"], 0, key)
                self.assertEqual(errors, [])

    def test_page_zoom_keys_are_blocked_during_the_task(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors, context, receiver = self.open_coding(browser, "&set.coding.durationMs=800")
                self.start_coding_training(page)
                self.key(page, "Equal", metaKey=True)
                self.key(page, "Minus", ctrlKey=True)
                self.pass_coding_training(page)
                page.get_by_role("button", name="Почати", exact=True).click()
                summary, _ = self.result(page, receiver)
                self.assertEqual(summary["coding_zoom_blocked_n"], 2)
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

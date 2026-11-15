"""Checks of the TMT instructions and practice (task T1.3) in Chromium and
WebKit: the scenario "Practice" of docs/14, 3.2 (errors in all five attempts:
the hint after the second, the status practice_failed after the fifth) and
its neighbours, with a bot that makes the practice errors on purpose.

Run from the app/ folder: ../.venv/bin/python -m unittest tests.test_tmt_practice -v
"""

import unittest

from playwright.sync_api import expect

from harness import AppTestCase

FAST = "&set.send.retryBaseMs=100&set.send.retryMaxMs=500"
A = "TMT, частина A"
B = "TMT, частина B"

# The practice has 8 circles. Orders of clicks (indexes in path order; None is
# a click beside the circles):
CLEAN = None  # all circles in order
FAIL = [0, 2, 1, 2, 3, 4, 5, 6, 7]  # the third circle where the second is due: one error, then to the end
NOISY = [0, None, 0, 1, 1, 2, 3, None, 4, 5, 6, 7]  # misses and double clicks: not errors

RETRY = "У пробній спробі була помилка"
HINT = "Знову була помилка"
MAIN = "Пробну спробу пройдено"


class PracticeTestCase(AppTestCase):
    def open_part(self, browser, block="tmt_a", extra="", mode="dev"):
        context, receiver = self.new_context(browser)
        page, errors = self.open(browser, f"?mode={mode}&only={block}{FAST}{extra}", context=context)
        return context, receiver, page, errors

    def screen(self, page):
        return page.locator(".screen")

    def attempt(self, page, order=CLEAN, first=False):
        """One practice attempt: from the instruction (first) or from the
        screen before it."""
        points = self.start_practice(page) if first else self.next_attempt(page)
        self.click_tmt(page, points, order=order)

    def sent(self, receiver, block):
        [message] = [m for m in receiver.accepted if m["block"] == block]
        return message["summary"], message["log"]


class PracticeScenarioTest(PracticeTestCase):
    def test_errors_in_all_five_attempts(self):
        """Scenario "Practice": the hint after the second, the end after the fifth."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser)
                self.tmt_lead(page, A).wait_for()
                self.attempt(page, FAIL, first=True)
                expect(self.screen(page)).to_contain_text(RETRY)  # after the first: try again
                expect(self.screen(page)).not_to_contain_text(HINT)
                self.attempt(page, FAIL)
                expect(self.screen(page)).to_contain_text(HINT)  # after the second: the hint
                expect(self.screen(page)).to_contain_text("Шукайте кружечок із наступним числом")
                for _ in range(2):  # attempts 3 and 4: the hint again
                    self.attempt(page, FAIL)
                    expect(self.screen(page)).to_contain_text(HINT)
                self.attempt(page, FAIL)  # the fifth
                expect(page.locator(".dev-status")).to_have_text("practice_failed")
                self.assertEqual(page.locator(".tmt-run").count(), 0)  # no test, no screen before it
                self.wait_delivered(page)

                summary, log = self.sent(receiver, "tmt_a")
                self.assertEqual(summary["status"], "practice_failed")
                self.assertEqual(summary["tmt_a_practice_attempts_n"], 5)
                self.assertNotIn("tmt_a_status", summary)  # the test never ran
                self.assertNotIn("tmt_a_time_ms", summary)
                self.assertEqual(len(log["practice"]["attempts"]), 5)
                self.assertEqual(log["practice"]["max_attempts"], 5)
                for number, attempt in enumerate(log["practice"]["attempts"], 1):
                    self.assertEqual((attempt["attempt"], attempt["part"], attempt["errors_n"]),
                                     (number, "practice_a", 1))
                    self.assertEqual(attempt["status"], "complete")
                    self.assertEqual(len(attempt["clicks"]), 9)  # every click of the attempt
                    self.assertEqual([c["result"] for c in attempt["clicks"]].count("error"), 1)
                    self.assertNotIn("trajectory", attempt)  # the author's answer of 16.11.2026
                    self.assertIsNone(attempt["time_limit_ms"])
                self.assertNotIn("clicks", log)  # the log of the test itself is absent
                self.assertEqual(receiver.blocks(), ["tmt_a"])
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_error_in_the_first_clean_second_goes_to_the_test(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser)
                self.attempt(page, FAIL, first=True)
                expect(self.screen(page)).to_contain_text(RETRY)
                self.attempt(page, CLEAN)  # clean: to the screen before the test
                expect(self.screen(page)).to_contain_text(MAIN)
                page.get_by_role("button", name="Почати", exact=True).click()
                points = self.field_points(page)
                self.click_tmt(page, points)
                page.locator(".dev-end").wait_for()
                self.wait_delivered(page)

                summary, log = self.sent(receiver, "tmt_a")
                self.assertNotIn("status", summary)  # no early end
                self.assertEqual(summary["tmt_a_practice_attempts_n"], 2)
                self.assertEqual(summary["tmt_a_status"], "complete")
                self.assertEqual(summary["tmt_a_targets_done"], 25)
                self.assertEqual([a["errors_n"] for a in log["practice"]["attempts"]], [1, 0])
                self.assertEqual(log["part"], "a")  # the test, not the practice
                self.assertEqual(len(log["clicks"]), 25)
                self.assertGreater(len(log["trajectory"]), 1)  # the test keeps its trajectory
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_hint_before_the_third_attempt_and_a_pass_on_it(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser)
                self.attempt(page, FAIL, first=True)
                self.attempt(page, FAIL)
                expect(self.screen(page)).to_contain_text(HINT)
                self.attempt(page, CLEAN)  # the third
                expect(self.screen(page)).to_contain_text(MAIN)
                page.get_by_role("button", name="Почати", exact=True).click()
                self.click_tmt(page, self.field_points(page))
                page.locator(".dev-end").wait_for()
                self.wait_delivered(page)
                summary, log = self.sent(receiver, "tmt_a")
                self.assertEqual(summary["tmt_a_practice_attempts_n"], 3)
                self.assertEqual([a["errors_n"] for a in log["practice"]["attempts"]], [1, 1, 0])
                self.assertEqual(errors, [])

    def test_misses_and_double_clicks_do_not_fail_the_practice(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser)
                self.tmt_lead(page, A).wait_for()
                points = self.start_practice(page)
                # Practice field: the label in the corner, 8 circles, no time limit.
                expect(page.locator(".tmt-corner-label")).to_have_text("Пробна спроба")
                self.assertEqual(page.locator(".tmt-run .tmt-circle").count(), 8)
                self.click_tmt(page, points, order=NOISY)
                expect(self.screen(page)).to_contain_text(MAIN)  # no "try again" in between
                page.get_by_role("button", name="Почати", exact=True).click()
                points = self.field_points(page)
                self.assertEqual(page.locator(".tmt-corner-label").count(), 0)  # the test has no label
                self.click_tmt(page, points)
                page.locator(".dev-end").wait_for()
                self.wait_delivered(page)
                summary, log = self.sent(receiver, "tmt_a")
                self.assertEqual(summary["tmt_a_practice_attempts_n"], 1)
                [attempt] = log["practice"]["attempts"]
                self.assertEqual((attempt["errors_n"], attempt["repeat_n"], attempt["miss_n"]), (0, 2, 2))
                self.assertEqual(attempt["targets_done"], 8)
                self.assertEqual(summary["tmt_a_time_ms"], log["time_ms"])
                self.assertEqual(errors, [])

    def test_the_practice_has_no_time_limit(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, extra="&set.tmt.timeLimitMs=1500")
                points = self.start_practice(page, A)
                page.mouse.click(*points["cross"])
                page.wait_for_timeout(2200)  # longer than the limit of the test
                for point in points["circles"]:
                    page.mouse.click(*point)
                expect(self.screen(page)).to_contain_text(MAIN)  # passed, not "timeout"
                page.get_by_role("button", name="Почати", exact=True).click()
                page.locator(".tmt-run").wait_for()
                self.assertEqual(errors, [])

    def test_attempt_limit_is_a_parameter(self):
        """In dev the number of attempts can be lowered to try the failure out."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, extra="&set.tmt.practiceMaxAttempts=2")
                self.attempt(page, FAIL, first=True)
                self.attempt(page, FAIL)
                expect(page.locator(".dev-status")).to_have_text("practice_failed")
                self.wait_delivered(page)
                summary, log = self.sent(receiver, "tmt_a")
                self.assertEqual(summary["tmt_a_practice_attempts_n"], 2)
                self.assertEqual(log["practice"]["max_attempts"], 2)
                self.assertEqual(errors, [])


class PracticePartBTest(PracticeTestCase):
    def test_part_b_letters_and_alternation(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_part(browser, "tmt_b")
                expect(self.tmt_lead(page, B)).to_contain_text("Першу частину завершено")
                expect(self.tmt_lead(page, B)).to_contain_text("1 → А → 2 → Б → 3 → В")
                self.assertEqual(self.tmt_lead(page, A).count(), 0)
                self.attempt(page, FAIL, first=True)  # a number where a letter is due
                expect(self.screen(page)).to_contain_text("чергуйте цифри й літери")
                self.attempt(page, FAIL)
                expect(self.screen(page)).to_contain_text(HINT)
                expect(self.screen(page)).to_contain_text("Після цифри завжди йде літера")
                self.attempt(page, CLEAN)
                expect(self.screen(page)).to_contain_text("Чергуйте цифри й літери, як у пробній")
                page.get_by_role("button", name="Почати", exact=True).click()
                points = self.field_points(page)
                self.click_tmt(page, points)
                page.locator(".dev-end").wait_for()
                self.wait_delivered(page)
                summary, log = self.sent(receiver, "tmt_b")
                self.assertEqual(summary["tmt_b_practice_attempts_n"], 3)
                self.assertEqual(summary["tmt_b_status"], "complete")
                attempts = log["practice"]["attempts"]
                self.assertEqual([a["part"] for a in attempts], ["practice_b"] * 3)
                self.assertEqual([a["err_alternation_n"] for a in attempts], [1, 1, 0])
                self.assertEqual(log["part"], "b")
                self.assertEqual(errors, [])


class PracticeSessionTest(PracticeTestCase):
    def test_failed_practice_ends_a_whole_session(self):
        """As a participant sees it (pilot): the thanks text, the status in the
        data, part B never starts."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, "?mode=pilot", context=context)
                texts = self.module(page, "texts.uk.js")["texts"]
                for block in self.session_blocks(page)[:7]:  # device check .. fullscreen
                    self.pass_block(page, *block)
                self.attempt(page, FAIL, first=True)
                for _ in range(4):
                    self.attempt(page, FAIL)
                expect(page.locator(".message")).to_have_text(texts["end"]["practice_failed"], timeout=15000)
                self.assertEqual(receiver.blocks()[-1], "tmt_a")
                self.assertNotIn("tmt_b", receiver.blocks())
                summary, _ = self.sent(receiver, "tmt_a")
                self.assertEqual(summary["status"], "practice_failed")
                # Counted from the start of the task: the instruction and the practice.
                self.assertEqual(summary["tmt_a_touch_n"], 0)
                self.assertEqual(errors, [])


class PracticeScreensTest(PracticeTestCase):
    def test_every_screen_fits_a_small_window(self):
        """The button of each instruction screen is in view in a 1366 x 600
        window (docs/12: no scrolling on a 1366 x 768 laptop)."""
        for browser in self.browsers:
            for block, label in [("tmt_a", A), ("tmt_b", B)]:
                with self.subTest(browser=browser.browser_type.name, block=block):
                    context, receiver = self.new_context(browser, viewport={"width": 1366, "height": 600})
                    page, errors = self.open(browser, f"?mode=dev&only={block}{FAST}", context=context)
                    self.tmt_lead(page, label).wait_for()
                    self.assertTrue(self.button_in_view(page, "Почати пробну спробу"))
                    self.attempt(page, FAIL, first=True)
                    self.assertTrue(self.button_in_view(page, "Спробувати ще раз"))  # try again
                    self.attempt(page, FAIL)
                    self.assertTrue(self.button_in_view(page, "Спробувати ще раз"))  # the hint
                    self.attempt(page, CLEAN)
                    self.assertTrue(self.button_in_view(page, "Почати", exact=True))  # the main screen
                    self.assertEqual(errors, [])

    def button_in_view(self, page, name, exact=False):
        button = page.get_by_role("button", name=name, exact=exact)
        button.wait_for()
        box = button.bounding_box()
        size = page.viewport_size
        return box["y"] >= 0 and box["y"] + box["height"] <= size["height"]


if __name__ == "__main__":
    unittest.main()

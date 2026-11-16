"""Checks of the derived TMT columns (task T1.4): tmt_b_minus_a_ms (B-A, in ms)
and tmt_b_over_a (B/A, 3 decimals).

The rule is a PROPOSAL to the author, not an approved decision (docs/11, 5.1):
both columns are filled only when BOTH parts ended with status "complete";
after a timeout time_ms is the limit itself, so a difference would be false.
In every other case the columns are empty (null). No other thresholds or
exclusions exist.

Run from the app/ folder: ../.venv/bin/python -m unittest tests.test_tmt_derived -v
"""

import unittest

from playwright.sync_api import expect

from harness import AppTestCase

FAST = "&set.send.retryBaseMs=100&set.send.retryMaxMs=500"
A = "TMT, частина A"
B = "TMT, частина B"
FAIL = [0, 2, 1, 2, 3, 4, 5, 6, 7]  # the practice: one error
MINUS, OVER = "tmt_b_minus_a_ms", "tmt_b_over_a"

DERIVED = """([a, b]) => import('./src/tasks/tmt.js').then(m => m.tmtDerived(a, b))"""


def part(status, time_ms):
    return {"status": status, "time_ms": time_ms}


class DerivedRuleTest(AppTestCase):
    """The rule itself, without a field on the screen."""

    def derive(self, a, b):
        if not hasattr(self, "page"):
            self.page, _ = self.open(self.browsers[0], "?mode=dev")
        return self.page.evaluate(DERIVED, [a, b])

    def test_both_complete(self):
        got = self.derive(part("complete", 20000), part("complete", 48400))
        self.assertEqual(got, {MINUS: 28400, OVER: 2.42})

    def test_ratio_is_rounded_to_three_decimals(self):
        # 31234 / 12345 = 2.5300526...; 2/3 = 0.6666... (B faster than A is possible, so a negative difference too)
        self.assertEqual(self.derive(part("complete", 12345), part("complete", 31234))[OVER], 2.53)
        self.assertEqual(self.derive(part("complete", 3000), part("complete", 2000)), {MINUS: -1000, OVER: 0.667})
        self.assertEqual(self.derive(part("complete", 7000), part("complete", 9999))[OVER], 1.428)

    def test_b_minus_a_and_not_a_minus_b(self):
        self.assertEqual(self.derive(part("complete", 10000), part("complete", 25000))[MINUS], 15000)
        self.assertEqual(self.derive(part("complete", 10000), part("complete", 25000))[OVER], 2.5)

    def test_a_timeout_leaves_both_empty(self):
        got = self.derive(part("timeout", 300000), part("complete", 40000))
        self.assertEqual(got, {MINUS: None, OVER: None})

    def test_b_timeout_leaves_both_empty(self):
        got = self.derive(part("complete", 20000), part("timeout", 300000))
        self.assertEqual(got, {MINUS: None, OVER: None})

    def test_both_timeout_leaves_both_empty(self):
        got = self.derive(part("timeout", 300000), part("timeout", 300000))
        self.assertEqual(got, {MINUS: None, OVER: None})

    def test_missing_part_leaves_both_empty(self):
        self.assertEqual(self.derive(None, part("complete", 40000)), {MINUS: None, OVER: None})
        self.assertEqual(self.derive(part("complete", 20000), None), {MINUS: None, OVER: None})

    def test_zero_time_of_a_does_not_divide(self):
        self.assertEqual(self.derive(part("complete", 0), part("complete", 40000)), {MINUS: None, OVER: None})


class DerivedSessionTest(AppTestCase):
    """A bot goes through A and B of a session (everything from tmt_a on)."""

    def open_session(self, browser, extra=""):
        context, receiver = self.new_context(browser)
        page, errors = self.open(browser, f"?mode=dev&start=tmt_a{FAST}{extra}", context=context)
        return context, receiver, page, errors

    def finish_part(self, page, label, order=None, wait_ms=0):
        """The bot passes the practice, then the test. With a wait the test
        takes longer (the bot is fast); with an order of clicks it stops on a
        limit and the participant gets the timeout screen."""
        points = self.start_tmt(page, label)
        page.mouse.click(*points["cross"])
        circles = points["circles"]
        for index in range(len(circles)) if order is None else order:
            if wait_ms and index == 12:
                page.wait_for_timeout(wait_ms)
            page.mouse.click(*circles[index])
        if order is not None:
            expect(page.locator(".screen")).to_contain_text("Час на цю частину вийшов", timeout=10000)
            page.get_by_role("button", name="Далі").click()
        else:
            page.locator(".tmt-run").wait_for(state="detached")

    def delivered(self, page, receiver):
        page.locator(".placeholder").wait_for()  # the block after part B
        self.wait_delivered(page)
        by_block = {m["block"]: m for m in receiver.accepted}
        return by_block

    def test_both_complete(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_session(browser)
                self.finish_part(page, A)
                self.finish_part(page, B, wait_ms=900)
                sent = self.delivered(page, receiver)
                a, b = sent["tmt_a"]["summary"], sent["tmt_b"]["summary"]
                self.assertEqual((a["tmt_a_status"], b["tmt_b_status"]), ("complete", "complete"))
                self.assertGreater(b["tmt_b_time_ms"], a["tmt_a_time_ms"] + 800)
                self.assertEqual(b[MINUS], b["tmt_b_time_ms"] - a["tmt_a_time_ms"])
                self.assertGreater(b[MINUS], 800)
                self.assertEqual(b[OVER], round(b["tmt_b_time_ms"] / a["tmt_a_time_ms"], 3))
                self.assertGreater(b[OVER], 1)
                self.assertEqual(len(str(b[OVER]).split(".")[-1]) <= 3, True)
                # They belong to the message of part B only, and only once.
                self.assertNotIn(MINUS, a)
                self.assertNotIn(OVER, a)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_b_timeout(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_session(browser, "&set.tmt.timeLimitMs=2500")
                self.finish_part(page, A)
                self.finish_part(page, B, order=[0, 1, 2])
                sent = self.delivered(page, receiver)
                a, b = sent["tmt_a"]["summary"], sent["tmt_b"]["summary"]
                self.assertEqual((a["tmt_a_status"], b["tmt_b_status"]), ("complete", "timeout"))
                self.assertEqual(b["tmt_b_time_ms"], 2500)  # the limit: a difference would be false
                self.assertIn(MINUS, b)  # the columns exist, empty
                self.assertIn(OVER, b)
                self.assertIsNone(b[MINUS])
                self.assertIsNone(b[OVER])
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_a_timeout(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_session(browser, "&set.tmt.timeLimitMs=2500")
                self.finish_part(page, A, order=[0, 1, 2])
                self.finish_part(page, B)
                sent = self.delivered(page, receiver)
                a, b = sent["tmt_a"]["summary"], sent["tmt_b"]["summary"]
                self.assertEqual((a["tmt_a_status"], b["tmt_b_status"]), ("timeout", "complete"))
                self.assertEqual(a["tmt_a_time_ms"], 2500)
                self.assertIn(MINUS, b)
                self.assertIsNone(b[MINUS])
                self.assertIsNone(b[OVER])
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_practice_failed_in_a_has_no_columns(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_session(browser, "&set.tmt.practiceMaxAttempts=1")
                points = self.start_practice(page, A)
                self.click_tmt(page, points, order=FAIL)
                expect(page.locator(".dev-status")).to_have_text("practice_failed")
                self.wait_delivered(page)
                self.assertEqual(receiver.blocks()[-1], "tmt_a")
                for message in receiver.accepted:
                    self.assertNotIn(MINUS, message["summary"])
                    self.assertNotIn(OVER, message["summary"])
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_practice_failed_in_b_has_no_columns(self):
        """A is done, B stops at its practice: the test of B never ran, so
        there is nothing to subtract."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_session(browser, "&set.tmt.practiceMaxAttempts=1")
                self.finish_part(page, A)
                points = self.start_practice(page, B)
                self.click_tmt(page, points, order=FAIL)
                expect(page.locator(".dev-status")).to_have_text("practice_failed")
                self.wait_delivered(page)
                summaries = {m["block"]: m["summary"] for m in receiver.accepted}
                self.assertEqual(summaries["tmt_a"]["tmt_a_status"], "complete")
                self.assertNotIn(MINUS, summaries["tmt_b"])
                self.assertNotIn(OVER, summaries["tmt_b"])
                self.assertNotIn("tmt_b_status", summaries["tmt_b"])
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_part_b_alone_leaves_the_columns_empty(self):
        """A dev link with only=tmt_b: part A did not run in this session."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, f"?mode=dev&only=tmt_b{FAST}", context=context)
                self.click_tmt(page, self.start_tmt(page, B))
                page.locator(".dev-end").wait_for()
                self.wait_delivered(page)
                [message] = [m for m in receiver.accepted if m["block"] == "tmt_b"]
                self.assertIsNone(message["summary"][MINUS])
                self.assertIsNone(message["summary"][OVER])
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

"""Checks of the whole session (task T4.1) in Chromium and WebKit: all blocks
in their fixed order with every message arriving once and in order, the total
time and the timeline of the blocks that the thanks block sends, the longest
stretch without input that each task records, and several sessions going on
at once without mixing.

The "at once" is interleaved: one browser process cannot run two bots in
parallel threads, so three sessions in three contexts are advanced block by
block in turn. Real parallel sessions against the real receiver: see
tests/live_sessions.py.

Run from the app/ folder: ../.venv/bin/python -m unittest discover -s tests -p "test_session.py" -v
"""

import re
import unittest

from harness import AppTestCase

FAST = "&set.send.retryBaseMs=100&set.send.retryMaxMs=500"
TASKS = ["tmt_a", "tmt_b", "coding", "stroop", "sart"]
ENV_COLUMNS = ["hidden_n", "hidden_ms", "blur_n", "blur_ms", "fs_exit_n", "fs_exit_ms", "resize_n", "zoom_n",
               "zoom_blocked_n", "touch_n", "idle_max_ms"]
CODE_ALPHABET = re.compile(r"^[a-z0-9]{10}$")


class SessionCase(AppTestCase):
    def blocks_of(self, page, retest=False):
        return self.session_blocks(page, retest=retest)

    def begin(self, browser, query=f"?mode=pilot{FAST}"):
        context, receiver = self.new_context(browser)
        page, errors = self.open(browser, query, context=context)
        return context, receiver, page, errors

    def run_session(self, page, retest=False):
        for block_id, label, placeholder in self.blocks_of(page, retest):
            if block_id == "retest_invite":
                self.pass_invite(page, None)
            else:
                self.pass_block(page, block_id, label, placeholder)
        # the thank-you text appears once everything is delivered (pilot mode has no dev handle)
        page.locator(".message", has_text="Дякуємо").wait_for(timeout=20000)


class WholeSessionTest(SessionCase):
    def test_a_whole_first_session_in_order(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.begin(browser)
                ids = [b[0] for b in self.blocks_of(page)]
                self.run_session(page)
                messages = receiver.accepted

                # every block that has something to send, once, in the fixed order (an accepted device sends nothing)
                self.assertEqual([m["block"] for m in messages], [i for i in ids if i != "device_check"])
                # one session, numbered 1..n without gaps, and the participant code
                self.assertEqual(len({m["session_id"] for m in messages}), 1)
                self.assertEqual({m["mode"] for m in messages}, {"pilot"})
                self.assertEqual([m["seq"] for m in messages], list(range(1, len(messages) + 1)))
                self.assertRegex(messages[0]["participant_code"], CODE_ALPHABET)
                self.assertEqual(len({m["participant_code"] for m in messages}), 1)
                # what describes the device goes in the first message only
                self.assertIn("started_at", messages[0]["summary"])
                for message in messages[1:]:
                    self.assertNotIn("started_at", message["summary"], message["block"])
                by_block = {m["block"]: m for m in messages}

                # the five tasks: the circumstances, with the longest stretch without input
                for task in TASKS:
                    summary = by_block[task]["summary"]
                    for column in ENV_COLUMNS:
                        self.assertIn(f"{task}_{column}", summary, task)
                    idle = summary[f"{task}_idle_max_ms"]
                    self.assertIsInstance(idle, int)
                    self.assertGreaterEqual(idle, 0)
                    self.assertEqual(by_block[task]["log"]["env"]["idle_max_ms"], idle)
                    self.assertLessEqual(idle, by_block[task]["log"]["env"]["duration_ms"])

                # the end: the status, the total time and the timeline of the blocks
                thanks = by_block["thanks"]
                summary, log = thanks["summary"], thanks["log"]
                self.assertEqual(summary["status"], "complete")
                self.assertIsInstance(summary["total_time_ms"], int)
                self.assertEqual(log["total_ms"], summary["total_time_ms"])
                self.assertEqual([b["id"] for b in log["blocks"]], ids)  # all blocks, the device check too
                previous_end = 0
                for entry in log["blocks"]:
                    self.assertIsNotNone(entry["end_ms"], entry)
                    self.assertLessEqual(previous_end, entry["start_ms"], entry)
                    self.assertLessEqual(entry["start_ms"], entry["end_ms"], entry)
                    previous_end = entry["end_ms"]
                self.assertLessEqual(previous_end, summary["total_time_ms"])
                # the whole is longer than the timed parts together
                timed = sum(by_block[b]["summary"][f"{b}_time_ms"] for b in ["tmt_a", "tmt_b", "coding", "sart"])
                self.assertGreater(summary["total_time_ms"], timed)
                # and agrees with the clock times of the first message and the end
                from datetime import datetime
                started = datetime.fromisoformat(messages[0]["summary"]["started_at"].replace("Z", "+00:00"))
                finished = datetime.fromisoformat(summary["finished_at"].replace("Z", "+00:00"))
                self.assertAlmostEqual((finished - started).total_seconds() * 1000, summary["total_time_ms"], delta=3000)

                self.assert_valid_for_receiver(context, messages)
                self.assertEqual(errors, [])

    def test_a_retest_has_the_same_end(self):
        browser = self.browsers[0]
        context, receiver, page, errors = self.begin(browser, f"?mode=pilot&r=k7m2x9pq4a{FAST}")
        ids = [b[0] for b in self.blocks_of(page, retest=True)]
        self.run_session(page, retest=True)
        thanks = receiver.accepted[-1]
        self.assertEqual(thanks["block"], "thanks")
        self.assertEqual(thanks["summary"]["status"], "complete")
        self.assertEqual([b["id"] for b in thanks["log"]["blocks"]], ids)
        self.assertEqual(thanks["log"]["total_ms"], thanks["summary"]["total_time_ms"])
        self.assert_valid_for_receiver(context, receiver.accepted)
        self.assertEqual(errors, [])

    def test_a_session_left_half_way_has_no_end_and_no_total(self):
        browser = self.browsers[0]
        context, receiver, page, errors = self.begin(browser)
        for block_id, label, placeholder in self.blocks_of(page):
            if block_id == "stroop":
                break
            self.pass_block(page, block_id, label, placeholder)
        page.wait_for_timeout(1500)
        self.assertEqual(receiver.blocks()[-1], "coding")  # where the person stopped
        for message in receiver.accepted:
            self.assertNotIn("status", message["summary"])
            self.assertNotIn("total_time_ms", message["summary"])
        page.close()


class SeveralSessionsTest(SessionCase):
    def test_three_sessions_in_turn_stay_apart(self):
        browser = self.browsers[0]
        sessions = [self.begin(browser) for _ in range(3)]
        steps = [self.blocks_of(page) for _, _, page, _ in sessions]
        for index in range(len(steps[0])):
            for (context, receiver, page, errors), blocks in zip(sessions, steps):
                block_id, label, placeholder = blocks[index]
                if block_id == "retest_invite":
                    self.pass_invite(page, None)
                else:
                    self.pass_block(page, block_id, label, placeholder)
        for _, _, page, _ in sessions:
            page.locator(".message", has_text="Дякуємо").wait_for(timeout=20000)
        ids = set()
        codes = set()
        for context, receiver, page, errors in sessions:
            messages = receiver.accepted
            self.assertEqual(messages[-1]["block"], "thanks")
            self.assertEqual(messages[-1]["summary"]["status"], "complete")
            self.assertEqual(len({m["session_id"] for m in messages}), 1)
            self.assertEqual([m["seq"] for m in messages], list(range(1, len(messages) + 1)))
            ids.add(messages[0]["session_id"])
            codes.add(messages[0]["participant_code"])
            self.assertEqual(errors, [])
        self.assertEqual((len(ids), len(codes)), (3, 3))


class IdleTest(SessionCase):
    def open_coding(self, browser):
        context, receiver = self.new_context(browser)
        page, errors = self.open(browser, f"?mode=dev&only=coding{FAST}", context=context)
        page.get_by_role("button", name="Почати тренування").wait_for()
        return context, receiver, page, errors

    def idle_of(self, page, receiver):
        page.locator(".dev-end").wait_for()
        self.wait_delivered(page)
        [message] = [m for m in receiver.accepted if m["block"] == "coding"]
        return message["summary"]["coding_idle_max_ms"], message["log"]["env"]

    def test_a_pause_without_input_is_recorded(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                _, receiver, page, errors = self.open_coding(browser)
                page.wait_for_timeout(2500)  # reading the instruction, or walking away
                self.start_coding(page)
                self.bot_coding(page, 1000)
                page.locator(".coding-run").wait_for(state="detached")
                idle, env = self.idle_of(page, receiver)
                self.assertGreaterEqual(idle, 2400)
                self.assertEqual(env["idle_max_ms"], idle)
                self.assertEqual(errors, [])

    def test_a_task_without_a_pause_has_a_short_one(self):
        browser = self.browsers[0]
        _, receiver, page, errors = self.open_coding(browser)
        self.start_coding(page)
        self.bot_coding(page, 1000)
        page.locator(".coding-run").wait_for(state="detached")
        idle, _ = self.idle_of(page, receiver)
        self.assertLess(idle, 2000)  # a click on the button, then answers one after another
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

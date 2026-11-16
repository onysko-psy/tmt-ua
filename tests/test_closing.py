"""Checks of PSS-10, the questions after the tasks, the invitation to the
retest and the thanks (task T2.3) in Chromium and WebKit: the sum of PSS-10
with the reverse items, what each block sends, the scenario "Email" of
docs/14, 3.2 (the address goes only to the contacts, with the ready letter),
the end text and the status "complete".

Run from the app/ folder: ../.venv/bin/python -m unittest tests.test_closing -v
"""

import re
import unittest

from playwright.sync_api import expect

from harness import AppTestCase

FAST = "&set.send.retryBaseMs=100&set.send.retryMaxMs=500"
SEND, SKIP = "Надіслати й завершити", "Ні, дякую"
ADDRESS = "pilot-check@example.com"
REQUIRED = "Будь ласка, дайте відповідь на це запитання."
INVALID = "Схоже, в адресі помилка. Перевірте її, будь ласка."
TOTAL = """answers => import('./src/tasks/closing.js').then(m => m.pssTotal(answers))"""
LETTER = """args => import('./src/tasks/closing.js').then(m => m.retestLetter({
    date: new Date(args.date), link: args.link }))"""


class ClosingCase(AppTestCase):
    def open_block(self, browser, block, extra=""):
        context, receiver = self.new_context(browser)
        page, errors = self.open(browser, f"?mode=dev&only={block}{FAST}{extra}", context=context)
        return context, receiver, page, errors

    def message(self, page, receiver, block):
        self.wait_delivered(page)
        [message] = [m for m in receiver.accepted if m["block"] == block]
        summary = {k: v for k, v in message["summary"].items()
                   if not k.startswith("device_") and k not in ("session_type", "started_at")}
        return {**message, "summary": summary}

    def error_texts(self, page):
        return page.locator(".field-error:visible").all_text_contents()


class PssSumTest(ClosingCase):
    """The sum of PSS-10 (decision 103): items 4, 5, 7, 8 are scored in reverse."""

    def total(self, answers):
        if not hasattr(self, "page"):
            self.page, _ = self.open(self.browsers[0], "?mode=dev")
        return self.page.evaluate(TOTAL, answers)

    def test_known_sums(self):
        self.assertEqual(self.total([0] * 10), 16)  # four reversed items give 4 each
        self.assertEqual(self.total([4] * 10), 24)  # six direct items give 4 each
        self.assertEqual(self.total([2] * 10), 20)
        self.assertEqual(self.total([4, 4, 4, 0, 0, 4, 0, 0, 4, 4]), 40)  # the most stress
        self.assertEqual(self.total([0, 0, 0, 4, 4, 0, 4, 4, 0, 0]), 0)  # the least

    def test_each_item_counts_in_its_own_direction(self):
        for item in range(1, 11):
            answers = [0] * 10
            answers[item - 1] = 3
            reversed_item = item in (4, 5, 7, 8)
            self.assertEqual(self.total(answers), 16 - 3 if reversed_item else 16 + 3, item)


class PssScreenTest(ClosingCase):
    def test_text_and_codes(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "pss10")
                page.locator("fieldset[data-name=pss_1]").wait_for()
                text = page.locator(".form").inner_text()
                self.assertIn("протягом ОСТАННЬОГО МІСЯЦЯ", text)
                self.assertIn("0 = ніколи, 1 = майже ніколи, 2 = іноді, 3 = досить часто, 4 = дуже часто.", text)
                self.assertIn("4. Як часто за останній місяць ви були впевнені, що зможете вирішити свої особисті проблеми?", text)
                self.assertIn("8. Як часто за останній місяць ви почувалися «господарем становища»?", text)
                self.assertEqual(page.locator("fieldset").count(), 10)
                self.assertEqual(page.locator("fieldset[data-name=pss_3] input").count(), 5)
                labels = page.locator("fieldset[data-name=pss_3] label").all_text_contents()
                self.assertEqual([x.strip() for x in labels],
                                 ["ніколи", "майже ніколи", "іноді", "досить часто", "дуже часто"])
                self.submit_form(page)
                self.assertEqual(self.error_texts(page), [REQUIRED] * 10)
                self.assertEqual(receiver.requests, [])
                answers = [0, 1, 2, 3, 4, 0, 1, 2, 3, 4]
                self.pass_pss(page, answers)
                page.locator(".dev-end").wait_for()
                summary = self.message(page, receiver, "pss10")["summary"]
                for number, value in enumerate(answers, 1):
                    self.assertEqual(summary[f"pss_{number}"], value)  # as answered, not reversed
                # direct 0+1+2+0+3+4 = 10, reversed (4-3)+(4-4)+(4-1)+(4-2) = 6
                self.assertEqual(summary["pss_total"], 16)
                self.assertEqual(summary["pss_version"], "veldbrekht_tavrovetska_2022_appendix_a")
                self.assertEqual(len(summary), 12)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])


class PostTest(ClosingCase):
    def test_answers_and_codes(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "post")
                page.locator("fieldset[data-name=distraction]").wait_for()
                self.assertEqual(page.locator("fieldset").count(), 3)
                self.assertIn("(необов’язково)", page.locator(".form").inner_text())
                self.assertIn("Будь ласка, не пишіть свого імені чи контактів.", page.locator(".form").inner_text())
                self.submit_form(page)
                self.assertEqual(self.error_texts(page), [REQUIRED] * 3)  # the comment is optional
                self.pass_post(page, distraction="2", interruption="yes", effort="1")
                page.locator(".dev-end").wait_for()
                summary = self.message(page, receiver, "post")["summary"]
                self.assertEqual(summary, {"post_distraction": 2, "post_interrupted": 1, "post_effort": 1,
                                           "post_comment": None})
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_comment(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "post")
                comment = "Плутала З і 3.\nІнакше все зрозуміло. =1+1"
                self.pass_post(page, distraction="0", interruption="no", effort="5", comment=f"  {comment}  ")
                page.locator(".dev-end").wait_for()
                summary = self.message(page, receiver, "post")["summary"]
                self.assertEqual(summary["post_comment"], comment)
                self.assertEqual((summary["post_distraction"], summary["post_interrupted"], summary["post_effort"]),
                                 (0, 0, 5))
                self.assertEqual(errors, [])

    def test_the_comment_is_limited(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "post")
                page.locator("#field-comment").wait_for()
                self.assertEqual(page.locator("#field-comment").get_attribute("maxlength"), "1000")


class InviteTest(ClosingCase):
    def test_scenario_email(self):
        """The address goes only into the contacts, with the letter."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "retest_invite")
                page.locator("#field-email").wait_for()
                text = page.locator(".form").inner_text()
                self.assertIn("Повторне проходження – за бажанням", text)
                self.assertIn("видалимо після завершення дослідження", text)
                self.assertEqual(page.get_by_role("button").all_text_contents(), [SEND, SKIP])
                self.pass_invite(page, ADDRESS)
                page.locator(".dev-end").wait_for()
                message = self.message(page, receiver, "retest_invite")
                self.assertEqual(message["summary"], {"email_left": 1})
                self.assertNotIn(ADDRESS, str(message["summary"]))  # never into the results
                self.assertEqual(set(message["contact"]), {"email", "letter"})
                self.assertEqual(message["contact"]["email"], ADDRESS)
                code = message["participant_code"]
                letter = message["contact"]["letter"]
                self.assertTrue(letter.startswith("Тема: Запрошення на повторне проходження дослідження\n\nДобрий день!"))
                self.assertIn(f"?r={code}&mode=dev", letter)  # the link of a test session leads to the test data
                self.assertRegex(letter, r"\d{1,2} (січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня) 20\d\d року Ви пройшли")
                self.assertNotIn("{", letter)
                self.assertIn("- відкрийте його на тому самому ноутбуці", letter)
                self.assertNotIn(ADDRESS, letter)
                self.assertIn("Артем Онисько, студент-психолог УКУ", letter)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_no_thanks(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "retest_invite")
                self.pass_invite(page)
                page.locator(".dev-end").wait_for()
                message = self.message(page, receiver, "retest_invite")
                self.assertEqual(message["summary"], {"email_left": 0})
                self.assertNotIn("contact", message)
                self.assertEqual(errors, [])

    def test_a_wrong_address_does_not_go(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "retest_invite")
                page.locator("#field-email").wait_for()
                for bad in ["", "abc", "a@b", "a b@c.d", "@c.de", "a@@c.de"]:
                    page.locator("#field-email").fill(bad)
                    page.get_by_role("button", name=SEND).click()
                    self.assertEqual(self.error_texts(page), [INVALID], bad)
                self.assertEqual(receiver.requests, [])
                self.assertEqual(page.locator(".dev-end").count(), 0)
                page.locator("#field-email").fill("  a.b+c@d.ua ")
                page.get_by_role("button", name=SEND).click()
                page.locator(".dev-end").wait_for()
                message = self.message(page, receiver, "retest_invite")
                self.assertEqual(message["contact"]["email"], "a.b+c@d.ua")
                self.assertEqual(errors, [])

    def test_the_letter_text(self):
        """The letter keeps the wording of docs/12, 3.8."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, _ = self.open(browser, "?mode=dev")
                letter = page.evaluate(LETTER, {"date": "2026-12-03T10:00:00", "link": "https://x.test/?r=abc"})
                self.assertIn("3 грудня 2026 року Ви пройшли онлайн-дослідження «Психометрична оцінка україномовної "
                              "онлайн-версії Trail Making Test» і погодилися пройти його ще раз. Дякуємо!", letter)
                self.assertIn("Ваше персональне посилання: https://x.test/?r=abc\n", letter)
                self.assertIn("Будь ласка, пройдіть його протягом двох тижнів після цього листа.", letter)


class ThanksTest(ClosingCase):
    def finish(self, browser, email):
        """A whole session as a participant (pilot mode: nothing is skipped),
        leaving an address or not."""
        context, receiver = self.new_context(browser)
        page, errors = self.open(browser, f"?mode=pilot{FAST}", context=context)
        for block_id, label, placeholder in self.session_blocks(page):
            if block_id == "retest_invite":
                self.pass_invite(page, email)
            else:
                self.pass_block(page, block_id, label, placeholder)
        return context, receiver, page, errors

    def test_the_end_text_with_an_address(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.finish(browser, ADDRESS)
                expect(page.locator(".message")).to_contain_text("Дякуємо за участь!", timeout=15000)
                text = page.locator(".message").inner_text()
                self.assertIn("Ви пройшли всі завдання, Ваші відповіді збережено.", text)
                self.assertIn("Індивідуальних результатів ми не показуємо", text)
                self.assertIn("Якщо Ви залишили адресу, запрошення надійде не раніше ніж через тиждень.", text)
                self.assertIn("onysko.nz@ucu.edu.ua", text)
                self.assertNotIn(ADDRESS, text)
                self.assertEqual(errors, [])

    def test_the_end_text_without_an_address(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.finish(browser, None)
                expect(page.locator(".message")).to_contain_text("Дякуємо за участь!", timeout=15000)
                text = page.locator(".message").inner_text()
                self.assertNotIn("запрошення надійде", text)
                self.assertIn("onysko.nz@ucu.edu.ua", text)
                self.assertEqual(errors, [])

    def test_the_end_is_recorded_as_complete(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.finish(browser, ADDRESS)
                expect(page.locator(".message")).to_contain_text("Дякуємо за участь!", timeout=15000)
                self.assertEqual(receiver.blocks()[-4:], ["pss10", "post", "retest_invite", "thanks"])
                thanks = receiver.accepted[-1]["summary"]
                self.assertEqual(thanks["status"], "complete")
                self.assertRegex(thanks["finished_at"], r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d")
                self.assertEqual(sum(1 for m in receiver.accepted if "contact" in m), 1)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_a_session_that_ended_early_is_not_complete(self):
        """An early end (no consent) never reaches the thanks."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, f"?mode=pilot{FAST}", context=context)
                self.pass_consent(page, agree=False)
                texts = self.module(page, "texts.uk.js")["texts"]
                expect(page.locator(".message")).to_have_text(texts["end"]["no_consent"], timeout=15000)
                self.assertNotIn("thanks", receiver.blocks())
                self.assertEqual(receiver.accepted[-1]["summary"].get("status"), "no_consent")


class FitTest(ClosingCase):
    def test_post_and_invite_fit_a_laptop_window(self):
        for browser in self.browsers:
            for block in ["post", "retest_invite"]:
                with self.subTest(browser=browser.browser_type.name, block=block):
                    context, receiver = self.new_context(browser, viewport={"width": 1366, "height": 650})
                    page, errors = self.open(browser, f"?mode=dev&only={block}{FAST}", context=context)
                    submit = page.locator(".form-submit")
                    submit.wait_for()
                    box = submit.bounding_box()
                    self.assertLessEqual(box["y"] + box["height"], 650, "the button is below the window edge")
                    self.assertFalse(page.evaluate("document.documentElement.scrollHeight > window.innerHeight"))
                    self.assertEqual(errors, [])

    def test_pss_scrolls_and_its_button_is_reachable(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser, viewport={"width": 1366, "height": 650})
                page, errors = self.open(browser, f"?mode=dev&only=pss10{FAST}", context=context)
                page.locator("fieldset[data-name=pss_1]").wait_for()
                for number in range(1, 11):
                    page.locator(f"fieldset[data-name=pss_{number}] input[value='2']").check()
                button = page.locator(".form-submit")
                button.scroll_into_view_if_needed()
                button.click()
                page.locator(".dev-end").wait_for()
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

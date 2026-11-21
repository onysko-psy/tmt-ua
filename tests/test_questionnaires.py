"""Checks of consent, criteria, biography and the conditions questionnaire
(task T2.2) in Chromium and WebKit: the scenarios "No consent" and
"Exclusion" of docs/14, 3.2, the required answers, what each block sends
(codes, nothing more for a person who does not fit) and that the screens fit
a laptop window without scrolling (the consent scrolls on purpose).

Run from the app/ folder: ../.venv/bin/python -m unittest tests.test_questionnaires -v
"""

import unittest

from playwright.sync_api import expect

from harness import AppTestCase

FAST = "&set.send.retryBaseMs=100&set.send.retryMaxMs=500"
AGREE, DECLINE = "Я погоджуюся", "Я не погоджуюся"


class FormTestCase(AppTestCase):
    def open_block(self, browser, block, mode="dev", extra=""):
        """One block (dev), or the whole session: pilot, as a participant
        sees it, or dev from the consent on (block None; has window.tmtua)."""
        context, receiver = self.new_context(browser)
        if block:
            query = f"?mode=dev&only={block}{FAST}{extra}"
        else:
            query = f"?mode={mode}{FAST}{extra}" + ("&start=consent" if mode == "dev" else "")
        page, errors = self.open(browser, query, context=context)
        return context, receiver, page, errors

    META = ("session_type", "started_at")

    def only_message(self, page, receiver, block, keep_meta=False):
        """The one message of a block. In a single-block run it is also the
        first message of the session, so it carries the device and the start
        time (sender.js); they are dropped unless asked for."""
        self.wait_delivered(page)
        [message] = [m for m in receiver.accepted if m["block"] == block]
        if not keep_meta:
            summary = {k: v for k, v in message["summary"].items() if not k.startswith("device_") and k not in self.META}
            message = {**message, "summary": summary}
        return message

    def error_texts(self, page):
        return page.locator(".field-error:visible").all_text_contents()


class ConsentTest(FormTestCase):
    def test_agree(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "consent")
                self.pass_consent(page)
                page.locator(".dev-end").wait_for()
                message = self.only_message(page, receiver, "consent", keep_meta=True)
                self.assertIn("consent_at", message["summary"])
                self.assertIn("started_at", message["summary"])  # the first message carries the device
                self.assertNotIn("status", message["summary"])
                self.assertEqual(page.locator(".dev-status").count(), 0)  # the session is not ended
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_text_and_buttons(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "consent")
                consent = page.locator(".consent")
                expect(consent.locator("h2")).to_have_text("Інформована згода на участь у дослідженні")
                text = consent.inner_text()
                for part in ["Назва наукового дослідження:", "Онисько Артем Артурович", "onysko.nz@ucu.edu.ua",
                             "близько 150 осіб", "Результатів завдань застосунок не показує.",
                             "Знадобиться банківська картка", "факультет наук про здоров’я"]:
                    self.assertIn(part, text)
                self.assertNotIn("'", text)  # typographic apostrophes
                self.assertNotIn("клацн", text)  # decision 140
                self.assertEqual(consent.locator("ol li").count(), 5)
                self.assertEqual(page.get_by_role("button").all_text_contents(), [AGREE, DECLINE])
                self.assertEqual(errors, [])

    def test_no_consent(self):
        """Scenario "No consent": status no_consent, nothing else is written."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "consent")
                self.pass_consent(page, agree=False)
                expect(page.locator(".dev-status")).to_have_text("no_consent")
                # keep_meta: a refusal must not send the device or the start time.
                message = self.only_message(page, receiver, "consent", keep_meta=True)
                self.assertEqual(message["summary"], {"status": "no_consent"})
                self.assertNotIn("log", message)
                self.assertEqual(receiver.blocks(), ["consent"])
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_no_consent_ends_the_whole_session(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, None, mode="pilot")
                self.pass_consent(page, agree=False)
                texts = self.module(page, "texts.uk.js")["texts"]
                expect(page.locator(".message")).to_have_text(texts["end"]["no_consent"], timeout=15000)
                self.assertEqual(receiver.blocks(), ["consent"])  # no criteria, no calibration
                self.assertEqual(page.locator(".form, .consent").count(), 0)
                self.assertEqual(errors, [])


class CriteriaTest(FormTestCase):
    def run_criteria(self, browser, **answers):
        context, receiver, page, errors = self.open_block(browser, "criteria")
        self.pass_criteria(page, **answers)
        page.locator(".dev-end").wait_for()
        message = self.only_message(page, receiver, "criteria")
        return context, receiver, page, errors, message

    def test_fits(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors, message = self.run_criteria(browser, age=27)
                self.assertEqual(message["summary"]["age"], 27)
                self.assertIsInstance(message["summary"]["age"], int)
                self.assertNotIn("status", message["summary"])
                self.assertNotIn("exclusion_reason", message["summary"])
                self.assertEqual(page.locator(".dev-status").count(), 0)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_age_boundaries(self):
        """18 and 60 take part, 17 and 61 do not (decisions 11, 178)."""
        for browser in self.browsers:
            for age, fits in [(18, True), (45, True), (46, True), (60, True), (17, False), (61, False), (70, False)]:
                with self.subTest(browser=browser.browser_type.name, age=age):
                    *_, page, errors, message = self.run_criteria(browser, age=age)
                    if fits:
                        self.assertEqual(message["summary"], {"age": age})
                    else:
                        self.assertEqual(message["summary"], {"exclusion_reason": "age", "status": "excluded_criteria"})
                    self.assertEqual(errors, [])

    def test_exclusion_keeps_only_the_reason(self):
        """Scenario "Exclusion" (decision 86): age 65 -> excluded_criteria,
        reason age, no age and no other answers."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors, message = self.run_criteria(browser, age=65, tbi="yes", color_vision="yes")
                expect(page.locator(".dev-status")).to_have_text("excluded_criteria")
                self.assertEqual(message["summary"], {"exclusion_reason": "age", "status": "excluded_criteria"})
                self.assertNotIn("log", message)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_each_reason(self):
        cases = [
            (dict(age=30, tbi="yes", color_vision="no"), "tbi"),
            (dict(age=30, tbi="no", color_vision="yes"), "color_vision"),
            (dict(age=30, tbi="yes", color_vision="yes"), "tbi"),  # the order of the questions
        ]
        for browser in self.browsers:
            for answers, reason in cases:
                with self.subTest(browser=browser.browser_type.name, answers=answers):
                    *_, page, errors, message = self.run_criteria(browser, **answers)
                    self.assertEqual(message["summary"], {"exclusion_reason": reason, "status": "excluded_criteria"})
                    self.assertEqual(errors, [])

    def test_exclusion_ends_the_whole_session_with_the_text(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, None, mode="pilot")
                self.pass_consent(page)
                self.pass_criteria(page, age=65)
                texts = self.module(page, "texts.uk.js")["texts"]
                expect(page.locator(".message")).to_have_text(texts["end"]["excluded_criteria"], timeout=15000)
                self.assertEqual(receiver.blocks(), ["consent", "criteria"])
                self.assertEqual(page.locator("fieldset[data-name=sex]").count(), 0)  # no biography
                self.assertEqual(errors, [])

    def test_answers_are_required_and_age_is_a_whole_number(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "criteria")
                page.locator(".form").wait_for()
                self.submit_form(page)  # nothing answered
                self.assertEqual(self.error_texts(page), ["Будь ласка, дайте відповідь на це запитання."] * 3)
                self.assertEqual(receiver.requests, [])
                for bad in ["abc", "27.5", "27,5", "-3", "0", "200", "1e1", "2 7"]:
                    page.locator("#field-age").fill(bad)
                    self.submit_form(page)
                    self.assertEqual(self.error_texts(page)[0], "Вкажіть вік цілим числом, наприклад 27.", bad)
                page.locator("#field-age").fill(" 27 ")
                self.answer(page, "tbi", "no")
                self.submit_form(page)  # the colour question is still open
                self.assertEqual(self.error_texts(page), ["Будь ласка, дайте відповідь на це запитання."])
                self.assertEqual(page.locator(".dev-end").count(), 0)
                self.answer(page, "color_vision", "no")
                self.submit_form(page)
                page.locator(".dev-end").wait_for()
                message = self.only_message(page, receiver, "criteria")
                self.assertEqual(message["summary"], {"age": 27})
                self.assertEqual(errors, [])


class DemographicsTest(FormTestCase):
    def test_answers_and_codes(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "demographics")
                page.locator("fieldset[data-name=sex]").wait_for()
                labels = page.locator("fieldset[data-name=sex] label").all_text_contents()
                self.assertEqual([x.strip() for x in labels], ["Жіноча", "Чоловіча", "Інша", "Не хочу вказувати"])
                self.assertEqual(page.locator("fieldset[data-name=education] input").count(), 7)
                self.submit_form(page)
                self.assertEqual(len(self.error_texts(page)), 2)
                self.answer(page, "sex", "undisclosed")
                self.answer(page, "education", "4")
                self.submit_form(page)
                page.locator(".dev-end").wait_for()
                message = self.only_message(page, receiver, "demographics")
                for key in ["sex", "education"]:
                    self.assertIn(key, message["summary"])
                self.assertEqual((message["summary"]["sex"], message["summary"]["education"]), ("undisclosed", 4))
                self.assertNotIn("age", message["summary"])  # asked with the criteria
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_all_codes(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                for sex in ["female", "male", "other", "undisclosed"]:
                    context, receiver, page, errors = self.open_block(browser, "demographics")
                    self.pass_demographics(page, sex=sex, education="7")
                    page.locator(".dev-end").wait_for()
                    summary = self.only_message(page, receiver, "demographics")["summary"]
                    self.assertEqual((summary["sex"], summary["education"]), (sex, 7))


class ConditionsTest(FormTestCase):
    def test_before_the_tasks_then_three_questions_and_the_device(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "conditions")
                screen = page.locator(".screen", has_text="Перед завданнями")
                expect(screen).to_contain_text("закрийте інші вкладки й програми")
                expect(screen).to_contain_text("Знадобиться банківська картка")
                self.assertEqual(page.locator("form").count(), 0)  # the questions come after
                page.get_by_role("button", name="Далі").click()
                page.locator("fieldset[data-name=sleep]").wait_for()
                names = page.locator("fieldset").evaluate_all("nodes => nodes.map(n => n.dataset.name)")
                self.assertEqual(names, ["sleep", "fatigue", "others", "pointer"])  # decision 142: three and the device
                body = page.locator(".form").inner_text()
                for gone in ["сонлив", "хочеться спати", "Де Ви зараз", "впевнено Ви користуєтеся"]:
                    self.assertNotIn(gone, body)
                self.assertIn("Будь ласка, не змінюйте його до кінця.", body)
                self.submit_form(page)
                self.assertEqual(len(self.error_texts(page)), 4)
                self.assertEqual(receiver.requests, [])
                self.assertEqual(errors, [])

    def test_codes(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "conditions")
                self.pass_conditions(page, sleep="4", fatigue="5", others="yes", pointer="touchpad")
                page.locator(".dev-end").wait_for()
                summary = self.only_message(page, receiver, "conditions")["summary"]
                self.assertEqual((summary["sleep_h"], summary["fatigue"], summary["others_present"],
                                  summary["pointer_self"]), (4, 5, 1, "touchpad"))
                self.assertEqual(list(summary), ["sleep_h", "fatigue", "others_present", "pointer_self"])
                self.assertEqual(errors, [])

    def test_the_other_end_of_the_scales(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, "conditions")
                self.pass_conditions(page, sleep="10", fatigue="1", others="no", pointer="other")
                page.locator(".dev-end").wait_for()
                summary = self.only_message(page, receiver, "conditions")["summary"]
                self.assertEqual((summary["sleep_h"], summary["fatigue"], summary["others_present"],
                                  summary["pointer_self"]), (10, 1, 0, "other"))
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])


class FitTest(FormTestCase):
    def test_screens_fit_a_laptop_window_without_scrolling(self):
        """The form screens (not the consent) fit 1366x650, the visible part
        of a 1366x768 laptop screen; the button is on the screen."""
        for browser in self.browsers:
            for block, prepare in [("criteria", None), ("demographics", None), ("conditions", "form")]:
                with self.subTest(browser=browser.browser_type.name, block=block):
                    context, receiver = self.new_context(browser, viewport={"width": 1366, "height": 650})
                    page, errors = self.open(browser, f"?mode=dev&only={block}{FAST}", context=context)
                    if prepare:
                        page.get_by_role("button", name="Далі").click()
                    submit = page.locator(".form-submit")
                    submit.wait_for()
                    box = submit.bounding_box()
                    self.assertLessEqual(box["y"] + box["height"], 650, "the button is below the window edge")
                    self.assertFalse(page.evaluate("document.documentElement.scrollHeight > window.innerHeight"))
                    self.assertEqual(errors, [])

    def test_the_consent_scrolls_and_its_buttons_are_reachable(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser, viewport={"width": 1366, "height": 650})
                page, errors = self.open(browser, f"?mode=dev&only=consent{FAST}", context=context)
                button = page.get_by_role("button", name=AGREE)
                button.scroll_into_view_if_needed()
                button.click()
                page.locator(".dev-end").wait_for()
                self.assertEqual(errors, [])


class WholeFlowTest(FormTestCase):
    def test_a_session_goes_from_consent_to_calibration_and_each_block_sends_once(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.open_block(browser, None, mode="dev")
                self.pass_consent(page)
                self.pass_criteria(page, age=31)
                self.pass_demographics(page, sex="male", education="6")
                self.pass_conditions(page, sleep="6", fatigue="3", others="yes", pointer="mouse")
                page.locator("#jspsych-resize-handle").wait_for()  # the calibration screen
                self.wait_delivered(page)
                self.assertEqual(receiver.blocks(), ["consent", "criteria", "demographics", "conditions"])
                merged = {}
                for message in receiver.accepted:
                    merged.update(message["summary"])
                for key, value in dict(age=31, sex="male", education=6, sleep_h=6, fatigue=3, others_present=1,
                                       pointer_self="mouse").items():
                    self.assertEqual(merged[key], value, key)
                self.assertIn("consent_at", merged)
                self.assertNotIn("status", merged)
                # Device and start time travel once, with the first message.
                self.assertIn("started_at", receiver.accepted[0]["summary"])
                self.assertTrue(all("started_at" not in m["summary"] for m in receiver.accepted[1:]))
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

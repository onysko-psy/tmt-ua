"""Checks of the retest (task T2.4) in Chromium and WebKit: the personal link
?r=CODE, the flow without biography and invitation, the short confirmation of
the consent, what the session sends (type retest, the code of the first
session, the mark in the contacts), the thanks, and the handling of a link
opened again or with a code the app cannot know (decision 143).

Run from the app/ folder: ../.venv/bin/python -m unittest discover -s tests -p "test_retest.py" -v
"""

import json
import unittest

from playwright.sync_api import expect

from harness import AppTestCase

CODE = "k7m2x9pq4a"  # a valid code: ten characters of the participant-code alphabet
PARSE = "search => import('./src/session.js').then(m => m.parseUrl(search))"
LINK = """args => import('./src/tasks/closing.js').then(m => m.retestLink(
    { origin: args.origin, pathname: args.pathname }, args.code, args.mode))"""
RETEST_IDS = ["device_check", "consent", "conditions", "calibration", "fullscreen", "tmt_a", "tmt_b",
              "coding", "stroop", "sart", "pss10", "post", "thanks"]
# Whatever the first session asks and the retest must not.
FIRST_ONLY = {"age", "sex", "education", "exclusion_reason", "email_left"}


class RetestCase(AppTestCase):
    def finish(self, browser, query=f"?mode=pilot&r={CODE}", context=None, receiver=None):
        """A whole retest as a participant (pilot mode: nothing is skipped)."""
        if context is None:
            context, receiver = self.new_context(browser)
        page, errors = self.open(browser, query, context=context)
        for block_id, label, placeholder in self.session_blocks(page, retest=True):
            self.pass_block(page, block_id, label, placeholder)
        return context, receiver, page, errors


class LinkTest(RetestCase):
    def parse(self, page, search):
        return page.evaluate(PARSE, search)

    def test_a_personal_link_makes_a_retest(self):
        page, _ = self.open(self.browsers[0], "?mode=dev")
        for search, mode in [(f"?r={CODE}", "main"), (f"?r={CODE}&mode=pilot", "pilot"), (f"?mode=dev&r={CODE}", "dev")]:
            session = self.parse(page, search)
            self.assertEqual((session["type"], session["retestCode"], session["mode"]), ("retest", CODE, mode), search)
            self.assertNotIn("error", session)

    def test_a_link_without_a_code_is_the_first_session(self):
        page, _ = self.open(self.browsers[0], "?mode=dev")
        for search in ["", "?mode=pilot", "?mode=dev&start=pss10"]:
            session = self.parse(page, search)
            self.assertEqual((session["type"], session["retestCode"]), ("first", None), search)

    def test_a_code_that_cannot_be_a_code_is_rejected(self):
        page, _ = self.open(self.browsers[0], "?mode=dev")
        bad = ["", "abc", CODE[:-1], CODE + "a", CODE.upper(), "k7m2x9pq4i", "k7m2x9pq40", "k7m2x9pq4l",
               "k7m2x9pq4.", "k7m2x9pq4%20", "k7m2 9pq4a"]
        for code in bad:
            for search in [f"?r={code}", f"?mode=pilot&r={code}", f"?mode=dev&r={code}"]:
                self.assertEqual(self.parse(page, search), {"error": "bad_code"}, search)

    def test_the_mode_is_still_checked(self):
        page, _ = self.open(self.browsers[0], "?mode=dev")
        self.assertEqual(self.parse(page, f"?r={CODE}&mode=pliot"), {"error": "bad_mode"})

    def test_the_dev_controls_stay_dev_only(self):
        page, _ = self.open(self.browsers[0], "?mode=dev")
        session = self.parse(page, f"?r={CODE}&start=pss10&set.tmt.timeLimitMs=1")
        self.assertEqual((session["devStart"], session["overrides"]), (None, {}))

    def test_the_link_of_the_letter_leads_to_the_same_session(self):
        """What the letter holds (retestLink) is read back as a retest of the
        same code in the same mode, and the main link has no mode."""
        page, _ = self.open(self.browsers[0], "?mode=dev")
        for mode in ["main", "pilot", "dev"]:
            link = page.evaluate(LINK, {"origin": "https://x.test", "pathname": "/tmt-ua/", "code": CODE, "mode": mode})
            self.assertEqual(link, f"https://x.test/tmt-ua/?r={CODE}" + ("" if mode == "main" else f"&mode={mode}"))
            session = self.parse(page, link[link.index("?"):])
            self.assertEqual((session["type"], session["retestCode"], session["mode"]), ("retest", CODE, mode))

    def test_a_broken_link_shows_the_message_and_sends_nothing(self):
        for browser in self.browsers:
            for query in [f"?r={CODE[:-1]}", "?r=", f"?mode=pilot&r={CODE.upper()}"]:
                with self.subTest(browser=browser.browser_type.name, query=query):
                    context, receiver = self.new_context(browser)
                    page, errors = self.open(browser, query, context=context)
                    texts = self.module(page, "texts.uk.js")["texts"]
                    expect(page.locator(".message")).to_have_text(texts["errors"]["badLink"])
                    self.assertEqual(page.locator("button").count(), 0)
                    self.assertEqual(receiver.requests, [])
                    self.assertEqual(errors, [])


class FlowTest(RetestCase):
    def test_the_blocks_of_a_retest(self):
        page, _ = self.open(self.browsers[0], "?mode=dev")
        retest = self.session_blocks(page, retest=True)
        self.assertEqual([b[0] for b in retest], RETEST_IDS)
        self.assertEqual([b[0] for b in self.session_blocks(page)][:5],
                         ["device_check", "consent", "criteria", "demographics", "conditions"])  # the first session is as before
        self.assertEqual(len(self.session_blocks(page)), 16)

    def test_the_dev_menu_of_a_retest(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                page, errors = self.open(browser, f"?mode=dev&r={CODE}")
                self.assertEqual(page.locator(".dev-menu tr").evaluate_all("rows => rows.map(r => r.dataset.block)"),
                                 RETEST_IDS)
                self.assertIn(CODE, page.locator(".dev-menu").inner_text())
                # the links keep the code and lead to the retest
                hrefs = page.locator(".dev-menu tr a").evaluate_all("links => links.map(a => a.getAttribute('href'))")
                self.assertTrue(all(f"r={CODE}" in href for href in hrefs), hrefs)
                self.assertEqual(errors, [])

    def test_the_dev_menu_of_the_first_session_offers_a_retest(self):
        page, errors = self.open(self.browsers[0], "?mode=dev")
        href = page.get_by_role("link", name="ретест із новим кодом").get_attribute("href")
        self.assertRegex(href, r"^\?mode=dev&r=[2-9a-hjkmnp-z]{10}$")
        page.get_by_role("link", name="ретест із новим кодом").click()
        page.locator(".dev-menu tr[data-block=conditions]").wait_for()
        self.assertEqual(page.locator(".dev-menu tr[data-block=criteria]").count(), 0)
        page.get_by_role("link", name="до першої сесії").click()
        page.locator(".dev-menu tr[data-block=criteria]").wait_for()

    def test_a_block_of_the_first_session_only_does_not_exist_in_a_retest(self):
        for block in ["criteria", "demographics", "retest_invite"]:
            page, _ = self.open(self.browsers[0], f"?mode=dev&r={CODE}&only={block}")
            expect(page.locator(".message")).to_contain_text(block)


class ConsentTest(RetestCase):
    def test_the_short_confirmation_with_the_full_text_on_the_screen(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, f"?mode=dev&r={CODE}&only=consent", context=context)
                page.locator(".consent").wait_for()
                text = page.locator(".consent").inner_text()
                self.assertIn("Повторне проходження", text)
                self.assertIn("Дякуємо, що повернулися!", text)
                self.assertIn("під тим самим випадковим кодом", text)
                self.assertIn("Цього разу запитань про Вас не буде", text)
                self.assertIn("Будь ласка, проходьте на тому самому пристрої, що й першого разу, і так само мишею чи тачпадом.", text)
                self.assertEqual(page.get_by_role("button").all_text_contents(), ["Я погоджуюся", "Я не погоджуюся"])
                # the full text is folded until asked for, and opens on the same screen
                self.assertIsNone(page.locator("details.consent-full").get_attribute("open"))
                expect(page.get_by_text("Назва наукового дослідження")).to_be_hidden()
                page.get_by_text("Повний текст згоди").click()
                expect(page.get_by_text("Назва наукового дослідження")).to_be_visible()
                expect(page.get_by_text("Контактні дані при виникненні запитань")).to_be_visible()
                self.assertEqual(receiver.requests, [])
                self.assertEqual(errors, [])

    def test_the_first_session_consent_is_unchanged(self):
        page, _ = self.open(self.browsers[0], "?mode=dev&only=consent")
        page.locator(".consent").wait_for()
        self.assertEqual(page.locator("details").count(), 0)
        self.assertIn("Інформована згода на участь у дослідженні", page.locator(".consent").inner_text())

    def test_the_buttons_are_in_the_window_of_a_laptop(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, _ = self.new_context(browser, viewport={"width": 1366, "height": 650})
                page, errors = self.open(browser, f"?mode=dev&r={CODE}&only=consent", context=context)
                button = page.get_by_role("button", name="Я погоджуюся")
                button.wait_for()
                box = button.bounding_box()
                self.assertLessEqual(box["y"] + box["height"], 650)
                self.assertEqual(errors, [])

    def test_a_refusal_ends_the_retest_with_the_status_and_the_type(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, f"?mode=pilot&r={CODE}", context=context)
                self.pass_consent(page, agree=False)
                texts = self.module(page, "texts.uk.js")["texts"]
                expect(page.locator(".message")).to_have_text(texts["end"]["no_consent"], timeout=15000)
                [message] = receiver.accepted
                self.assertEqual(message["participant_code"], CODE)
                self.assertEqual(message["block"], "consent")
                # only the status and that it was the retest: no device, no time
                self.assertEqual(message["summary"], {"session_type": "retest", "status": "no_consent"})
                self.assertNotIn("contact", message)
                self.assert_valid_for_receiver(context, receiver.accepted)
                self.assertEqual(errors, [])

    def test_a_refusal_of_the_first_session_is_as_before(self):
        context, receiver = self.new_context(self.browsers[0])
        page, _ = self.open(self.browsers[0], "?mode=pilot", context=context)
        self.pass_consent(page, agree=False)
        page.locator(".message").wait_for()
        for _ in range(100):
            if receiver.accepted:
                break
            page.wait_for_timeout(100)
        self.assertEqual(receiver.accepted[0]["summary"], {"status": "no_consent"})


class SessionTest(RetestCase):
    def test_a_whole_retest(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.finish(browser)
                texts = self.module(page, "texts.uk.js")["texts"]
                expect(page.locator(".message")).to_contain_text("Дякуємо, що пройшли дослідження вдруге!", timeout=15000)
                text = page.locator(".message").inner_text()
                self.assertIn("Вашу електронну адресу ми видалимо після завершення дослідження.", text)
                self.assertIn("Запитання можна надіслати на onysko.nz@ucu.edu.ua.", text)
                self.assertNotIn("Дякуємо за участь!", text)
                self.assertNotIn("запрошення надійде", text)
                self.assertEqual(receiver.blocks(), [i for i in RETEST_IDS if i != "device_check"])

                messages = receiver.accepted
                # one new session under the code of the first one
                self.assertEqual({m["participant_code"] for m in messages}, {CODE})
                self.assertEqual(len({m["session_id"] for m in messages}), 1)
                self.assertEqual({m["mode"] for m in messages}, {"pilot"})
                first = messages[0]["summary"]
                self.assertEqual(first["session_type"], "retest")
                self.assertIn("started_at", first)
                self.assertTrue(any(k.startswith("device_") for k in first))  # this device is recorded again
                self.assertIn("consent_at", first)
                # nothing of the first session's questionnaires, and no invitation
                for message in messages:
                    self.assertFalse(FIRST_ONLY & set(message["summary"]), message["block"])
                    self.assertNotIn("@", json.dumps(message))
                # the same questions as in the first session where the retest has them
                by_block = {m["block"]: m["summary"] for m in messages}
                self.assertEqual(set(by_block["conditions"]), {"sleep_h", "fatigue", "others_present", "pointer_self"})
                self.assertEqual(by_block["tmt_a"]["layout_version"], "1")  # the same layout (decision 64)
                self.assertEqual(by_block["tmt_a"]["tmt_a_status"], "complete")
                self.assertEqual(by_block["tmt_b"]["tmt_b_status"], "complete")
                self.assertIn("tmt_b_minus_a_ms", by_block["tmt_b"])
                self.assertEqual(by_block["pss10"]["pss_total"], 20)
                self.assertIn("post_effort", by_block["post"])
                # the end: complete, and the contacts row of the code is marked
                thanks = [m for m in messages if m["block"] == "thanks"][0]
                self.assertEqual(thanks["summary"]["status"], "complete")
                self.assertEqual(thanks["contact"], {"retest_done_at": thanks["summary"]["finished_at"]})
                self.assertEqual([m["block"] for m in messages if "contact" in m], ["thanks"])
                self.assert_valid_for_receiver(context, messages)
                self.assertEqual(errors, [])

    def test_a_retest_in_the_main_mode_sends_nothing_while_blocks_are_placeholders(self):
        """As the first session: the main spreadsheet stays empty until all blocks are built."""
        context, receiver, page, errors = self.finish(self.browsers[0], query=f"?r={CODE}")
        expect(page.locator(".message")).to_contain_text("Дякуємо, що пройшли дослідження вдруге!", timeout=15000)
        self.assertEqual(receiver.requests, [])
        self.assertEqual(errors, [])

    def test_the_first_session_marks_no_contact_at_the_end(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, "?mode=dev&only=thanks", context=context)
                page.locator(".dev-end").wait_for()
                self.wait_delivered(page)
                [message] = receiver.accepted
                self.assertEqual(message["summary"]["session_type"], "first")
                self.assertNotIn("contact", message)

    def test_the_thanks_of_a_retest_alone(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, f"?mode=dev&r={CODE}&only=thanks", context=context)
                page.locator(".dev-end").wait_for()
                self.wait_delivered(page)
                [message] = receiver.accepted
                self.assertEqual(message["summary"]["session_type"], "retest")
                self.assertEqual(message["participant_code"], CODE)
                self.assertEqual(list(message["contact"]), ["retest_done_at"])
                self.assert_valid_for_receiver(context, receiver.accepted)


class OpenedAgainTest(RetestCase):
    """Decision 143: nothing is blocked; the analysis keeps the first finished
    retest of a code. Each opening is its own session under the same code."""

    def test_a_finished_retest_can_be_opened_again(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver, page, errors = self.finish(browser)
                expect(page.locator(".message")).to_contain_text("вдруге", timeout=15000)
                done = len(receiver.accepted)
                # the same link, the same browser, after the end
                second, errors2 = self.open(browser, f"?mode=pilot&r={CODE}", context=context)
                second.locator(".consent").wait_for()
                self.assertIn("Повторне проходження", second.locator(".consent").inner_text())
                self.pass_consent(second)
                self.pass_conditions(second)
                second.locator(".jspsych-content, #jspsych-resize-handle").first.wait_for()
                self.wait_delivered_pilot(second, receiver, done + 2)
                ids = {m["session_id"] for m in receiver.accepted}
                self.assertEqual(len(ids), 2)
                self.assertEqual({m["participant_code"] for m in receiver.accepted}, {CODE})
                new = [m for m in receiver.accepted if m["seq"] == 1 and m["session_id"] != receiver.accepted[0]["session_id"]]
                self.assertEqual(new[0]["summary"]["session_type"], "retest")
                self.assertEqual(errors + errors2, [])

    def wait_delivered_pilot(self, page, receiver, count):
        """In pilot mode there is no window.tmtua; wait until the receiver has the messages."""
        for _ in range(150):
            if len(receiver.accepted) >= count:
                return
            page.wait_for_timeout(100)
        self.fail(f"only {len(receiver.accepted)} messages arrived")

    def test_two_openings_are_two_sessions_with_the_same_code(self):
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                pages = [self.open(browser, f"?mode=pilot&r={CODE}", context=context)[0] for _ in range(2)]
                for page in pages:
                    page.locator(".consent").wait_for()
                self.pass_consent(pages[0], agree=False)  # one refuses, the other goes on
                self.pass_consent(pages[1])
                self.pass_conditions(pages[1])
                self.wait_delivered_pilot(pages[1], receiver, 3)
                self.assertEqual({m["participant_code"] for m in receiver.accepted}, {CODE})
                self.assertEqual(len({m["session_id"] for m in receiver.accepted}), 2)
                statuses = [m["summary"].get("status") for m in receiver.accepted]
                self.assertEqual(statuses.count("no_consent"), 1)

    def test_an_unknown_but_well_formed_code_goes_on(self):
        """The app cannot read the tables, so a code nobody holds is not noticed
        (the analysis drops such rows). The retest runs and is recorded."""
        for browser in self.browsers:
            with self.subTest(browser=browser.browser_type.name):
                context, receiver = self.new_context(browser)
                page, errors = self.open(browser, "?mode=pilot&r=zzzzzzzzzz", context=context)
                self.pass_consent(page)
                self.pass_conditions(page)
                self.wait_delivered_pilot(page, receiver, 2)
                self.assertEqual({m["participant_code"] for m in receiver.accepted}, {"zzzzzzzzzz"})
                self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

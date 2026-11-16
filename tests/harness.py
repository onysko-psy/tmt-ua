"""Shared setup for browser checks: a local server for app/ (or the published
site if TMTUA_BASE_URL is set), Chromium and WebKit, and a fake receiver so
that automatic checks never write into the real spreadsheets.
"""

import functools
import http.server
import json
import os
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

APP_DIR = Path(__file__).resolve().parent.parent
CODE_GS = (APP_DIR / "receiver" / "Code.gs").read_text()
RECEIVER_GLOB = "https://script.google.com/macros/**"

# Chromium does not route beacons through Playwright, so a page closed with
# pending data would beacon it to the real receiver. In checks, sendBeacon
# only records the body in window.__beacons.
RECORD_BEACONS = """window.__beacons = [];
navigator.sendBeacon = (url, blob) => {
    blob.text().then(text => window.__beacons.push(text));
    return true;
};"""


# Where to click in a TMT field that is on the page, in page px: the cross,
# an empty corner of the field, and the centre of every circle in path order.
TMT_POINTS = """() => {
    const svg = document.querySelector('.tmt-run .tmt-field');
    const field = svg.getBoundingClientRect();
    return {
        cross: [field.left + field.width / 2, field.top + field.height / 2],
        corner: [field.left + 3, field.top + 3],
        circles: [...svg.querySelectorAll('.tmt-circle circle')].map(circle => {
            const box = circle.getBoundingClientRect();
            return [box.left + box.width / 2, box.top + box.height / 2];
        }),
    };
}"""

TMT_BLOCKS = {"TMT, частина A": "Частина 1", "TMT, частина B": "Частина 2"}
TMT_IDS = {"tmt_a": "TMT, частина A", "tmt_b": "TMT, частина B"}
# Questionnaire blocks (T2.2), by the label in the dev menu.
FORM_BLOCKS = {
    "Згода": "consent",
    "Критерії включення й виключення": "criteria",
    "Біографічна анкета": "demographics",
    "Анкета умов": "conditions",
    "PSS-10": "pss10",
    "Питання після тесту": "post",
    "Запрошення на ретест": "retest_invite",
    "Подяка": "thanks",
}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class FakeReceiver:
    """Answers like the real receiver and records what the app sent.

    reply(body) may be replaced to simulate failures: return a dict to answer
    with it, or None to drop the connection.
    """

    def __init__(self):
        self.accepted = []  # parsed messages answered with ok
        self.requests = []  # (resource type, raw body) of everything that arrived
        self.reply = lambda body: {"ok": True, "receiver_version": "fake"}
        # Playwright's offline mode does not stop intercepted requests, so
        # going offline has to drop them here as well (see go_offline).
        self.offline = False

    def handle(self, route):
        request = route.request
        body = request.post_data or ""
        self.requests.append((request.resource_type, body))
        answer = None if self.offline else self.reply(body)
        if answer is None:
            route.abort()
            return
        if answer.get("ok"):
            self.accepted.append(json.loads(body))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(answer),
                      headers={"Access-Control-Allow-Origin": "*"})

    def blocks(self):
        return [message["block"] for message in self.accepted]


class AppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = None
        cls.base = os.environ.get("TMTUA_BASE_URL")
        if not cls.base:
            handler = functools.partial(QuietHandler, directory=APP_DIR)
            cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=cls.server.serve_forever, daemon=True).start()
            cls.base = f"http://127.0.0.1:{cls.server.server_port}/"
        cls.pw = sync_playwright().start()
        cls.browsers = [cls.pw.chromium.launch(), cls.pw.webkit.launch()]

    @classmethod
    def tearDownClass(cls):
        for browser in cls.browsers:
            browser.close()
        cls.pw.stop()
        if cls.server:
            cls.server.shutdown()

    def new_context(self, browser, init_script=None, **options):
        """A fresh browser profile (own localStorage) with a fake receiver.
        options go to Playwright, e.g. a device to emulate."""
        context = browser.new_context(**options)
        self.addCleanup(context.close)
        receiver = FakeReceiver()
        context.route(RECEIVER_GLOB, receiver.handle)
        context.add_init_script(RECORD_BEACONS)
        if init_script:
            context.add_init_script(init_script)
        return context, receiver

    def set_offline(self, context, receiver, offline):
        """Drops or restores the connection; coming back fires 'online'."""
        receiver.offline = offline
        context.set_offline(offline)

    def open(self, browser, query, block_cdn=False, tamper_cdn=False, context=None):
        """Opens the app; returns the page and a list collecting JS errors."""
        if context is None:
            context, _ = self.new_context(browser)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: msg.type == "error" and errors.append(msg.text))
        if block_cdn:
            page.route("**/cdn.jsdelivr.net/**", lambda route: route.abort())
        if tamper_cdn:
            def tamper(route):
                response = route.fetch()
                route.fulfill(response=response, body=response.text() + "\n;")
            page.route("**/jspsych@*/dist/*.js", tamper)
        page.goto(self.base + query)
        # The app loads its stimuli before the first screen (main.js).
        page.wait_for_function("() => document.documentElement.dataset.tmtuaReady === '1'")
        return page, errors

    def module(self, page, path):
        """Imports one of the app's own modules inside the page."""
        return page.evaluate(f"import('./src/{path}').then(m => JSON.parse(JSON.stringify(m)))")

    def blocks(self, page):
        return page.evaluate("import('./src/blocks.js').then(m => m.BLOCKS.map(b => [b.id, b.label]))")

    def click_through(self, page, labels):
        for label in labels:
            if label in TMT_BLOCKS:
                self.pass_tmt(page, label)
                continue
            if label in FORM_BLOCKS:
                self.pass_form(page, FORM_BLOCKS[label])
                continue
            if label == "Кодування символів":
                self.pass_coding(page)
                continue
            if label == "Stroop":
                self.pass_stroop(page)
                continue
            if label == "SART":
                self.pass_sart(page)
                continue
            page.locator(".placeholder", has_text=label).wait_for()
            page.get_by_role("button", name="Далі").click()

    def field_points(self, page):
        """Waits for a TMT field and returns where to click (TMT_POINTS)."""
        page.locator(".tmt-run").wait_for()
        return page.evaluate(TMT_POINTS)

    def answer(self, page, name, value):
        """Answers one question of a form: a radio option by its code, or a
        whole number typed into the age field."""
        if name == "age":
            page.locator("#field-age").fill(str(value))
        else:
            page.locator(f'fieldset[data-name="{name}"] input[value="{value}"]').check()

    def submit_form(self, page):
        page.locator("form button[type=submit]").click()

    def pass_consent(self, page, agree=True):
        page.locator(".consent").wait_for()
        page.get_by_role("button", name="Я погоджуюся" if agree else "Я не погоджуюся").click()

    def pass_criteria(self, page, age=27, tbi="no", color_vision="no"):
        page.locator(".form").wait_for()
        self.answer(page, "age", age)
        self.answer(page, "tbi", tbi)
        self.answer(page, "color_vision", color_vision)
        self.submit_form(page)

    def pass_demographics(self, page, sex="female", education="5"):
        page.locator("fieldset[data-name=sex]").wait_for()
        self.answer(page, "sex", sex)
        self.answer(page, "education", education)
        self.submit_form(page)

    def pass_conditions(self, page, sleep="7", fatigue="2", others="no", pointer="mouse"):
        page.locator(".screen", has_text="Перед завданнями").wait_for()
        page.get_by_role("button", name="Далі").click()
        page.locator("fieldset[data-name=sleep]").wait_for()
        self.answer(page, "sleep", sleep)
        self.answer(page, "fatigue", fatigue)
        self.answer(page, "others", others)
        self.answer(page, "pointer", pointer)
        self.submit_form(page)

    def pass_pss(self, page, answers=None):
        """PSS-10: ten answers 0-4 in the order of the items."""
        page.locator("fieldset[data-name=pss_1]").wait_for()
        for number, value in enumerate(answers or [2] * 10, 1):
            self.answer(page, f"pss_{number}", value)
        self.submit_form(page)

    def pass_post(self, page, distraction="0", interruption="no", effort="4", comment=None):
        page.locator("fieldset[data-name=distraction]").wait_for()
        self.answer(page, "distraction", distraction)
        self.answer(page, "interruption", interruption)
        self.answer(page, "effort", effort)
        if comment:
            page.locator("#field-comment").fill(comment)
        self.submit_form(page)

    def pass_invite(self, page, email=None):
        """The invitation: an address and "send", or "no, thanks"."""
        page.locator("#field-email").wait_for()
        if email:
            page.locator("#field-email").fill(email)
            page.get_by_role("button", name="Надіслати й завершити").click()
        else:
            page.get_by_role("button", name="Ні, дякую").click()

    def pass_form(self, page, block_id):
        """Gets through a questionnaire block with ordinary answers."""
        if block_id == "thanks":
            return  # no screen of its own
        {"consent": self.pass_consent, "criteria": self.pass_criteria,
         "demographics": self.pass_demographics, "conditions": self.pass_conditions,
         "pss10": self.pass_pss, "post": self.pass_post, "retest_invite": self.pass_invite}[block_id](page)

    def tmt_lead(self, page, label):
        """The instruction screen of a TMT part."""
        return page.locator(".screen", has_text=f"Завдання з кружечками. {TMT_BLOCKS[label]}")

    def start_practice(self, page, label=None):
        """From the instruction to the field of the first practice attempt;
        returns where to click (TMT_POINTS)."""
        if label:
            self.tmt_lead(page, label).wait_for()
        page.get_by_role("button", name="Почати пробну спробу").click()
        return self.field_points(page)

    def next_attempt(self, page):
        """After a practice attempt: the screen with 'try again', then the
        field of the next attempt."""
        page.get_by_role("button", name="Спробувати ще раз").click()
        return self.field_points(page)

    def pass_practice(self, page, label=None):
        """The instruction and a practice attempt without errors, up to the
        screen before the test."""
        self.click_tmt(page, self.start_practice(page, label))
        page.get_by_role("button", name="Почати", exact=True).wait_for()

    def start_tmt(self, page, label=None):
        """From the instruction through a clean practice to the field of the
        test with the cross; returns where to click (TMT_POINTS)."""
        self.pass_practice(page, label)
        page.get_by_role("button", name="Почати", exact=True).click()
        return self.field_points(page)

    def click_tmt(self, page, points, order=None):
        """The bot: clicks the cross, then the circles with these indexes (all
        in path order by default); None in the order is a click beside the
        circles."""
        page.mouse.click(*points["cross"])
        for index in range(len(points["circles"])) if order is None else order:
            page.mouse.click(*(points["corner"] if index is None else points["circles"][index]))

    def pass_tmt(self, page, label=None):
        """Gets through a TMT block without errors."""
        self.click_tmt(page, self.start_tmt(page, label))
        page.locator(".tmt-run").wait_for(state="detached")

    # ---- symbol coding (T3.1) ----

    def coding_symbol(self, page):
        """The digit (1-9) of the figure now in the frame."""
        return int(page.locator(".coding-frame").get_attribute("data-symbol"))

    def start_coding_training(self, page):
        """From the instruction to the first figure of the training."""
        page.get_by_role("button", name="Почати тренування").click()
        page.locator(".coding-frame").wait_for()

    def coding_press(self, page, digit, numpad=False):
        """A real key press (a trusted event); digits by their place on the
        keyboard, top row or numeric pad."""
        page.keyboard.press(f"{'Numpad' if numpad else 'Digit'}{digit}")

    def coding_answer(self, page, wrong=False):
        """Answers the figure on the screen with a real key press, rightly or
        wrongly; waits until the next figure is in the frame (or the run is
        over). Returns the digit of the figure that was answered."""
        page.locator(".coding-frame[data-shown='1']").wait_for()  # the figure has to be drawn first
        digit = self.coding_symbol(page)
        press = digit % 9 + 1 if wrong else digit
        self.coding_press(page, press)
        page.wait_for_function(
            "d => { const f = document.querySelector('.coding-frame'); return !f || f.dataset.symbol !== String(d) "
            "|| document.querySelector('.coding-wrong').style.visibility === 'visible'; }", arg=digit)
        return digit

    def pass_coding_training(self, page, wrong=0):
        """The 10 figures of one training attempt; the first `wrong` of them
        are answered wrongly once before the right digit."""
        for number in range(10):
            if number < wrong:
                self.coding_answer(page, wrong=True)
            self.coding_answer(page)
        page.locator(".coding-run").wait_for(state="detached")

    def start_coding(self, page, wrong=0):
        """From the instruction through the training (with `wrong` errors in
        its first attempt; a repeat is passed cleanly) to the first figure of
        the main part."""
        self.start_coding_training(page)
        self.pass_coding_training(page, wrong)
        if wrong >= 3:
            page.get_by_role("button", name="Почати тренування").click()
            page.locator(".coding-frame").wait_for()
            self.pass_coding_training(page)
        page.get_by_role("button", name="Почати", exact=True).click()
        page.locator(".coding-frame").wait_for()

    CODING_BOT = """async ({ limit, wrong }) => {
        // Answers with synthetic key events, one per frame: rightly, except
        // the answers at the given positions (from 0), which are wrong. Stops
        // after `limit` answers or when the run is over.
        const frame = () => document.querySelector('.coding-frame');
        for (let n = 0; n < limit && frame(); n++) {
            let digit = Number(frame().dataset.symbol);
            if (wrong.includes(n)) digit = digit % 9 + 1;
            // one frame, so that the figure is drawn; the timer is for a page that gets no frames
            await new Promise(resolve => { requestAnimationFrame(resolve); setTimeout(resolve, 200); });
            window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Digit' + digit, bubbles: true }));
        }
    }"""

    def bot_coding(self, page, limit=1000, wrong=()):
        """Runs the bot in the main part: `limit` answers, those at the
        positions in `wrong` wrong (the whole sequence is 180)."""
        page.evaluate(self.CODING_BOT, {"limit": limit, "wrong": list(wrong)})

    def pass_coding(self, page, answers=1000):
        """Gets through the coding block: a clean training and the main part
        answered rightly and fast (the whole sequence of 180 figures by
        default, so the main part ends at once)."""
        self.start_coding(page)
        self.bot_coding(page, answers)
        page.locator(".coding-run").wait_for(state="detached")

    # ---- Stroop (T3.2) ----

    def start_stroop_training(self, page):
        """From the instruction to the first dot of the training."""
        page.get_by_role("button", name="Почати тренування").click()
        page.locator(".stroop-run[data-dot-shown='1']").wait_for()

    def stroop_fast(self, page, iti=0, feedback=0):
        """Shortens the pauses of the Stroop task through the live parameters
        (window.tmtuaParams), so that whole sessions pass quickly."""
        page.evaluate("([iti, feedback]) => Object.assign(window.tmtuaParams.stroop, { itiMs: iti, feedbackMs: feedback })",
                      [iti, feedback])

    def stroop_click(self, page, selector):
        """A real mouse click in the middle of an element of the Stroop screen."""
        box = page.locator(selector).first.bounding_box()
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    def stroop_dot(self, page):
        """Waits until the dot is drawn and clicks it; waits until the word is drawn;
        returns (word, ink) of the trial."""
        page.locator(".stroop-run[data-phase='dot'][data-dot-shown='1']").wait_for()
        self.stroop_click(page, ".stroop-dot-visible")
        word = page.locator(".stroop-word[data-shown='1']")
        word.wait_for()
        return word.get_attribute("data-word"), word.get_attribute("data-ink")

    def stroop_plate(self, page, color):
        self.stroop_click(page, f".stroop-plate[data-color='{color}']")

    STROOP_BOT = """async ({ plan }) => {
        // Runs trials with synthetic pointer presses until the run is over (or `limit`
        // trials are done). plan: { delay: {congruent, incongruent} ms from the word drawn to
        // the answer, wrong: [trial indices answered with a wrong plate], timeout: [indices
        // not answered], misses: {index: presses beside the plates}, repeats: [indices that
        // press the dot again], limit }.
        const until = (fn, ms = 20000) => new Promise((resolve, reject) => {
            const start = performance.now();
            const tick = () => {
                const value = fn();
                if (value) resolve(value);
                else if (performance.now() - start > ms) reject(new Error('the bot waited too long'));
                else setTimeout(tick, 3);
            };
            tick();
        });
        const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
        const stage = () => document.querySelector('.stroop-run');
        const press = (el) => el.dispatchEvent(new PointerEvent('pointerdown',
            { bubbles: true, button: 0, isPrimary: true, pointerType: 'mouse' }));
        const order = ['red', 'green', 'blue', 'yellow'];
        const limit = plan.limit ?? 1000;
        for (let done = 0; done < limit; done++) {
            await until(() => !stage() || (stage().dataset.phase === 'dot' && stage().dataset.dotShown === '1'));
            if (!stage()) break;
            const n = Number(stage().dataset.trial);
            press(stage().querySelector('.stroop-dot-hit'));
            const word = await until(() => stage().querySelector('.stroop-word[data-shown="1"]'));
            const ink = word.dataset.ink;
            const same = word.dataset.word === ink;
            for (let k = 0; k < ((plan.misses ?? {})[n] ?? 0); k++) press(stage());
            if ((plan.repeats ?? []).includes(n)) press(stage().querySelector('.stroop-dot-hit'));
            await sleep(((plan.delay ?? {})[same ? 'congruent' : 'incongruent']) ?? 5);
            if ((plan.timeout ?? []).includes(n)) {
                await until(() => !stage() || stage().dataset.phase !== 'word');
            } else {
                const target = (plan.wrong ?? []).includes(n) ? order[(order.indexOf(ink) + 1) % 4] : ink;
                press(stage().querySelector(`.stroop-plate[data-color="${target}"]`));
            }
        }
    }"""

    def bot_stroop(self, page, **plan):
        """Runs the bot in the run on the screen (see STROOP_BOT for the plan)."""
        page.evaluate(self.STROOP_BOT, {"plan": plan})

    def start_stroop(self, page, wrong_trials=(), repeat=False):
        """From the instruction through the training (the trials in `wrong_trials` of its
        first attempt are answered wrongly; with `repeat` a second attempt is passed
        cleanly) to the first dot of the main part."""
        self.start_stroop_training(page)
        self.bot_stroop(page, wrong=list(wrong_trials))
        if repeat:
            page.get_by_role("button", name="Почати тренування").click()
            page.locator(".stroop-run[data-dot-shown='1']").wait_for()
            self.bot_stroop(page)
        page.get_by_role("button", name="Почати", exact=True).click()
        page.locator(".stroop-run[data-dot-shown='1']").wait_for()

    def pass_stroop(self, page):
        """Gets through the Stroop block: a clean training and the main part answered
        rightly (the pauses are shortened)."""
        self.stroop_fast(page)
        self.start_stroop(page)
        self.bot_stroop(page)
        page.locator(".stroop-run").wait_for(state="detached")

    # ---- SART ----

    def sart_fast(self, page, trials=12, practice=6, mask=100, countdown=200, feedback=40, measure=12):
        """Shortens the SART through the live parameters (window.tmtuaParams) so that whole
        sessions pass quickly: fewer trials, a short mask, a short countdown and feedback.
        The time of the digit (250 ms) is never changed."""
        page.evaluate(
            "p => Object.assign(window.tmtuaParams.sart, { mainTrials: p.trials, practiceTrials: p.practice, "
            "maskMs: p.mask, countdownMs: p.countdown, feedbackMs: p.feedback, measureFrames: p.measure })",
            {"trials": trials, "practice": practice, "mask": mask, "countdown": countdown,
             "feedback": feedback, "measure": measure})

    def sart_press(self, page, code="Space", **options):
        """A synthetic key press on the page (keydown and keyup)."""
        page.evaluate(
            "([code, options]) => { for (const type of ['keydown', 'keyup']) window.dispatchEvent("
            "new KeyboardEvent(type, { code, key: code === 'Space' ? ' ' : code, bubbles: true, cancelable: true, ...options })); }",
            [code, options])

    def start_sart_training(self, page):
        """From the instruction to the run of the training (its first trial may already be over)."""
        page.get_by_role("button", name="Почати тренування").click()
        # Only the stage is waited for: a digit is on the screen 250 ms, and a wait may miss it;
        # the bot picks the trials up from wherever the run is.
        page.locator(".sart-run").wait_for(timeout=30000)

    SART_BOT = """async ({ plan }) => {
        // Goes through the trials of the run on the screen with synthetic space presses until the
        // run is over. plan: { delay: ms after the digit was drawn to the press, press3: [trial
        // indices of 3s that are pressed], omit: [trial indices not pressed], fast: {index: ms
        // delay (shorter than 100 ms)}, double: [indices pressed twice], hold: [indices where a
        // repeated key event comes], keys: {index: [codes of other keys]}, limit }.
        const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
        const stage = () => document.querySelector('.sart-run');
        const key = (code, options = {}) => window.dispatchEvent(new KeyboardEvent('keydown',
            { code, key: code === 'Space' ? ' ' : code, bubbles: true, cancelable: true, ...options }));
        const limit = plan.limit ?? 100000;
        let last = null;
        for (let done = 0; done < limit; done++) {
            let node;
            const since = performance.now();
            for (;;) {
                node = stage();
                if (!node) return;
                if (node.dataset.shown === '1' && node.dataset.trial !== last) break;
                await sleep(2);
                if (performance.now() - since > 20000) throw new Error('the bot waited too long');
            }
            last = node.dataset.trial;
            const n = Number(last);
            const digit = Number(node.dataset.digit);
            const press = digit === 3 ? (plan.press3 ?? []).includes(n) : !(plan.omit ?? []).includes(n);
            for (const code of ((plan.keys ?? {})[n] ?? [])) key(code);
            if ((plan.fast ?? {})[n] !== undefined) { await sleep(plan.fast[n]); key('Space'); }
            else if (press) {
                await sleep(plan.delay ?? 200);
                key('Space');
                if ((plan.double ?? []).includes(n)) { await sleep(8); key('Space'); }
                if ((plan.hold ?? []).includes(n)) key('Space', { repeat: true });
            }
        }
    }"""

    def bot_sart(self, page, **plan):
        """Runs the bot in the run on the screen (see SART_BOT for the plan)."""
        page.evaluate(self.SART_BOT, {"plan": plan})

    def start_sart(self, page, omit_trials=(), press3=(), repeat=False):
        """From the instruction through the training (the digits at the trial indices in
        `omit_trials` of its first attempt are not pressed; with `repeat` a second attempt is
        passed cleanly) to the first digit of the main part."""
        self.start_sart_training(page)
        self.bot_sart(page, omit=list(omit_trials), press3=list(press3))
        if repeat:
            page.get_by_role("button", name="Почати тренування").click()
            page.locator(".sart-run").wait_for()
            self.bot_sart(page)
        page.get_by_role("button", name="Почати", exact=True).click()
        page.locator(".sart-run").wait_for()

    def pass_sart(self, page, short=True):
        """Gets through the SART block: a clean training and the main part answered rightly
        (short runs, see sart_fast)."""
        if short:
            self.sart_fast(page)
        self.start_sart(page)
        self.bot_sart(page)
        page.locator(".sart-run").wait_for(state="detached")

    def session_blocks(self, page, retest=False):
        """(id, label, is a placeholder) of every block, in session order
        (of a retest if asked)."""
        return page.evaluate(
            "type => import('./src/blocks.js').then(m => m.blocksFor({ type })"
            ".map(b => [b.id, b.label, m.isPlaceholder(b)]))", "retest" if retest else "first")

    def calibrate(self, page, card_px=380):
        """Drags the corner of the card picture until it is card_px wide (the
        plugin grows the card by twice the drag) and confirms. 380 px is a
        card at 4.44 px/mm, as on a 15" MacBook Air."""
        handle = page.locator("#jspsych-resize-handle")
        box = handle.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + (card_px - 250) / 2, y, steps=5)
        page.mouse.up()
        page.get_by_role("button", name="Готово: розмір збігається").click()

    def pass_block(self, page, block_id, label, placeholder):
        """Gets through one block as a participant on a desktop would."""
        if placeholder:
            page.locator(".placeholder", has_text=label).wait_for()
            page.get_by_role("button", name="Далі").click()
        elif block_id == "calibration":
            self.calibrate(page)
            if "mode=dev" in page.url:  # the 100 mm square, dev only
                page.locator(".dev-square").wait_for()
                page.get_by_role("button", name="Далі").click()
        elif block_id == "fullscreen":
            page.get_by_role("button", name="Увімкнути повноекранний режим").click()
        elif block_id in TMT_IDS:
            self.pass_tmt(page, label)
        elif block_id == "coding":
            self.pass_coding(page)
        elif block_id == "stroop":
            self.pass_stroop(page)
        elif block_id == "sart":
            self.pass_sart(page)
        elif block_id in FORM_BLOCKS.values():
            self.pass_form(page, block_id)
        elif block_id != "device_check":  # an accepted device sees no screen
            raise AssertionError(f"no way through block {block_id}")

    def wait_delivered(self, page):
        page.wait_for_function("() => window.tmtua.sender.pending() === 0", timeout=15000)

    def assert_valid_for_receiver(self, context, messages):
        """Every message must pass the real receiver's validation."""
        page = context.new_page()
        page.add_script_tag(content=CODE_GS)
        for message in messages:
            self.assertIsNone(page.evaluate("p => validatePayload(p)", message), message)
        page.close()

"""Runs dev sessions against the REAL receiver (tasks T0.3, T0.5, T0.6, T1.2, T1.4, T2.2, T2.3, T2.4, T3.1, T3.2, T3.3).

Not part of the automatic test run: it writes rows into the PILOT storage
(mode=dev). Prints the session ids; then compare the pilot spreadsheet with
the expectations printed at the end. Run from the app/ folder:

    ../.venv/bin/python tests/sender_live.py
"""

import functools
import http.server
import sys
import threading

from playwright.sync_api import sync_playwright

from harness import APP_DIR, RECEIVER_GLOB, TMT_POINTS, AppTestCase, QuietHandler


# Shortens the pauses and the answer limit of the Stroop task, so that a live session is quick.
STROOP_FAST = "&set.stroop.itiMs=50&set.stroop.feedbackMs=100&set.stroop.responseLimitMs=800"
# The SART runs in real time (a digit is 250 ms, a trial 1.15 s); only the main part is cut to its first 60 trials.
SART_FAST = "&set.sart.mainTrials=60"


def click_through(page, count):
    for _ in range(count):
        page.locator(".placeholder").wait_for()
        text = page.locator(".placeholder").text_content()
        page.get_by_role("button", name="Далі").click()
        page.wait_for_function("t => document.querySelector('.placeholder')?.textContent !== t", arg=text)


# The Stroop block (T3.2): the instruction, the training (a repeat if fewer than 9
# of 12 are correct), the main part of 96 trials answered by the bot from the test
# harness (synthetic presses; the pauses are shortened in the link).
def pass_stroop(page, training_wrong=(), repeat=False, wrong=(), timeout=(), delay=None):
    def bot(plan):
        page.evaluate(AppTestCase.STROOP_BOT, {"plan": plan})

    page.get_by_role("button", name="Почати тренування").click()
    page.locator(".stroop-run[data-started='1']").wait_for()
    bot({"wrong": list(training_wrong)})
    if repeat:
        page.get_by_role("button", name="Почати тренування").click()
        page.locator(".stroop-run[data-started='1']").wait_for()
        bot({})
    page.get_by_role("button", name="Почати", exact=True).click()
    page.locator(".stroop-run[data-started='1']").wait_for()
    bot({"wrong": list(wrong), "timeout": list(timeout), "delay": delay or {"congruent": 20, "incongruent": 70}})
    page.locator(".stroop-run").wait_for(state="detached")


# The SART block (T3.3): the instruction, the training (a repeat at 9 misses of 16), the main part
# of the first 60 trials, answered by the bot (synthetic space presses 200 ms after the digit).
def sart_plan():
    import json
    sequence = json.loads((APP_DIR / "stimuli" / "sart-sequence.json").read_text())
    practice = sequence["practice"][0]
    main = sequence["main"][:60]
    threes = [i for i, t in enumerate(main) if t[0] == 3]
    others = [i for i, t in enumerate(main) if t[0] != 3]
    return {
        "training_omit": [i for i, t in enumerate(practice) if t[0] != 3][:9],  # 9 misses: the repeat
        "press3": threes[:3],  # 3 false responses
        "omit": [others[5], others[12], others[30]],  # 3 misses
        "threes": len(threes), "others": len(others),
    }


def pass_sart(page, training_omit=(), repeat=False, press3=(), omit=()):
    def bot(plan):
        page.evaluate(AppTestCase.SART_BOT, {"plan": plan})

    page.get_by_role("button", name="Почати тренування").click()
    page.locator(".sart-run").wait_for()
    bot({"omit": list(training_omit)})
    if repeat:
        page.get_by_role("button", name="Почати тренування").click()
        page.locator(".sart-run").wait_for()
        bot({})
    page.get_by_role("button", name="Почати", exact=True).click()
    page.locator(".sart-run").wait_for()
    bot({"press3": list(press3), "omit": list(omit)})
    page.locator(".sart-run").wait_for(state="detached")


def pass_questionnaires(page, age=27):
    """Consent, criteria, biography, the screen before the tasks and the
    conditions questionnaire, with ordinary answers."""
    page.get_by_role("button", name="Я погоджуюся").click()
    page.locator("#field-age").fill(str(age))
    for name, value in [("tbi", "no"), ("color_vision", "no")]:
        page.locator(f'fieldset[data-name="{name}"] input[value="{value}"]').check()
    page.locator("form button[type=submit]").click()
    page.locator('fieldset[data-name="sex"]').wait_for()
    page.locator('fieldset[data-name="sex"] input[value="female"]').check()
    page.locator('fieldset[data-name="education"] input[value="5"]').check()
    page.locator("form button[type=submit]").click()
    pass_conditions(page)


# The training of the coding task: the first `wrong` figures are first answered
# with a wrong digit, then rightly (synthetic key events, one per frame).
TRAINING_BOT = """async (wrong) => {
    const frame = () => document.querySelector('.coding-frame');
    const press = (digit) => window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Digit' + digit, bubbles: true }));
    const frames = (n) => new Promise(resolve => { let i = 0; const tick = () => (++i >= n ? resolve() : requestAnimationFrame(tick)); tick(); });
    for (let n = 0; frame(); n++) {
        await frames(3);
        const digit = Number(frame().dataset.symbol);
        if (n < wrong) { press(digit % 9 + 1); await frames(3); }
        press(digit);
        await frames(2);
    }
}"""


def pass_coding(page, training_wrong=0, answers=30, wrong=(), extra_keys=False):
    """The coding block: the instruction, the training (a repeat if 3 or more
    wrong digits), the main part with `answers` answers (those at the
    positions in `wrong` are wrong) and the extra keys, until its time (set in
    the link) is over."""
    page.get_by_role("button", name="Почати тренування").click()
    page.locator(".coding-frame").wait_for()
    page.evaluate(TRAINING_BOT, training_wrong)
    if training_wrong >= 3:
        page.get_by_role("button", name="Почати тренування").click()
        page.locator(".coding-frame").wait_for()
        page.evaluate(TRAINING_BOT, 0)
    page.get_by_role("button", name="Почати", exact=True).click()
    page.locator(".coding-frame[data-shown='1']").wait_for()
    if extra_keys:
        page.evaluate("""() => { for (const code of ['KeyA', 'Space', 'Digit0'])
            window.dispatchEvent(new KeyboardEvent('keydown', { code, bubbles: true })); }""")
    page.evaluate(AppTestCase.CODING_BOT, {"limit": answers, "wrong": list(wrong)})
    page.locator(".coding-run").wait_for(state="detached", timeout=20_000)


def pass_conditions(page):
    """The screen before the tasks and the conditions questionnaire."""
    page.get_by_role("button", name="Далі").click()  # the screen before the tasks
    page.locator('fieldset[data-name="sleep"]').wait_for()
    for name, value in [("sleep", "7"), ("fatigue", "2"), ("others", "no"), ("pointer", "mouse")]:
        page.locator(f'fieldset[data-name="{name}"] input[value="{value}"]').check()
    page.locator("form button[type=submit]").click()


ADDRESS = "pilot-check@example.com"  # a made-up address: only for the pilot contacts sheet
UNKNOWN_CODE = "u2n7k8m3qz"  # a well-formed code that no first session has


def pass_closing(page, email=ADDRESS):
    """PSS-10 (all answers 2), the questions after the tasks, the invitation
    (not on a retest: email=None)."""
    page.locator('fieldset[data-name="pss_1"]').wait_for()
    for number in range(1, 11):
        page.locator(f'fieldset[data-name="pss_{number}"] input[value="2"]').check()
    page.locator("form button[type=submit]").click()
    page.locator('fieldset[data-name="distraction"]').wait_for()
    for name, value in [("distraction", "1"), ("interruption", "no"), ("effort", "4")]:
        page.locator(f'fieldset[data-name="{name}"] input[value="{value}"]').check()
    page.locator("#field-comment").fill("Live check: no comment.")
    page.locator("form button[type=submit]").click()
    if email is None:
        return
    page.locator("#field-email").wait_for()
    page.locator("#field-email").fill(email)
    page.get_by_role("button", name="Надіслати й завершити").click()


CONSOLE = []  # the page's errors and warnings, for the diagnosis of a stuck queue


def open_app(page, url):
    page.on("console", lambda m: CONSOLE.append(m.text[:300]) if m.type in ("error", "warning") else None)
    page.goto(url)
    page.wait_for_function("() => document.documentElement.dataset.tmtuaReady === '1'")


def pass_tmt(page, order=None):
    """Clicks through a TMT test: the cross, then the circles with these
    indexes (all in path order by default); None is a click beside them."""
    page.get_by_role("button", name="Почати пробну спробу").wait_for()
    page.get_by_role("button", name="Почати пробну спробу").click()
    page.locator(".tmt-run").wait_for()
    points = page.evaluate(TMT_POINTS)
    page.mouse.click(*points["cross"])  # the practice, without errors
    for point in points["circles"]:
        page.mouse.click(*point)
        page.wait_for_timeout(40)
    page.get_by_role("button", name="Почати", exact=True).click()
    page.wait_for_function("() => document.querySelectorAll('.tmt-run .tmt-circle').length > 8")
    points = page.evaluate(TMT_POINTS)
    page.mouse.click(*points["cross"])
    for index in range(len(points["circles"])) if order is None else order:
        page.mouse.click(*(points["corner"] if index is None else points["circles"][index]))
        page.wait_for_timeout(40)
    page.locator(".tmt-run").wait_for(state="detached")


def calibrate(page, card_px=380):
    handle = page.locator("#jspsych-resize-handle")
    box = handle.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + (card_px - 250) / 2, y, steps=5)
    page.mouse.up()
    page.get_by_role("button", name="Готово: розмір збігається").click()


def wait_delivered(page):
    try:
        page.wait_for_function("() => window.tmtua.sender.pending() === 0", timeout=300_000)
    except Exception:
        state = page.evaluate("({ pending: window.tmtua.sender.pending(), rejected: window.tmtua.sender.rejected() })")
        print("NOT DELIVERED:", state, "| console:", CONSOLE[-8:], flush=True)
        raise


def main():
    handler = functools.partial(QuietHandler, directory=APP_DIR)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    report = []

    with sync_playwright() as pw:
        wanted = sys.argv[1:] or ["chromium", "webkit"]  # e.g. `sender_live.py chromium`
        for browser_type in [getattr(pw, name) for name in wanted]:
            browser = browser_type.launch()
            name = browser_type.name

            # 1. Whole session, connection drops after 7 messages and comes
            # back. device_check shows no screen on a desktop and sends nothing.
            context = browser.new_context()
            page = context.new_page()
            open_app(page, base + "?mode=dev&start=device_check&set.coding.durationMs=4000" + STROOP_FAST + SART_FAST)
            session_id = page.evaluate("window.tmtua.ids.session_id")
            pass_questionnaires(page)  # consent .. conditions
            calibrate(page)
            page.locator(".dev-square").wait_for()  # the 100 mm square, dev only
            page.get_by_role("button", name="Далі").click()
            page.get_by_role("button", name="Увімкнути повноекранний режим").click()
            pass_tmt(page)  # tmt_a, without errors
            wait_delivered(page)
            context.set_offline(True)
            # tmt_b: 2 instead of А, a click beside, Б again after Б, 1 instead of 3.
            pass_tmt(page, [0, 2, None, 1, 2, 3, 3, 0] + list(range(4, 25)))
            # coding: 3 wrong digits in the training (so a repeat), then 30 answers
            # of the main part, 3 of them wrong (positions 3, 10, 20), and 3 extra keys.
            pass_coding(page, training_wrong=3, answers=30, wrong=[3, 10, 20], extra_keys=True)
            # stroop: 4 wrong in the training (8 of 12 correct: a repeat), then the main part:
            # wrong at trials 3, 10, 20, 50, no answer at 7 and 60 (limit 0.8 s here).
            pass_stroop(page, training_wrong=[1, 2, 3, 4], repeat=True, wrong=[3, 10, 20, 50], timeout=[7, 60])
            plan = sart_plan()
            pass_sart(page, training_omit=plan["training_omit"], repeat=True, press3=plan["press3"], omit=plan["omit"])
            pass_closing(page)  # pss10 .. retest_invite; thanks has no screen
            page.locator(".dev-end").wait_for()
            queued = page.evaluate("window.tmtua.sender.pending()")
            context.set_offline(False)
            wait_delivered(page)
            first_code = page.evaluate("window.tmtua.ids.participant_code")
            report.append(f"{name}: full session {session_id} code {first_code} (8 blocks queued offline: {queued == 8}); SART expected: "
                          f"commission {len(plan['press3'])}, omission {len(plan['omit'])}, hit {plan['others'] - len(plan['omit'])}, "
                          f"withhold {plan['threes'] - len(plan['press3'])}")
            context.close()

            # 1b. The retest of that participant (T2.4): the personal link
            # ?r=CODE, no biography, no invitation; the end marks the contacts.
            context = browser.new_context()
            page = context.new_page()
            open_app(page, base + f"?mode=dev&r={first_code}&start=device_check&set.coding.durationMs=4000" + STROOP_FAST + SART_FAST)
            session_id = page.evaluate("window.tmtua.ids.session_id")
            page.get_by_role("button", name="Я погоджуюся").click()
            pass_conditions(page)
            calibrate(page)
            page.locator(".dev-square").wait_for()
            page.get_by_role("button", name="Далі").click()
            page.get_by_role("button", name="Увімкнути повноекранний режим").click()
            pass_tmt(page)
            pass_tmt(page)
            pass_coding(page, training_wrong=0, answers=30)  # the same 30 figures, no errors
            pass_stroop(page)  # a clean training and 96 right answers: the same sequence
            pass_sart(page)  # a clean training and the first 60 trials: the same sequence
            pass_closing(page, email=None)
            page.locator(".dev-end").wait_for()
            wait_delivered(page)
            report.append(f"{name}: RETEST {session_id} of code {first_code}")
            context.close()

            # 1c. A retest under a code nobody left an address for: the
            # receiver must ignore the contacts mark (no new contacts row).
            context = browser.new_context()
            page = context.new_page()
            open_app(page, base + f"?mode=dev&r={UNKNOWN_CODE}&only=thanks")
            session_id = page.evaluate("window.tmtua.ids.session_id")
            page.locator(".dev-end").wait_for()
            wait_delivered(page)
            report.append(f"{name}: RETEST of an UNKNOWN code {session_id} ({UNKNOWN_CODE})")
            context.close()

            # 1d. A retest of a finished code, opened again: its own session.
            context = browser.new_context()
            page = context.new_page()
            open_app(page, base + f"?mode=dev&r={first_code}&only=consent")
            session_id = page.evaluate("window.tmtua.ids.session_id")
            page.get_by_role("button", name="Я погоджуюся").click()
            page.locator(".dev-end").wait_for()
            wait_delivered(page)
            report.append(f"{name}: RETEST OPENED AGAIN {session_id} of code {first_code}")
            context.close()

            # 2. fetch blocked, page left: only the beacon can deliver.
            context = browser.new_context()
            context.route(RECEIVER_GLOB, lambda route: route.abort()
                          if route.request.resource_type == "fetch" else route.continue_())
            page = context.new_page()
            open_app(page, base + "?mode=dev&only=tmt_a")
            session_id = page.evaluate("window.tmtua.ids.session_id")
            pass_tmt(page)
            page.locator(".dev-end").wait_for()
            page.goto("about:blank")
            page.wait_for_timeout(8000)  # the receiver needs a few seconds
            report.append(f"{name}: beacon only {session_id}")
            context.close()

            # 3. Part B runs out of time (limit 3.5 s): the derived columns
            # tmt_b_minus_a_ms and tmt_b_over_a must stay empty (T1.4).
            context = browser.new_context()
            page = context.new_page()
            open_app(page, base + "?mode=dev&start=tmt_a&set.tmt.timeLimitMs=3500")
            session_id = page.evaluate("window.tmtua.ids.session_id")
            page.get_by_role("button", name="Почати пробну спробу").wait_for()
            pass_tmt(page)  # tmt_a within the limit
            pass_tmt(page, [0, 1, 2])  # tmt_b: three circles, then the limit
            page.get_by_text("Час на цю частину вийшов").wait_for()
            page.get_by_role("button", name="Далі").click()
            page.get_by_text("Завдання із символами").first.wait_for()  # the coding instruction follows
            wait_delivered(page)
            report.append(f"{name}: B timeout {session_id}")
            context.close()

            # 4. No consent: a row with the status alone (T2.2).
            context = browser.new_context()
            page = context.new_page()
            open_app(page, base + "?mode=dev&start=consent")
            session_id = page.evaluate("window.tmtua.ids.session_id")
            page.get_by_role("button", name="Я не погоджуюся").click()
            page.locator(".dev-end").wait_for()
            wait_delivered(page)
            report.append(f"{name}: no consent {session_id}")
            context.close()

            # 5. Exclusion by age 50: the reason alone (T2.2, decision 86).
            context = browser.new_context()
            page = context.new_page()
            open_app(page, base + "?mode=dev&start=consent")
            session_id = page.evaluate("window.tmtua.ids.session_id")
            page.get_by_role("button", name="Я погоджуюся").click()
            page.locator("#field-age").fill("50")
            for field, value in [("tbi", "yes"), ("color_vision", "yes")]:
                page.locator(f'fieldset[data-name="{field}"] input[value="{value}"]').check()
            page.locator("form button[type=submit]").click()
            page.locator(".dev-end").wait_for()
            wait_delivered(page)
            report.append(f"{name}: excluded by age {session_id}")
            context.close()
            browser.close()

    server.shutdown()
    print("\n".join(report))
    print("""
Expected in the pilot sessions sheet:
- each "full session" id: one row, no *_placeholder column (every block is real since T3.3),
  px_per_mm 4.4393, calibration_card_px 380, calibration_attempts 1,
  calibration_suspect 0, screen_w_mm 288.3, screen_h_mm 162.2,
  fullscreen_status "entered", fullscreen_view_w_mm / _h_mm filled,
  fullscreen_window_checks 0, no status column value, device_* columns filled (device_any_pointer_fine
  among them), session_type "first", last_block "thanks"; for each of tmt_a,
  tmt_b, coding, stroop, sart ten columns <task>_hidden_n, _hidden_ms,
  _blur_n, _blur_ms, _fs_exit_n, _fs_exit_ms, _resize_n, _zoom_n,
  _zoom_blocked_n, _touch_n, all 0 (a headless browser has nothing to leave);
  TMT: layout_version 1; tmt_a_status "complete", tmt_a_time_ms about 1100-2500,
  tmt_a_targets_done 25, tmt_a_errors_n 0, tmt_a_err_wrong_target_n 0,
  tmt_a_repeat_n 0, tmt_a_miss_n 0, six tmt_a_test_* columns equal to 0, no
  tmt_a_err_alternation_n column value; tmt_b_status "complete",
  tmt_b_targets_done 25, tmt_b_errors_n 2, tmt_b_err_alternation_n 1,
  tmt_b_err_wrong_target_n 1, tmt_b_repeat_n 1, tmt_b_miss_n 1, six tmt_b_test_*
  columns equal to 0; in the session's log folder calibration.json with the
  attempts, tmt_a.json and tmt_b.json with "clicks", "trajectory" and "env",
  and a JSON file per other task with "env" inside
- each "full session" id also (T1.4): tmt_b_minus_a_ms = tmt_b_time_ms minus
  tmt_a_time_ms, tmt_b_over_a = tmt_b_time_ms / tmt_a_time_ms to 3 decimals
  (B has errors and is slower than A, so both are positive, the ratio > 1)
- each "full session" id (T3.1): coding_practice_attempts_n 2, coding_practice_errors_1 3,
  coding_practice_errors_2 0, coding_symbols_version "1", coding_sequence_version "1",
  coding_answers_n 30, coding_errors_n 3, coding_correct_n 27, coding_extra_keys_n 3,
  coding_time_ms 4000, coding_sequence_exhausted 0; ten coding_* environment columns;
  coding.json in the session's Drive folder with practice.attempts (2), main.answers (30,
  their "symbol" equal to the first 30 numbers of stimuli/coding-sequence.json), main.extra_keys
  (3 "not_digit"), during_test, env.
- each "full session" id (T3.2): stroop_practice_attempts_n 2, stroop_practice_correct_1 8,
  stroop_practice_correct_2 12, stroop_colors_version "1", stroop_sequence_version "1",
  stroop_correct_n 90, stroop_errors_n 4, stroop_timeouts_n 2 (trials 3, 10, 20, 50 wrong; 7, 60 not answered),
  per condition (computed from stimuli/stroop-sequence.json): stroop_congruent_* and stroop_incongruent_*
  correct_n, errors_n, timeouts_n, rt_ms (congruent about 20-60, incongruent about 70-110 ms),
  stroop_effect_ms = incongruent rt minus congruent rt (about 50), stroop_miss_n 0,
  stroop_time_ms filled; ten stroop_* environment columns; stroop.json in the session's Drive folder with
  colors, sequence, sizes_mm, limits, practice.attempts (2, 12 trials each) and main.trials (96,
  "word"/"ink" equal to stimuli/stroop-sequence.json "main"), during_test, env.
- each "full session" id (T3.3, SART; the main part is cut to its first 60 trials): sart_practice_attempts_n 2,
  sart_practice_omissions_1 9, sart_practice_omissions_2 0, sart_practice_commissions_1 0 and _2 0,
  sart_look_version "1", sart_sequence_version "1"; the counts printed in the report line (commission 3, omission 3,
  hit, withhold; computed from stimuli/sart-sequence.json) and the rates sart_commission_rate = commission /
  threes, sart_omission_rate = omission / other digits; sart_rt_mean_ms about 200-215 (the press was 200 ms after the
  digit), sart_rt_sd_ms small (under 10), sart_rt_cv about 0.01-0.04, sart_fast_n 0, sart_extra_n 0, sart_time_ms about
  87000 (60 x 1450), sart_refresh_hz about 60 (59-60 in Chromium, 58-60 in WebKit), sart_digit_frames 15,
  sart_digit_mean_ms about 250 (+-2), sart_digit_dev_mean_ms under 2, sart_digit_dev_max_ms under 17,
  sart_mask_mean_ms about 1200; ten sart_* environment columns; sart.json in the session's Drive folder with look,
  sequence, sizes_mm, limits, practice.attempts (2, 18 trials each, with "timing"), main.timing and main.trials (60,
  "digit"/"size" equal to the first 60 of stimuli/sart-sequence.json, with digit_ms about 250 and mask_ms about 1200
  each), main.keys (empty), during_test, env.
- each "RETEST" id of a code (T3.3): sart_practice_attempts_n 1, sart_practice_omissions_1 0,
  sart_practice_omissions_2 EMPTY, sart_commission_n 0, sart_omission_n 0, sart_hit_n = all digits other than 3 in the
  first 60, and the same 60 digit/size pairs in sart.json as in the first session.
- each "RETEST" id of a code (T3.2): stroop_practice_attempts_n 1, stroop_practice_correct_1 12,
  stroop_practice_correct_2 EMPTY, stroop_correct_n 96, stroop_errors_n 0, stroop_timeouts_n 0, and the same
  96 word/ink pairs in stroop.json as in the first session.
- each "RETEST" id of a code (T3.1): coding_practice_attempts_n 1, coding_practice_errors_1 0,
  coding_practice_errors_2 EMPTY, coding_answers_n 30, coding_errors_n 0, coding_correct_n 30,
  coding_extra_keys_n 0, and the same 30 "symbol" values in coding.json as in the first session.
- each "B timeout" id: tmt_a_status "complete"; tmt_b_status "timeout",
  tmt_b_time_ms 3500, tmt_b_targets_done 3; tmt_b_minus_a_ms and
  tmt_b_over_a EMPTY cells
- each "full session" id also (T2.3): pss_1 .. pss_10 all 2, pss_total 20,
  pss_version "veldbrekht_tavrovetska_2022_appendix_a", post_distraction 1,
  post_interrupted 0, post_effort 4, post_comment "Live check: no comment.",
  email_left 1, status "complete", finished_at (ISO), last_block "thanks";
  NO email in this sheet. In the pilot CONTACTS sheet a row per full session:
  participant_code of that session, email pilot-check@example.com, created_on
  today, invite_from today + 7 days, a checkbox "invited", and the ready
  letter (starts with "Тема: Запрошення на повторне проходження дослідження",
  holds a link ending ?r=<participant_code>&mode=dev)
- each "full session" id also (T2.2): consent_at (ISO time), age 27, sex
  "female", education 5, sleep_h 7, fatigue 2, others_present 0, pointer_self
  "mouse"; no status
- each "no consent" id: a row with status "no_consent", last_block "consent"
  and NO device_*, session_type or started_at columns filled, no consent_at
- each "excluded by age" id: status "excluded_criteria", exclusion_reason
  "age", last_block "criteria"; consent_at and the device columns filled,
  but NO age, tbi or color_vision values
- each "RETEST" id (T2.4): a NEW row (own session_id) with participant_code
  equal to the code printed in the line, session_type "retest", started_at
  and device_* filled, consent_at (the retest's own), sleep_h 7, fatigue 2,
  others_present 0, pointer_self "mouse", tmt_a_* and tmt_b_* as in a full
  session (layout_version 1), no *_placeholder column, pss_total 20,
  post_* filled, status "complete", finished_at, last_block "thanks"; NO age,
  sex, education, email_left, exclusion_reason. The first session's row with
  the same participant_code is unchanged (still session_type "first", email_left 1).
  In the pilot CONTACTS sheet the row of that code now has retest_done_at
  (an ISO time, the same as the retest's finished_at), email and letter as
  before, and the number of rows did not grow
- the "RETEST of an UNKNOWN code" id: a row with participant_code
  u2n7k8m3qz, session_type "retest", status "complete", last_block "thanks";
  the CONTACTS sheet has NO row for u2n7k8m3qz (the mark is ignored)
- the "RETEST OPENED AGAIN" id: a third row with the same participant_code,
  session_type "retest", last_block "consent", consent_at, no status; it does
  not change the contacts row
- each "beacon only" id: one row with tmt_a_status "complete" and the other tmt_a_* columns""")


if __name__ == "__main__":
    main()
